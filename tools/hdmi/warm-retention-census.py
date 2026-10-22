#!/usr/bin/env python3
"""Read-only Linux census for the warm-retention test. Writes nothing.

Stream it over SSH:  ssh root@board 'python3 - LABEL' < warm-retention-census.py
Design: docs/hdmi-warm-retention-test-design-2026-10-21.md (set L).

Every MMIO read goes through `busybox devmem ADDR 32` (a single 32-bit
access) and is gated on the state that makes it safe:
- PPU status only after R_CCU bus-r-ppu (0x070101ac) shows gate and reset open;
- TVTOP +0x00/+0x04/+0x84/+0x88 only when +0x40 reads exactly the routed
  0x00011111 (+0x40/+0x44/+0x80 are read-modify-written by SPL every boot);
- AudioTop and DSP status only with both TV PPU domains ON;
- lock words only with TVTOP +0x40 = 0x00011111 (routed), never written.
Never touches CPUS/ARISC (0x07091xxx), DSP command ports or the lock writes.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

R_CCU_PPU = 0x070101ac
PPU_TVFE, PPU_TVCAP = 0x070010a4, 0x07001124
MIPS_STATUS = 0x0306101c
TVTOP = 0x05700000
TVTOP_SPL = (0x40, 0x44, 0x80)
TVTOP_ROUTED_ONLY = (0x00, 0x04, 0x84, 0x88)
TVTOP_ROUTED_40 = 0x00011111
AUDIOTOP, DSP_STATUS = 0x0614a000, 0x06144000
LOCK_PEER, LOCK_OWN = 0x05001530, 0x05001534
PPU_ON = 0x10000
FORBIDDEN = ((0x07090000, 0x070a0000),)  # CPUS/ARISC window


class Board:
    def run(self, argv):
        return subprocess.run(argv, capture_output=True, text=True, check=False).stdout

    def devmem(self, address):
        for lo, hi in FORBIDDEN:
            if lo <= address < hi:
                raise RuntimeError('refusing forbidden address %08x' % address)
        out = subprocess.run(['busybox', 'devmem', '0x%08x' % address, '32'],
                             capture_output=True, text=True, check=True).stdout
        return int(out.strip(), 16)

    def read(self, path):
        try:
            return Path(path).read_text()
        except OSError:
            return None


def census(board, label):
    reads = {}
    def rd(name, address):
        reads[name] = '%08x' % board.devmem(address)
        return int(reads[name], 16)
    r = {'label': label, 'time': time.time(), 'reads': reads, 'skipped': []}
    r['boot_id'] = (board.read('/proc/sys/kernel/random/boot_id') or '').strip()
    r['hdmi_handoff'] = board.read('/proc/device-tree/chosen/h713,hdmi-boot-v1') is not None
    r['units'] = {u: board.run(['systemctl', 'show', 'h713-hdmi-%s.service' % u, '-p',
                                'ActiveState', '--value']).strip()
                  for u in ('capture', 'signal', 'speaker')}
    r['dsp_journal'] = [l for l in board.run(['journalctl', '-k', '-b', '--no-pager', '-o', 'short-monotonic']).splitlines()
                        if 'h713-hdmi-audio: DSP' in l or 'DSP patch verified' in l]
    r['h713_modules'] = sorted(l.split()[0] for l in (board.read('/proc/modules') or '').splitlines()
                               if l.startswith('h713'))
    rd('mips_status', MIPS_STATUS)
    gate = rd('r_ccu_ppu', R_CCU_PPU)
    both_on = False
    if (gate & 0x10001) == 0x10001:
        tvfe = rd('ppu_tvfe', PPU_TVFE)
        tvcap = rd('ppu_tvcap', PPU_TVCAP)
        both_on = (tvfe & 0x30000) == PPU_ON and (tvcap & 0x30000) == PPU_ON
    else:
        r['skipped'].append('ppu: bus-r-ppu not open')
    for off in TVTOP_SPL:
        rd('tvtop_%02x' % off, TVTOP + off)
    routed = int(reads['tvtop_40'], 16) == TVTOP_ROUTED_40
    if routed:   # exactly the routed value; MIPS-live captures read these routinely
        for off in TVTOP_ROUTED_ONLY:
            rd('tvtop_%02x' % off, TVTOP + off)
    else:
        r['skipped'].append('tvtop 00/04/84/88: +0x40 not the routed value')
    if both_on:
        rd('audiotop_ctl', AUDIOTOP)
        rd('audiotop_cfg', AUDIOTOP + 0xc)
        rd('dsp_status', DSP_STATUS)
    else:
        r['skipped'].append('audiotop/dsp status: TV domains not both ON (or PPU unread)')
    if routed:
        rd('lock_peer', LOCK_PEER)
        rd('lock_own', LOCK_OWN)
    else:
        r['skipped'].append('lock words: TVTOP +0x40 not routed')
    r['tv_domains_both_on'] = both_on
    r['tvtop_routed'] = routed
    return r


if __name__ == '__main__':
    print(json.dumps(census(Board(), sys.argv[1] if len(sys.argv) > 1 else 'unlabelled'), indent=2))
