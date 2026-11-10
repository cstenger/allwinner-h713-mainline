#!/usr/bin/env python3
"""Offline recovery-input checks. Never opens a device or prints environment values."""
import argparse
import hashlib
import json
from pathlib import Path
import stat
import struct
import zlib

PROPER_HASH = '1b1f702fc7b52adf8246b124b8fbe209b7dadc651a37e53a600689810c45302e'
ENV_HASH = '6eb7b7958139263f88cc0a0830b4ac33f4b4ca71b096081802b2f50f2cd205bc'
SPL_HASH = 'cb9da87448a57aa1cafbc7ebf66200b5183304cef1eafe23d0818b99696a49ec'
RESCUE_SPL_HASH = 'dab3b1585a8d05d30d87a57795fa505409304ce7287cfa58d5c8deed1bcf75f0'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_regular(path):
    require(stat.S_ISREG(path.stat().st_mode), 'input must be a regular host file')
    return path.read_bytes()


def check_blob(data, size, digest):
    require(len(data) == size, 'recovery input size mismatch')
    require(hashlib.sha256(data).hexdigest() == digest, 'recovery input SHA-256 mismatch')


def check_environment(data, selected):
    require(len(data) == 65536, 'environment must be 64 KiB, nonredundant')
    require(struct.unpack('<I', data[:4])[0] == zlib.crc32(data[4:]), 'environment CRC mismatch')
    body = data[4:]
    require(b'\0\0' in body, 'environment terminator missing')
    values = {}
    for entry in body.split(b'\0\0', 1)[0].split(b'\0'):
        require(b'=' in entry, 'malformed environment entry')
        key, value = entry.split(b'=', 1)
        require(key and key not in values, 'empty or duplicate environment key')
        values[key] = value
    for key, value in selected.items():
        require(values.get(key.encode()) == value.encode(), 'saved startup policy mismatch: ' + key)
    return len(values)


def legacy_lba(capacity):
    narrowed = struct.unpack('<i', struct.pack('<I', 0x93d80000))[0]
    return ((capacity + narrowed) & 0xffffffff) // 512


def check_proper(data):
    check_blob(data, 1877 * 512, PROPER_HASH)
    magic, size = struct.unpack('>II', data[:8])
    require(magic == 0xd00dfeed and size == 960817, 'proper FIT header mismatch')
    require((size + 511) // 512 == 1877, 'proper sector count mismatch')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    root = args.root
    inventory = json.loads(read_regular(root / 'docs/production-audit/2026-10-28/board-inventory.json'))
    checkpoint = root / 'local/recovery/2026-10-28-production-cleanup'
    for line in read_regular(checkpoint / 'SHA256SUMS').decode().splitlines():
        digest, name = line.split('  ', 1)
        require(Path(name).name == name, 'checkpoint entry must be a basename')
        require(hashlib.sha256(read_regular(checkpoint / name)).hexdigest() == digest,
                'checkpoint checksum mismatch: ' + name)
    proper = read_regular(root / 'build/hdmi-reset-controls-2026-10-20/trial-package/proper-controls.bin')
    env = read_regular(root / 'build/hdmi-reset-baseline-2026-10-20/trial-package/active-environment-backup.bin')
    check_proper(proper)
    check_blob(env, 65536, ENV_HASH)
    selected = inventory['boot_environments']['documented-active']['selected_values']
    require(set(selected) == {'bootcmd', 'preboot', 'bootdelay', 'h713_hdmi_previous_bootcmd'},
            'audit startup-policy keys changed')
    count = check_environment(env, selected)
    for path, digest in [
        ('local/h713-lab/uboot-backup-20261016/spl-lba10.bin', SPL_HASH),
        ('build/out/h713-rescue-spl.bin', RESCUE_SPL_HASH),
    ]:
        check_blob(read_regular(root / path), 32768, digest)
    require(legacy_lba(7818182656) == 0x32ec00, 'legacy arithmetic differs from observed board')
    require(inventory['bootloader']['uboot-proper']['sha256'] == PROPER_HASH,
            'audit proper identity changed')
    require(inventory['boot_environments']['documented-active']['sha256'] == ENV_HASH,
            'audit environment identity changed')
    print(json.dumps({
        'result': 'PASS offline retained recovery inputs',
        'environment_entries_validated': count,
        'saved_startup_policy_matches_audit': True,
        'legacy_environment_lba': '0x32ec00',
        'intended_environment_lba': '0x49ec00',
        'proper_rollback_sectors': 1877,
        'board_contact': False,
        'candidate_built_or_installation_ready': False,
        'limits': ['No fresh device identity, GPT or rescue-slot readback',
                   'No new U-Boot build, migration rehearsal or hardware test'],
    }, indent=2))


if __name__ == '__main__':
    main()
