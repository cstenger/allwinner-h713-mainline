#!/usr/bin/env python3
"""Assemble the offline U-Boot 0006 bundle (comm-trace markers off k0/k1).

Proper-only: the startup script does not change. Inputs are the reproducible
baseline and candidate combined images (release environment, pinned epoch,
kernel DT as of the 0005 install, commit 1166ab3f) and the installed startup
script pair. Refused unless:

  - the baseline proper reproduces the installed proper pin,
  - the script files are the installed pair (baseline == candidate script),
  - the candidate FIT differs only in its U-Boot image (DTB and BL31 equal),
  - the candidate U-Boot image carries the 0006 markers: 61 `lui t8,0xae34`
    and no `ori k1,zero,0xa002`, against 9 / 1 in the baseline.

The bundle reuses install-single-launch.py (proper phase only).
"""
import argparse, hashlib, json, struct, subprocess, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_PROPER = '33bc73c871d76cc7d69bd5d7b421fad0b9265f6b871a2d94ac396c0561343216'  # 0005, 2026-11-09
CMD = 'a9161a8641a3f0c4162f01f3ec07538cd16779cf4cb674fbcf2c38c217fb01e3'
SCR = '4c3495e2956dfa4b6d55c92f3fea7035580310a8a13ce431354a42483183e228'
SERIES = ['0000-h713-shared-dt-panel-regulator-prerequisites.patch',
          '0001-h713-establish-initial-panel-power-state.patch',
          '0003-env-mmc-preserve-configured-offset-width.patch',
          '0004-h713-single-display-firmware-launch.patch',
          '0005-h713-early-panel-off-interval.patch',
          '0006-h713-comm-trace-markers-avoid-k0-k1.patch']


def sha(b):
    return hashlib.sha256(b).hexdigest()


def need(ok, msg):
    if not ok:
        raise SystemExit(msg)


def proper(combined):
    data = Path(combined).read_bytes()[32768:]
    need(struct.unpack('>II', data[:8]) == (0xd00dfeed, len(data)), 'unexpected combined SPL/proper layout')
    return data + b'\0' * ((-len(data)) % 512)


def images(fit, dumpimage):
    with tempfile.TemporaryDirectory() as t:
        f = Path(t) / 'fit'; f.write_bytes(fit)
        out = []
        for i in range(3):
            o = Path(t) / str(i)
            subprocess.run([dumpimage, '-T', 'flat_dt', '-p', str(i), '-o', str(o), str(f)],
                           check=True, capture_output=True)
            out.append(o.read_bytes())
    return out


def count(b, w):
    return b.count(struct.pack('<I', w))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--baseline', required=True, type=Path)
    p.add_argument('--candidate', required=True, type=Path)
    p.add_argument('--scripts', required=True, type=Path, help='directory with the installed h713-hdmi.cmd/.scr')
    p.add_argument('--dumpimage', required=True)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    base, cand = proper(a.baseline), proper(a.candidate)
    need(sha(base) == BASE_PROPER, 'baseline build does not reproduce the installed proper')
    need(sha(cand) != BASE_PROPER and len(cand) == len(base), 'candidate proper missing or resized')
    bu, ba, bd = images(base, a.dumpimage)
    cu, ca, cd = images(cand, a.dumpimage)
    need(ba == ca and bd == cd, 'candidate DTB/BL31 differ from the baseline')
    need((count(bu, 0x3c18ae34), count(bu, 0x341ba002)) == (9, 1), 'baseline U-Boot markers unexpected')
    need((count(cu, 0x3c18ae34), count(cu, 0x341ba002), count(cu, 0x3419a002)) == (61, 0, 1),
         'candidate U-Boot does not carry the 0006 markers')
    cmd, scr = (a.scripts / 'h713-hdmi.cmd').read_bytes(), (a.scripts / 'h713-hdmi.scr').read_bytes()
    need(sha(cmd) == CMD and sha(scr) == SCR, 'script files are not the installed pair')
    a.output.mkdir(parents=True, exist_ok=False)
    files = {'u-boot-proper.itb': cand, 'h713-hdmi.cmd': cmd, 'h713-hdmi.scr': scr,
             'install-single-launch.py': (ROOT / 'tools/hdmi/install-single-launch.py').read_bytes()}
    for name, data in files.items():
        (a.output / name).write_bytes(data)
    script = {'h713-hdmi.cmd': CMD, 'h713-hdmi.scr': SCR}
    manifest = dict(schema='h713-single-launch-v1', files={n: sha(d) for n, d in files.items()},
                    proper=dict(baseline=BASE_PROPER, candidate=sha(cand)),
                    script=dict(baseline=script, candidate=dict(script)),
                    proper_only=True, uboot_series=SERIES,
                    checks=dict(dtb_equal=True, bl31_equal=True, uboot_lui_t8=61, uboot_old_a002=0))
    (a.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
