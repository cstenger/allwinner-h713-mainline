#!/usr/bin/env python3
"""Build the HPD re-advertise owner bundle for install-readvertise.sh.

Regenerates the SCP payload with --verify-restore --readvertise, builds the signal
module against the validated 6.18.38 kernel tree, and packages it with the
re-advertise service, its unit and the installer.
"""
import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / 'tools/hdmi'
MODULE = ROOT / 'modules/hdmi-signal'
KERNEL = ROOT / 'build/linux-6.18.38-0b40c55351a5ebc7b8b3d2a7e6c481393402000af1ee29c5742e2664641bcd6e'
EDID = TOOLS / 'fixtures/hdmi-audio-edid.hex'
FILES = ('h713-hdmi-readvertise.py', 'h713-hdmi-readvertise.service', 'install-readvertise.sh')


def build(out):
    if out.exists():
        raise FileExistsError(out)
    work = out.with_name(out.name + '.module')
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    for name in ('h713-hdmi-signal.c', 'Makefile'):
        shutil.copyfile(MODULE / name, work / name)
    subprocess.run([sys.executable, str(TOOLS / 'make-edid-trial-code.py'), '--verify-restore', '--readvertise',
                    '--edid', str(EDID), str(work / 'edid-trial-code.h')], check=True)
    subprocess.run(['make', '-C', str(KERNEL), f'M={work}', f'KBUILD_EXTRA_SYMBOLS={ROOT}/modules/hdmi-receiver/Module.symvers',
                    'ARCH=arm64', 'LLVM=1', 'W=1', 'modules'], check=True)
    out.mkdir(parents=True)
    shutil.copyfile(work / 'h713-hdmi-signal.ko', out / 'h713-hdmi-signal.ko')
    for name in FILES:
        shutil.copyfile(TOOLS / name, out / name)
    (out / 'SHA256SUMS').write_text(''.join(
        hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n'
        for p in sorted(out.iterdir()) if p.name != 'SHA256SUMS'))
    print((out / 'SHA256SUMS').read_text(), end='')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    build(parser.parse_args().output.resolve())
