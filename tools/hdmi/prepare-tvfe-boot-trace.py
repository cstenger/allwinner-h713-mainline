#!/usr/bin/env python3
"""Prepare isolated boot/PPU trace trees and optionally build; never install.

Inputs are the exact Oct 16 production kernel tree and Oct 20 installed
proper's source/object trees. Existing outputs and mismatched sources refuse.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
ASSETS = Path(__file__).resolve().parent / 'tvfe-boot-trace'
KREL = 'drivers/pmdomain/sunxi/sun50i-h713-ppu.c'
UREL = 'boot/bootm.c'
PINS = {KREL: 'a172754f1b236a6617e5ed747c2cd59adcc2445d5470e8ab733b0b5a7ccc1984',
        UREL: 'e41359ec8063451e1cee872c8f1bbc2745c9dcc864d9092523e5242796adcf0c'}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate(kernel, uboot, obj, output):
    bases = [p.resolve() for p in (kernel, uboot, obj)]
    output = output.resolve()
    if output.exists():
        raise FileExistsError(output)
    if any(output == b or b in output.parents or output in b.parents for b in bases):
        raise ValueError('output must be outside every base tree')
    for base, rel in ((kernel, KREL), (uboot, UREL)):
        if sha(base / rel) != PINS[rel]:
            raise ValueError('unrecognized source: ' + str(base / rel))
    config = (kernel / '.config').read_text()
    if 'CONFIG_SUN50I_H713_PPU=y\n' not in config:
        raise ValueError('PPU must be built-in for early_initcall')
    if (kernel / 'include/generated/utsversion.h').read_text().strip() != \
            '#define UTS_VERSION "#1 SMP Fri Oct 16 15:44:49 PDT 2026"':
        raise ValueError('not the Oct 16 production kernel build')
    image = kernel / 'arch/arm64/boot/Image'
    if hashlib.sha256(gzip.decompress((ROOT / 'build/out/Image.gz').read_bytes())).hexdigest() != sha(image):
        raise ValueError('kernel Image does not match production Image.gz')
    # The installed image is a padded FIT-containing proper, not u-boot.bin.
    manifest = json.loads((uboot.parent / 'manifest.json').read_text())
    if manifest.get('source_pin') != '320a17f71d41ed0d4be7aab25947ce015c98c48e' or \
            not manifest.get('optional_domain_controls'):
        raise ValueError('not the installed reset-controls build')
    if sha(obj / 'u-boot.bin') != 'e16ede6254491ea59fbcf36e8a295d744e6bc3a73d5b9594818c8530a97c72f9':
        raise ValueError('not the exact reset-controls U-Boot object build')
    return {'kernel_config': sha(kernel / '.config'), 'kernel_image': sha(image),
            'kernel_symvers': sha(kernel / 'Module.symvers'),
            'dtb': sha(ROOT / 'build/out/sun50i-h713-hy200-qz713df-a1.dtb'),
            'uboot_config': sha(obj / '.config'), 'uboot_binary': sha(obj / 'u-boot.bin')}


def prepare(kernel, uboot, obj, output):
    pins = validate(kernel, uboot, obj, output)
    output.mkdir(parents=True, exist_ok=False)
    for src, name in ((kernel, 'kernel'), (uboot, 'uboot-src'), (obj, 'uboot-obj')):
        # Independent files, not hard links. Reflinks avoid duplicating old objects.
        subprocess.run(['cp', '-a', '--reflink=auto', str(src), str(output / name)], check=True)
    for name, tree in (('0001-kernel-ppu-observation.patch', 'kernel'),
                       ('0002-uboot-handoff-observation.patch', 'uboot-src')):
        subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(ASSETS / name)],
                       cwd=output / tree, check=True)
    shutil.copyfile(ASSETS / 'h713_tvfe_boot_trace.h', output / 'uboot-src/include/h713_tvfe_boot_trace.h')
    (output / 'uboot-src/.scmversion').write_text('-g320a17f71d41-tvfe-boot-trace-v1\n')
    manifest = {'schema': 1, 'purpose': 'bench TVFE boot trace; offline, not installed',
                'bases': {k: str(v.resolve()) for k, v in [('kernel', kernel), ('uboot', uboot), ('obj', obj)]},
                'baseline': pins,
                'assets': {p.name: sha(p) for p in sorted(ASSETS.iterdir()) if p.is_file()},
                'kernel_trace_requires': 'h713_tvfe_trace=1', 'built': False}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def build(output, jobs):
    manifest = json.loads((output / 'manifest.json').read_text())
    kernel = output / 'kernel'
    commands = [
        ['make', '-C', str(kernel), 'ARCH=arm64', 'LLVM=1', '-j' + str(jobs), 'Image', 'modules'],
        ['make', '-C', str(output / 'uboot-src'), 'O=' + str(output / 'uboot-obj'),
         'ARCH=arm', 'HOSTCC=clang', 'CC=clang -target aarch64-linux-gnu',
         'LD=ld.lld', 'AR=llvm-ar', 'NM=llvm-nm', 'OBJCOPY=llvm-objcopy',
         'OBJDUMP=llvm-objdump', 'READELF=llvm-readelf', 'STRIP=llvm-strip',
         'KAFLAGS=-fintegrated-as',
         'KCFLAGS=-fintegrated-as -Wno-error=deprecated-non-prototype -fno-stack-protector',
         'BL31=' + str(ROOT / 'build/out/bl31.bin'), '-j' + str(jobs)],
    ]
    for i, cmd in enumerate(commands):
        with (output / ('build-%d.log' % i)).open('w') as log:
            subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True)
    artifacts = output / 'artifacts'
    artifacts.mkdir(exist_ok=False)
    with (artifacts / 'Image.gz').open('wb') as stream:
        stream.write(gzip.compress((kernel / 'arch/arm64/boot/Image').read_bytes(), mtime=0))
    shutil.copyfile(ROOT / 'build/out/sun50i-h713-hy200-qz713df-a1.dtb', artifacts / 'board.dtb')
    its = (ROOT / 'build/out/h713-kernel.its').read_text()
    its = its.replace(str(ROOT / 'build/out/Image.gz'), str(artifacts / 'Image.gz'))
    its = its.replace(str(ROOT / 'build/out/sun50i-h713-hy200-qz713df-a1.dtb'), str(artifacts / 'board.dtb'))
    its = its.replace('H713 arm64 kernel (6.18.38)', 'H713 bench TVFE boot trace v1 (6.18.38)')
    (artifacts / 'kernel.its').write_text(its)
    subprocess.run([str(output / 'uboot-obj/tools/mkimage'), '-f', str(artifacts / 'kernel.its'),
                    str(artifacts / 'kernel.fit')], check=True, capture_output=True)
    shutil.copyfile(output / 'uboot-obj/u-boot-sunxi-with-spl.fit.itb', artifacts / 'proper.itb')
    # A diagnostic FIT is not a normal startup-script replacement (size pinned).
    manifest.update(built=True, commands=commands, compiler=subprocess.check_output(['clang', '--version'], text=True),
                    kernel_release=(kernel / 'include/config/kernel.release').read_text().strip(),
                    symvers_unchanged=sha(kernel / 'Module.symvers') == manifest['baseline']['kernel_symvers'],
                    artifacts={p.name: {'size': p.stat().st_size, 'sha256': sha(p)}
                               for p in sorted(artifacts.iterdir()) if p.is_file()})
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kernel-base', type=Path, required=True)
    p.add_argument('--uboot-base', type=Path, required=True)
    p.add_argument('--uboot-obj', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--build', action='store_true')
    p.add_argument('--jobs', type=int, default=8)
    args = p.parse_args()
    if args.jobs < 1:
        p.error('--jobs must be positive')
    out = args.output.resolve()
    prepare(args.kernel_base.resolve(), args.uboot_base.resolve(), args.uboot_obj.resolve(), out)
    if args.build:
        build(out, args.jobs)
    print(out / 'manifest.json')


if __name__ == '__main__':
    main()
