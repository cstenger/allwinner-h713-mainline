#!/usr/bin/env python3
"""Generate the on-board runtime identity audit for an installed V2 slot.

The A1 audit (tools/release/make-runtime-audit.py) pins files from a sealed
release and an installation packet, which V2 images do not have yet. The V2
root is a read-only erofs image, so this audit pins the whole slot instead:

  - the booted root and boot slots hash to the bundle manifest's images
    (first `size` bytes of each partition, as RAUC wrote them);
  - the U-Boot primary at LBA 0x49ac00 hashes to the FIT that was installed;
  - `/` is the booted root slot, and the /etc overlay holds nothing under the
    HDMI runtime paths (the only writable layer that could shadow them).

Pins come from the host artifacts, never from the board. The generated script
is read-only and prints one JSON object with status PASS/FAIL, boot_id and
files_verified, which is what tools/hdmi/startup-qualification.py --audit
expects.

    tools/hdmi/make-v2-runtime-audit.py --bundle B.raucb --uboot-primary P.bin > audit.py
"""
import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

PROPER_LBA = 0x49ac00
COMPATIBLE = 'cstenger,hy200-qz713-v2'
# /etc overlay paths that would shadow the HDMI product path (relative to /etc).
SHADOW = ('systemd/system/h713-hdmi', 'systemd/system/multi-user.target.wants/h713-hdmi',
          'udev/', 'modprobe.d/', 'modules-load.d/', 'h713-hdmi', 'fstab')

BOARD = r'''
import hashlib, json, os, sys
P = %(pins)r
def fail(msg):
    print(json.dumps({'status': 'FAIL', 'error': msg, 'boot_id': boot})); sys.exit(0)
def digest(dev, offset, size):
    h = hashlib.sha256(); left = size
    with open(dev, 'rb') as f:
        f.seek(offset)
        while left:
            chunk = f.read(min(left, 1 << 20))
            if not chunk: fail('short read: ' + dev)
            h.update(chunk); left -= len(chunk)
    return h.hexdigest()
boot = open('/proc/sys/kernel/random/boot_id').read().strip()
compat = open('/proc/device-tree/compatible', 'rb').read().split(b'\0')
if P['compatible'].encode() not in compat: fail('not a V2 board')
cmdline = open('/proc/cmdline').read().split()
slot = [a.split('=', 1)[1] for a in cmdline if a.startswith('rauc.slot=')]
if slot != [P['slot']]: fail('booted slot is %%r, expected %%r' %% (slot, P['slot']))
root = os.path.realpath('/dev/disk/by-partlabel/root_' + P['slot'].lower())
bootdev = os.path.realpath('/dev/disk/by-partlabel/boot_' + P['slot'].lower())
if os.stat('/').st_dev != os.stat(root).st_rdev: fail('/ is not ' + root)
checked = []
for name, dev in (('rootfs', root), ('boot', bootdev)):
    if digest(dev, 0, P[name]['size']) != P[name]['sha256']: fail(name + ' slot image differs')
    checked.append(name)
if digest('/dev/mmcblk0', P['proper_lba'] * 512, P['proper']['size']) != P['proper']['sha256']:
    fail('U-Boot primary differs')
checked.append('uboot-primary')
upper = '/data/overlay/etc/upper'
for top, dirs, files in os.walk(upper):
    for name in dirs + files:
        rel = os.path.relpath(os.path.join(top, name), upper)
        if any(rel.startswith(s) for s in P['shadow']): fail('overlay shadows ' + rel)
checked.append('etc-overlay')
print(json.dumps({'status': 'PASS', 'boot_id': boot, 'files_verified': checked,
                  'version': P['version']}))
'''


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(bundle):
    text = subprocess.run(['unsquashfs', '-cat', str(bundle), 'manifest.raucm'],
                          check=True, capture_output=True, text=True).stdout
    section, out = None, {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('['):
            section = line.strip('[]'); out[section] = {}
        elif '=' in line and section:
            key, value = line.split('=', 1); out[section][key] = value
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--uboot-primary', type=Path, required=True,
                        help='the padded FIT written at LBA 0x49ac00')
    parser.add_argument('--slot', choices=('A', 'B'), default='B')
    args = parser.parse_args()
    m = manifest(args.bundle)
    if m['update'].get('compatible') != 'hy200-qz713-v2':
        sys.exit('refused: bundle is not for the V2')
    pins = {'compatible': COMPATIBLE, 'slot': args.slot, 'version': m['update']['version'],
            'rootfs': {'sha256': m['image.rootfs']['sha256'], 'size': int(m['image.rootfs']['size'])},
            'boot': {'sha256': m['image.boot']['sha256'], 'size': int(m['image.boot']['size'])},
            'proper_lba': PROPER_LBA,
            'proper': {'sha256': sha(args.uboot_primary), 'size': args.uboot_primary.stat().st_size},
            'shadow': SHADOW}
    sys.stdout.write(BOARD % {'pins': pins})


if __name__ == '__main__':
    main()
