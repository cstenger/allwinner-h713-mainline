#!/usr/bin/env python3
"""Read-only preboot census at the U-Boot prompt, then optionally `boot`.

For the warm-retention test (docs/hdmi-warm-retention-test-design-2026-10-21.md).
Run after catch-cold-uboot.py has stopped autoboot. Sends only allowlisted
commands by default: `printenv bootcmd`, `md.l <addr> 1` for the addresses
below, and `boot`. The opt-in --open-ppu-bus diagnostic additionally reads
GP6/MIPS status and writes exactly one bus-r-ppu gate/reset word; it never
boots automatically. The PPU status words are read only when R_CCU bus-r-ppu
(0x070101ac) shows both its gate (bit 0) and reset release (bit 16), because
the PPU sits behind that clock and reset. Never reads CPUS/ARISC 0x07091xxx.

`--record-bootcmd FILE` stores the observed bootcmd (first, cold catch).
`--expected-bootcmd FILE` refuses to boot if the bootcmd differs (warm catch).
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from console import open_port, write_slow, drain  # noqa: E402

R_CCU_PPU = 0x070101ac
PPU_TVFE = 0x070010a4
PPU_TVCAP = 0x07001124
PPU_OPEN = (1 << 0) | (1 << 16)
MIPS_STATUS = 0x0306101c
GP6 = 0x07090118
OPEN_PPU_COMMAND = 'mw.l 0x070101ac 0x00010001 1'
ALLOWED_MD = {R_CCU_PPU, PPU_TVFE, PPU_TVCAP}
PPU_STATE_MASK = 0x30000
PPU_STATE = {0x10000: 'on', 0x20000: 'off'}


def command_allowed(line, open_ppu_bus=False):
    if open_ppu_bus and line == OPEN_PPU_COMMAND:
        return True
    if line in ('printenv bootcmd', 'boot'):
        return True
    m = re.fullmatch(r'md\.l 0x([0-9a-f]{8}) 1', line)
    allowed = ALLOWED_MD | ({MIPS_STATUS, GP6} if open_ppu_bus else set())
    return bool(m) and int(m.group(1), 16) in allowed


def parse_md(output, address):
    """Parse `md.l` output: '070101ac: 00010001    ....'"""
    m = re.search(rb'(?m)^%08x: ([0-9a-f]{8})\b' % address, output)
    if not m:
        raise RuntimeError('No md.l value for %08x' % address)
    return int(m.group(1), 16)


def parse_bootcmd(output):
    m = re.search(rb'(?m)^bootcmd=(.*?)\r?$', output)
    if not m:
        raise RuntimeError('bootcmd not printed')
    return m.group(1).decode()


def ppu_state(value):
    return PPU_STATE.get(value & PPU_STATE_MASK, 'unknown')


class Console:
    def __init__(self, fd, raw, open_ppu_bus=False):
        self.fd, self.raw = fd, raw
        self.open_ppu_bus = open_ppu_bus

    def run(self, line, quiet=1.0):
        if not command_allowed(line, self.open_ppu_bus):
            raise RuntimeError('Refusing non-allowlisted U-Boot command: ' + line)
        write_slow(self.fd, (line + '\n').encode())
        time.sleep(0.2)
        out = drain(self.fd, quiet, echo=False)
        self.raw.write(out)
        return out


def census(con):
    result = {}
    out = con.run('printenv bootcmd')
    result['bootcmd'] = parse_bootcmd(out)
    result['bootcmd_sha256'] = hashlib.sha256(result['bootcmd'].encode()).hexdigest()
    gate = parse_md(con.run('md.l 0x%08x 1' % R_CCU_PPU), R_CCU_PPU)
    result['r_ccu_ppu'] = '%08x' % gate
    result['ppu_bus_open'] = (gate & PPU_OPEN) == PPU_OPEN
    if result['ppu_bus_open']:
        for name, addr in (('ppu_tvfe', PPU_TVFE), ('ppu_tvcap', PPU_TVCAP)):
            value = parse_md(con.run('md.l 0x%08x 1' % addr), addr)
            result[name] = '%08x' % value
            result[name + '_state'] = ppu_state(value)
    else:
        result['ppu_tvfe'] = result['ppu_tvcap'] = None
        result['ppu_skipped'] = 'bus-r-ppu gate/reset not open; PPU not read'
    return result


def observe_warm_ppu(con, result, checkpoint):
    """Explicit diagnostic mutation; never power a TV domain or start MIPS.

    Caller must have checked the expected production bootcmd. Checkpoints
    persist intent before the write, including when its readback fails.
    """
    if result['r_ccu_ppu'] != '00000000':
        raise RuntimeError('PPU diagnostic requires the recorded closed-bus baseline 0')
    for name, addr in (('probe_gp6', GP6), ('probe_mips_status', MIPS_STATUS)):
        result[name] = '%08x' % parse_md(con.run('md.l 0x%08x 1' % addr), addr)
    if result['probe_gp6'] != '48444d49' or result['probe_mips_status'] != '00000000':
        raise RuntimeError('PPU diagnostic requires the production GP6 latch and parked MIPS')
    result['ppu_probe'] = {'write': OPEN_PPU_COMMAND, 'state': 'write-intent'}
    checkpoint()
    con.run(OPEN_PPU_COMMAND)
    gate = parse_md(con.run('md.l 0x%08x 1' % R_CCU_PPU), R_CCU_PPU)
    result['ppu_probe']['r_ccu_ppu_after'] = '%08x' % gate
    result['ppu_probe']['state'] = 'gate-readback'
    checkpoint()
    if gate != PPU_OPEN:
        raise RuntimeError('PPU bus readback differs; no PPU read or boot allowed')
    for name, addr in (('ppu_tvfe', PPU_TVFE), ('ppu_tvcap', PPU_TVCAP)):
        value = parse_md(con.run('md.l 0x%08x 1' % addr), addr)
        result['ppu_probe'][name] = '%08x' % value
        result['ppu_probe'][name + '_state'] = ppu_state(value)
        checkpoint()
    result['ppu_probe']['state'] = 'complete-stopped-at-prompt'
    checkpoint()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--label', required=True, help='e.g. cold-preboot, warm-preboot')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--record-bootcmd', type=Path)
    group.add_argument('--expected-bootcmd', type=Path)
    parser.add_argument('--boot', action='store_true', help='send `boot` after the census')
    parser.add_argument('--open-ppu-bus', action='store_true',
                        help='diagnostic: open only bus-r-ppu, read domains, stop at prompt; requires --expected-bootcmd, forbids --boot')
    args = parser.parse_args()
    if args.open_ppu_bus and (args.boot or not args.expected_bootcmd):
        parser.error('--open-ppu-bus requires --expected-bootcmd and forbids --boot')
    args.output.mkdir(parents=True, exist_ok=False)
    fd = open_port(args.port)
    try:
        with (args.output / 'serial.log').open('xb', buffering=0) as raw:
            write_slow(fd, b'\n')
            first = drain(fd, 1, echo=False)
            raw.write(first)
            if not re.search(rb'=>\s*$', first):
                raise RuntimeError('Not at U-Boot prompt; nothing sent')
            con = Console(fd, raw, args.open_ppu_bus)
            result = census(con)
            result['label'] = args.label
            if args.record_bootcmd:
                args.record_bootcmd.write_text(result['bootcmd'] + '\n')
            else:
                expected = args.expected_bootcmd.read_text().rstrip('\n')
                if expected != result['bootcmd']:
                    result['bootcmd_mismatch'] = True
                    (args.output / 'census.json').write_text(json.dumps(result, indent=2) + '\n')
                    raise RuntimeError('bootcmd differs from the recorded cold value; not booting')
            (args.output / 'census.json').write_text(json.dumps(result, indent=2) + '\n')
            if args.open_ppu_bus:
                def checkpoint():
                    (args.output / 'census.json').write_text(json.dumps(result, indent=2) + '\n')
                observe_warm_ppu(con, result, checkpoint)
            print(json.dumps(result, indent=2), flush=True)
            if args.boot:
                con.run('boot', quiet=3)
                print('boot sent', flush=True)
    finally:
        os.close(fd)


if __name__ == '__main__':
    main()
