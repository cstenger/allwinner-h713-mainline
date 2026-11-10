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
"""
import argparse
import hashlib
import importlib.util
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Installed since 2026-11-09 (0190 route hand-over cover, install-kernel-fit.py).
INSTALLED_FIT = 'd4cb9c9586172ec88c6e1c4f349a8f6a2506d23acc1bda12c0cd5c1164fb1bb0'
INSTALLED_CMD = 'bb89537cdbb0bedc5df5275859c5c83e43b5a058a4c2e3ccbbc70ef2ad69f2e5'
INSTALLED_SCR = '349a8c7485daa16b622c9761bf7e559b292842c212e5d1d3e2939315b7543a73'
DTB = 'sun50i-h713-hy200-qz713df-a1.dtb'


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


def check(baseline, candidate, installed_fit, expected_diff):
    bt, ct = tree(baseline), tree(candidate)
    bfit = (baseline/'build/out/h713-kernel-production.fit').read_bytes()
    cfit = (candidate/'build/out/h713-kernel-production.fit').read_bytes()
    need(sha(bfit) == installed_fit, 'baseline build does not reproduce the installed FIT')
    need(cfit != bfit, 'candidate FIT equals the baseline')
    bc, cc = config(bt/'.config'), config(ct/'.config')
    diff = sorted(k for k in set(bc) | set(cc) if bc.get(k) != cc.get(k))
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
    a = p.parse_args()
    bfit, cfit, dtb = check(a.baseline, a.candidate, a.installed_fit, a.config_diff)
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
