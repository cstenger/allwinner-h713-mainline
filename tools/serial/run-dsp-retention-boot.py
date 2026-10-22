#!/usr/bin/env python3
"""Reuse the guarded RAM loader with the retention FIT, path and boot flag."""
import importlib.util
import json
import re
import zlib
from pathlib import Path

spec = importlib.util.spec_from_file_location('retention_boot', Path(__file__).with_name('run-tvfe-boot-trace.py'))
loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loader)
loader.REMOTE_FIT = '/root/hdmi-dsp-retention-2026-10-21/kernel.fit'
loader.BOOTARGS += ' h713_tvfe_retain=1'
original_validate = loader.validate
original_boot = loader.boot
guard_bytes = None


def validate(prepared):
    global guard_bytes
    manifest = json.loads((prepared / 'manifest.json').read_text())
    if manifest.get('purpose') != 'bench DSP warm retention; not installed' or \
            'h713_tvfe_retain=1' not in manifest.get('requires', []):
        raise ValueError('retention candidate manifest required')
    guard_bytes = (prepared / 'bundle/h713-hdmi-hold-guard').read_bytes()
    if loader.hashlib.sha256(guard_bytes).hexdigest() != manifest['bundle']['h713-hdmi-hold-guard']:
        raise ValueError('bench guard changed')
    return original_validate(prepared)


def check_installed_guard(con):
    if guard_bytes is None:
        raise ValueError('validated bench guard required')
    con.checked('ext4load mmc 1:1a 0x53000000 /usr/lib/systemd/system-shutdown/h713-hdmi-hold-guard')
    con.checked('itest ${filesize} == %x' % len(guard_bytes))
    out = con.run('crc32 0x53000000 %x' % len(guard_bytes))
    m = re.search(rb'==>\s*([0-9a-fA-F]{8})\b', out)
    if not m or int(m.group(1), 16) != zlib.crc32(guard_bytes):
        raise RuntimeError('installed bench guard CRC mismatch; no diagnostic boot')


def boot(con, expected, fit):
    return original_boot(con, expected, fit, before_load=check_installed_guard)


loader.validate = validate
loader.boot = boot
if __name__ == '__main__':
    loader.main()
