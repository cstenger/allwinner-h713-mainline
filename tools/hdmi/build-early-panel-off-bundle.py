#!/usr/bin/env python3
"""Assemble the offline early-panel-off bundle (U-Boot 0005); no board access.

Inputs: the reproducible baseline and candidate combined U-Boot images
(release environment, pinned epoch). The baseline must reproduce the
installed proper pin. The scripts come from build-startup.py with the
installed FIT/FDT sizes, and the default script must reproduce the
installed command byte-for-byte. The bundle reuses the hardware-proven
install-single-launch.py unchanged: "baseline" is the installed single-launch
proper and script, "candidate" adds `h713_disp panel-off`.
"""
import argparse
import hashlib
import importlib.util
import json
import shutil
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_PROPER = '7e7835d0966d9268cf4a60887ba439e06eb2aed56c9563dc66247eab2b9d6c0c'  # single launch, 2026-11-06
BASE_CMD = 'd2e8cb7a2744c0abb8bce97a441a75ff05d03c0a1a0df7959f215d3cd28e7ad2'
BASE_SCR = '7e833c6dcc28ba435efb19b240c5aa1f228e8464a0b67abb191cc7485eab0d99'
FIT_SIZE, FDT_SIZE = 0x7428ec, 0x876a


def sha(b):
    return hashlib.sha256(b).hexdigest()


def proper(combined):
    data = Path(combined).read_bytes()[32768:]
    if struct.unpack('>II', data[:8]) != (0xd00dfeed, len(data)):
        raise SystemExit('unexpected combined SPL/proper layout')
    return data + b'\0' * ((-len(data)) % 512)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline', required=True, type=Path)
    p.add_argument('--candidate', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    base, cand = proper(a.baseline), proper(a.candidate)
    if sha(base) != BASE_PROPER:
        raise SystemExit('baseline build does not reproduce the installed proper')
    spec = importlib.util.spec_from_file_location('startup', ROOT / 'tools/hdmi/build-startup.py')
    st = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(st)
    old = st.script(fit_size=FIT_SIZE, fdt_size=FDT_SIZE, early_panel_off=False).encode()
    new = st.script(fit_size=FIT_SIZE, fdt_size=FDT_SIZE).encode()
    if sha(old) != BASE_CMD or sha(st.legacy_image(old)) != BASE_SCR:
        raise SystemExit('default script does not reproduce the installed script')
    a.output.mkdir(parents=True, exist_ok=False)
    files = {'u-boot-proper.itb': cand, 'h713-hdmi.cmd': new, 'h713-hdmi.scr': st.legacy_image(new),
             'install-single-launch.py': (ROOT / 'tools/hdmi/install-single-launch.py').read_bytes()}
    for name, data in files.items():
        (a.output / name).write_bytes(data)
    manifest = dict(schema='h713-single-launch-v1',
                    files={n: sha(d) for n, d in files.items()},
                    proper=dict(baseline=BASE_PROPER, candidate=sha(cand)),
                    script=dict(baseline={'h713-hdmi.cmd': BASE_CMD, 'h713-hdmi.scr': BASE_SCR},
                                candidate={'h713-hdmi.cmd': sha(new), 'h713-hdmi.scr': sha(st.legacy_image(new))}),
                    uboot_series=(ROOT / 'patches/u-boot/series').read_text().split())
    (a.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
