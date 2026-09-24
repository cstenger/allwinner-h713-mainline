#!/usr/bin/env python3
"""Read the board-B MIPS HDMI port objects without calling firmware or MMIO.

Run on the projector as root after the MIPS firmware has been started in
U-Boot. Only the MIPS DRAM carveout is mapped. A null or unexpected pointer
ends the probe before following it. This does not establish video lock.
"""

import ctypes
import json
import mmap
import os
import sys

ROOT_PHYS = 0x4BAC1A70
MIPS_LO = 0x8B100000
MIPS_HI = 0x8D961000
PHYS_DELTA = 0x40000000
PAGE = 0x1000
MANAGER_VPTR = 0x8B201D24
HDMI_VPTR = 0x8B1F5390


def checked_phys(mips_addr, size=4):
    if mips_addr % 4 or not MIPS_LO <= mips_addr <= MIPS_HI - size:
        raise ValueError(f"pointer outside aligned MIPS DRAM: {mips_addr:#010x}")
    return mips_addr - 0x80000000 + PHYS_DELTA


class ReadOnlyMem:
    def __init__(self):
        # ctypes.from_buffer requires a writable mmap, as in mips-shell.py.
        # This class exposes loads only and never stores to the mapping.
        self.fd = os.open('/dev/mem', os.O_RDWR | os.O_SYNC)
        self.maps = {}

    def word(self, phys):
        if phys % 4 or not 0x4B100000 <= phys <= 0x4D960FFC:
            raise ValueError(f"address outside aligned MIPS DRAM: {phys:#010x}")
        base = phys & ~(PAGE - 1)
        if base not in self.maps:
            page = mmap.mmap(self.fd, PAGE, mmap.MAP_SHARED,
                             mmap.PROT_READ | mmap.PROT_WRITE,
                             offset=base)
            self.maps[base] = (page, (ctypes.c_uint32 * (PAGE // 4)).from_buffer(page))
        return self.maps[base][1][(phys - base) // 4]

    def mips_word(self, mips_addr):
        return self.word(checked_phys(mips_addr))

    def mips_byte(self, mips_addr):
        aligned = mips_addr & ~3
        return (self.mips_word(aligned) >> ((mips_addr & 3) * 8)) & 0xFF


def snapshot(mem):
    manager = mem.word(ROOT_PHYS)
    if not manager:
        return {'manager': None, 'reason': 'MIPS device manager absent'}
    if mem.mips_word(manager) != MANAGER_VPTR:
        raise ValueError(f"device manager {manager:#010x} has unexpected vptr")
    # Manager constructor 0x8b1839ac stores the real THDMIRx at +0x18;
    # +0x1c is THDMIDummy and must never be mistaken for the receiver.
    hdmi = mem.mips_word(manager + 0x18)
    if not hdmi:
        return {'manager': f'{manager:#010x}', 'hdmi': None}
    if mem.mips_word(hdmi) != HDMI_VPTR:
        raise ValueError(f"HDMI device {hdmi:#010x} has unexpected vptr")
    result = {'manager': f'{manager:#010x}', 'hdmi': f'{hdmi:#010x}', 'ports': []}
    for index in range(3):
        port = mem.mips_word(hdmi + 0xEC + 4 * index)
        if not port:
            result['ports'].append({'index': index + 1, 'object': None})
            continue
        checked_phys(port, 0x534)
        port_id = mem.mips_byte(port + 0x51B)
        link_base = mem.mips_word(port + 0x520)
        if port_id != index + 1 or link_base != 0x06840000:
            raise ValueError(f"port {index + 1} has unexpected identity or link base")
        result['ports'].append({
            'index': index + 1,
            'object': f'{port:#010x}',
            'port_id': port_id,
            'state': mem.mips_word(port + 0xC0),
            'freq_event_pending': mem.mips_byte(port + 0x68),
            'cached_count': mem.mips_word(port + 0x6C),
            'link_base': f'{link_base:#010x}',
        })
    return result


if __name__ == '__main__':
    try:
        print(json.dumps(snapshot(ReadOnlyMem()), sort_keys=True))
    except (OSError, ValueError) as exc:
        print(f'MIPS_PORT_CACHE_ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
