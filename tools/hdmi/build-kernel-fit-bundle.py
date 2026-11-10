#!/usr/bin/env python3
"""Assemble the offline kernel FIT bundle for install-kernel-fit.py; no board access.

Inputs are two release-equivalent kernel builds (tools/build/build.sh kernel
with KERNEL_CONFIG=production and the release epoch/identity), the baseline
from the installed sources and the candidate with one config change. Refused
unless:
  - the baseline FIT reproduces the installed FIT byte-for-byte,
  - the two .configs differ only in the expected symbols,
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
INSTALLED_FIT = '6ccf040a513b89ba1062c206de4b6df36bdbe35b39d6e40e7711e8776f0fda9a'
INSTALLED_CMD = 'b2ea58fed3fe8d4b242687c663390d4a384a4e06b78a3ac838927d3ba9472114'
INSTALLED_SCR = 'ed3e4494d5f07d845a6f86c40cc0e363db0bdd5d3d8c95fb53ea3523ad480b54'
EXPECTED_DIFF = ['CONFIG_LEGACY_PTYS', 'CONFIG_LEGACY_PTY_COUNT']
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


def check(baseline, candidate):
    bt, ct = tree(baseline), tree(candidate)
    bfit = (baseline/'build/out/h713-kernel-production.fit').read_bytes()
    cfit = (candidate/'build/out/h713-kernel-production.fit').read_bytes()
    need(sha(bfit) == INSTALLED_FIT, 'baseline build does not reproduce the installed FIT')
    need(cfit != bfit, 'candidate FIT equals the baseline')
    bc, cc = config(bt/'.config'), config(ct/'.config')
    diff = sorted(k for k in set(bc) | set(cc) if bc.get(k) != cc.get(k))
    need(diff == EXPECTED_DIFF, 'unexpected config difference: '+str(diff))
    need(cc.get('CONFIG_LEGACY_PTYS') == 'n', 'candidate still has legacy ptys')
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
    a = p.parse_args()
    bfit, cfit, dtb = check(a.baseline, a.candidate)
    spec = importlib.util.spec_from_file_location('startup', ROOT/'tools/hdmi/build-startup.py')
    st = importlib.util.module_from_spec(spec);spec.loader.exec_module(st)
    old = st.script(fit_size=len(bfit), fdt_size=len(dtb)).encode()
    new = st.script(fit_size=len(cfit), fdt_size=len(dtb)).encode()
    need(sha(old) == INSTALLED_CMD and sha(st.legacy_image(old)) == INSTALLED_SCR,
         'baseline script does not reproduce the installed script')
    a.output.mkdir(parents=True, exist_ok=False)
    files = {'h713-kernel.fit': cfit, 'h713-hdmi.cmd': new, 'h713-hdmi.scr': st.legacy_image(new)}
    for name, data in files.items(): (a.output/name).write_bytes(data)
    shutil.copy(ROOT/'tools/hdmi/install-kernel-fit.py', a.output/'install-kernel-fit.py')
    manifest = dict(schema='h713-kernel-fit-v1',
                    files={n: sha(d) for n, d in files.items()},
                    baseline={'h713-kernel.fit': INSTALLED_FIT, 'h713-hdmi.cmd': INSTALLED_CMD,
                              'h713-hdmi.scr': INSTALLED_SCR},
                    sizes=dict(baseline_fit=len(bfit), candidate_fit=len(cfit), fdt=len(dtb)),
                    checks={'module_symvers_equal': True, 'kernel_release_equal': True,
                            'config_diff': EXPECTED_DIFF},
                    installer=sha((a.output/'install-kernel-fit.py').read_bytes()))
    (a.output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
