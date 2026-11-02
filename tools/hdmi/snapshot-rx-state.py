#!/usr/bin/env python3
"""Read-only board snapshot for diffing a failed HDMI first advert against a working boot.

Run on the board: ssh root@board python3 - < snapshot-rx-state.py > out.json
Reads debugfs summaries and an allowlist of kernel-owned register blocks with 32-bit
loads. Never maps the receiver window 0x07091000-0x07091fff or 0x06940000-0x0694ffff.
No writes, module loads, service changes or resets.
"""
from datetime import datetime, timezone
import json
import mmap
import os
from pathlib import Path

FORBIDDEN = ((0x07091000, 0x07092000), (0x06940000, 0x06950000))
# (name, base, bytes): kernel-claimed blocks in /proc/iomem, plus words read safely before.
BLOCKS = (
    ('ccu', 0x02001000, 0x1000),
    ('pio', 0x02000000, 0x800),
    ('r_ccu', 0x07010000, 0x240),
    ('r_pio', 0x07022000, 0x400),
    ('ppu_tvfe', 0x070010a4, 4),
    ('ppu_tvcap', 0x07001124, 4),
    ('scp_reset', 0x07000400, 4),
    ('scp_sram', 0x00100000, 0x5000),
)
DEBUGFS = (
    'clk/clk_summary', 'pm_genpd/pm_genpd_summary', 'regulator/regulator_summary', 'gpio',
    'pinctrl/7022000.pinctrl/pinmux-pins', 'pinctrl/7022000.pinctrl/pinconf-pins',
    'pinctrl/2000000.pinctrl/pinmux-pins', 'pinctrl/2000000.pinctrl/pinconf-pins',
)


def words(base, size):
    for lo, hi in FORBIDDEN:
        if base < hi and lo < base + size:
            raise RuntimeError('forbidden window: 0x%x' % base)
    page = base & ~4095
    length = ((base - page + size + 4095) // 4096) * 4096
    fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC | os.O_CLOEXEC)
    try:
        with mmap.mmap(fd, length, flags=mmap.MAP_SHARED, prot=mmap.PROT_READ, offset=page) as view:
            cells = memoryview(view)[base - page:base - page + size].cast('I')
            out = [cells[i] for i in range(size // 4)]  # one 32-bit load each
            cells.release()
            return out
    finally:
        os.close(fd)


def text(path):
    try:
        return Path(path).read_text(errors='replace')
    except OSError as error:
        return 'ERROR: %s' % error


result = {
    'utc': datetime.now(timezone.utc).isoformat(),
    'boot_id': text('/proc/sys/kernel/random/boot_id').strip(),
    'uptime': text('/proc/uptime').strip(),
    'signal': text('/sys/devices/platform/h713-hdmi-ring/signal').strip(),
    'debugfs': {name: text('/sys/kernel/debug/' + name) for name in DEBUGFS},
    'registers': {},
}
for name, base, size in BLOCKS:
    try:
        result['registers'][name] = {'base': base, 'words': words(base, size)}
    except (OSError, RuntimeError, ValueError) as error:
        result['registers'][name] = {'base': base, 'error': str(error)}
print(json.dumps(result, sort_keys=True))
