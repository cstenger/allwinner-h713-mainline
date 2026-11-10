#!/usr/bin/env python3
"""Assemble the offline kernel FIT bundle for install-kernel-fit.py; no board access.

Inputs are two release-equivalent kernel builds (tools/build/build.sh kernel
with KERNEL_CONFIG=production and the release epoch/identity): the baseline
from the installed sources and the candidate with the change. Refused unless:
  - the baseline FIT reproduces the installed FIT byte-for-byte (--installed-*
    pins; the defaults are what the board runs),
  - the two .configs differ only in the --config-diff symbols (none: a
    source-only change),
  - Module.symvers and the kernel release are identical (the installed
    out-of-tree and in-tree modules keep loading),
  - the board DTB is identical, and
  - the baseline script reproduces the installed startup script.

--rustc-probe-transition is for the first bundle after build.sh stopped
letting host rustc into .config (2026-11-09). FITs installed before it embed
rustc 1.99's probe results, so their baseline only reproduces with
H713_KERNEL_RUSTC=<that rustc>; the candidate is built normally. The option
expects exactly RUSTC_PROBE_SYMBOLS to differ, set in the baseline and "none"
in the candidate. Later baselines build without rustc and need no option.
"""
import argparse
import hashlib
import importlib.util
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Installed since 2026-11-10 (0190 + rustc-free kernel config, install-kernel-fit.py).
INSTALLED_FIT = '9d49630823d0d8636fc192cb4db7b000dbbf57f30361ee845e9e2fe517675ca6'
INSTALLED_CMD = '2dd9adb1bdd42a9325b429abfad68aabea3330f4012fe0a10a872896718c7b0b'
INSTALLED_SCR = '4c2453a4ee311bc8cec1b069cf078ce3d471172c87157fdfb1f4d9150f1c02d8'
DTB = 'sun50i-h713-hy200-qz713df-a1.dtb'
# What rustc 1.99 (installed kernels up to 2026-11-09) wrote into .config.
RUSTC_PROBE_SYMBOLS = {
    'CONFIG_RUSTC_VERSION': ('109900', '0'), 'CONFIG_RUSTC_LLVM_VERSION': ('230101', '0'),
    **{'CONFIG_RUSTC_HAS_'+s: ('y', None) for s in
       ('COERCE_POINTEE', 'SPAN_FILE', 'UNNECESSARY_TRANSMUTES', 'FILE_WITH_NUL', 'FILE_AS_C_STR')},
    'CONFIG_HAVE_CFI_ICALL_NORMALIZE_INTEGERS_RUSTC': ('y', None),
}


def sha(b): return hashlib.sha256(b).hexdigest()


def need(ok, message):
    if not ok: raise SystemExit(message)


def tree(work):
    trees = sorted((work/'build').glob('linux-*/'))
    need(len(trees) == 1, 'expected exactly one kernel tree in '+str(work))
    return trees[0]


def config(path):
    out = {}
    for line in path.read_text().splitlines():
        if m := re.fullmatch(r'(CONFIG_\w+)=(.*)', line): out[m[1]] = m[2]
        elif m := re.fullmatch(r'# (CONFIG_\w+) is not set', line): out[m[1]] = 'n'
    return out


def check(baseline, candidate, installed_fit, expected_diff, rustc_transition=False):
    bt, ct = tree(baseline), tree(candidate)
    bfit = (baseline/'build/out/h713-kernel-production.fit').read_bytes()
    cfit = (candidate/'build/out/h713-kernel-production.fit').read_bytes()
    need(sha(bfit) == installed_fit, 'baseline build does not reproduce the installed FIT')
    need(cfit != bfit, 'candidate FIT equals the baseline')
    bc, cc = config(bt/'.config'), config(ct/'.config')
    diff = sorted(k for k in set(bc) | set(cc) if bc.get(k) != cc.get(k))
    if rustc_transition:
        for k, (old, new) in RUSTC_PROBE_SYMBOLS.items():
            need((bc.get(k), cc.get(k)) == (old, new), 'not the rustc probe transition: %s %s -> %s'
                 % (k, bc.get(k), cc.get(k)))
        expected_diff = [*expected_diff, *RUSTC_PROBE_SYMBOLS]
    need(diff == sorted(expected_diff), 'unexpected config difference: '+str(diff))
    need((bt/'Module.symvers').read_bytes() == (ct/'Module.symvers').read_bytes(), 'Module.symvers differs')
    release = lambda t: (t/'include/config/kernel.release').read_text()
    need(release(bt) == release(ct), 'kernel release differs')
    bdtb, cdtb = ((w/'build/out'/DTB).read_bytes() for w in (baseline, candidate))
    need(bdtb == cdtb, 'board DTB differs')
    return bfit, cfit, bdtb


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--baseline', required=True, type=Path, help='baseline kernel work directory')
    p.add_argument('--candidate', required=True, type=Path, help='candidate kernel work directory')
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--installed-fit', default=INSTALLED_FIT)
    p.add_argument('--installed-cmd', default=INSTALLED_CMD)
    p.add_argument('--installed-scr', default=INSTALLED_SCR)
    p.add_argument('--config-diff', action='append', default=[],
                   help='a CONFIG_ symbol the candidate is meant to change (repeat)')
    p.add_argument('--rustc-probe-transition', action='store_true',
                   help='baseline built with H713_KERNEL_RUSTC (rustc 1.99), candidate without')
    a = p.parse_args()
    bfit, cfit, dtb = check(a.baseline, a.candidate, a.installed_fit, a.config_diff, a.rustc_probe_transition)
    if a.rustc_probe_transition: a.config_diff += list(RUSTC_PROBE_SYMBOLS)
    spec = importlib.util.spec_from_file_location('startup', ROOT/'tools/hdmi/build-startup.py')
    st = importlib.util.module_from_spec(spec);spec.loader.exec_module(st)
    old = st.script(fit_size=len(bfit), fdt_size=len(dtb)).encode()
    new = st.script(fit_size=len(cfit), fdt_size=len(dtb)).encode()
    need(sha(old) == a.installed_cmd and sha(st.legacy_image(old)) == a.installed_scr,
         'baseline script does not reproduce the installed script')
    a.output.mkdir(parents=True, exist_ok=False)
    files = {'h713-kernel.fit': cfit, 'h713-hdmi.cmd': new, 'h713-hdmi.scr': st.legacy_image(new)}
    for name, data in files.items(): (a.output/name).write_bytes(data)
    shutil.copy(ROOT/'tools/hdmi/install-kernel-fit.py', a.output/'install-kernel-fit.py')
    manifest = dict(schema='h713-kernel-fit-v1',
                    files={n: sha(d) for n, d in files.items()},
                    baseline={'h713-kernel.fit': a.installed_fit, 'h713-hdmi.cmd': a.installed_cmd,
                              'h713-hdmi.scr': a.installed_scr},
                    sizes=dict(baseline_fit=len(bfit), candidate_fit=len(cfit), fdt=len(dtb)),
                    checks={'module_symvers_equal': True, 'kernel_release_equal': True,
                            'config_diff': sorted(a.config_diff)},
                    installer=sha((a.output/'install-kernel-fit.py').read_bytes()))
    (a.output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
