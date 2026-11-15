#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Bench diagnostic: make the display firmware's fatal-exception dump survivable.

Pinned firmware (display.bin SHA-256 4380f1b3...). Every general exception
enters the "Display Dump" handler 0x8b15bd28, whose register saver 0x8b15bbd8
stores BadVAddr with a misaligned `sw $k1, 0x8a($k0)` (0x8b15bc70). That
store faults, re-enters the handler and recurses forever; the runaway stack
writes {0x8baa0000, 0x8b15bd44} every 32 bytes down through physical DRAM.

Two in-RAM instruction changes, written through /dev/mem into the no-map
firmware reservation after boot (a reboot reloads the pristine image):

  0x8b15bc70  sw  $k1, 0x8a($k0)  -> sw  $k1, 0x94($k0)   aligned free slot
  0x8b15bbd8  lui $a1, 0x8baa     -> lui $a1, 0xabaa      uncached save area

The firmware then parks in its own `b .` after a fatal exception, and the
saved GPRs, Status, Cause, EPC and BadVAddr are in DRAM at ARM 0x4ba99dc8.
Both sites are reachable only from the fatal handlers (0x8b15bd28 and the
cache-error path 0x8b15bde4), so the MIPS I-cache cannot hold stale copies.

  --check     verify the original words (default; no writes)
  --apply     verify, patch, read back
  --restore   write the original words back
  --read      decode the save area (works patched or not)
  --image F   run --check against a display.bin file instead
"""
import argparse, json, mmap, os, struct, sys

MIPS_TO_ARM = 0x40000000            # kseg0 0x8bxxxxxx -> ARM 0x4bxxxxxx
SITES = (  # MIPS address, original word, patched word
    (0x8b15bc70, 0xaf5b008a, 0xaf5b0094),
    (0x8b15bbd8, 0x3c058baa, 0x3c05abaa),
)
# Neighbouring words that must match the pinned image before any write.
GUARDS = ((0x8b15bc6c, 0x401b4000), (0x8b15bc74, 0x3c026372),
          (0x8b15bbdc, 0x24a59dc8), (0x8b15bbe0, 0x00a0d025),
          (0x8b101180, 0x0ac56f4a), (0x8b15bd3c, 0x0ec56ef6))
SAVE = 0x8ba99dc8
SAVE_LEN = 0x98
NAMES = {0x00: 'magic0', 0x04: 'magic1', 0x08: 'v0', 0x0c: 'v1', 0x10: 'a0', 0x14: 'a1',
         0x18: 'a2', 0x1c: 'a3', 0x20: 't0', 0x24: 't1', 0x28: 't2', 0x2c: 't3',
         0x30: 't4', 0x34: 't5', 0x38: 't6', 0x3c: 't7', 0x40: 't8', 0x44: 't9',
         0x48: 's0', 0x4c: 's1', 0x50: 's2', 0x54: 's3', 0x58: 's4', 0x5c: 's5',
         0x60: 's6', 0x64: 's7', 0x70: 'gp', 0x74: 'sp', 0x78: 'fp', 0x7c: 'ra',
         0x80: 'status', 0x84: 'cause', 0x88: 'epc', 0x8c: 'magic0_copy',
         0x90: 'magic1_copy', 0x94: 'badvaddr'}
EXC = {0: 'Int', 1: 'Mod', 2: 'TLBL', 3: 'TLBS', 4: 'AdEL', 5: 'AdES', 6: 'IBE', 7: 'DBE',
       8: 'Sys', 9: 'Bp', 10: 'RI', 11: 'CpU', 12: 'Ov', 13: 'Tr', 23: 'WATCH', 24: 'MCheck'}


class DevMem:
    def __init__(self, write=False):
        self.fd = os.open('/dev/mem', (os.O_RDWR if write else os.O_RDONLY) | os.O_SYNC)
        self.write = write
        self.maps = {}

    def _page(self, arm):
        base = arm & ~0xfff
        if base not in self.maps:
            prot = mmap.PROT_READ | (mmap.PROT_WRITE if self.write else 0)
            self.maps[base] = mmap.mmap(self.fd, 0x1000, mmap.MAP_SHARED, prot, offset=base)
        return self.maps[base], arm - base

    def u32(self, mips):
        m, off = self._page(mips - MIPS_TO_ARM)
        return struct.unpack_from('<I', m, off)[0]

    def put(self, mips, value):
        m, off = self._page(mips - MIPS_TO_ARM)
        struct.pack_into('<I', m, off, value)


class Image:
    def __init__(self, path):
        self.b = open(path, 'rb').read()

    def u32(self, mips):
        return struct.unpack_from('<I', self.b, mips - 0x8b100000)[0]


def state(mem):
    for addr, want in GUARDS:
        got = mem.u32(addr)
        if got != want:
            raise SystemExit('guard %#x is %#010x, expected %#010x: not the pinned firmware' % (addr, got, want))
    kinds = []
    for addr, old, new in SITES:
        got = mem.u32(addr)
        kinds.append('original' if got == old else 'patched' if got == new else 'foreign')
        if kinds[-1] == 'foreign':
            raise SystemExit('site %#x holds %#010x, neither original nor patched' % (addr, got))
    if len(set(kinds)) != 1:
        raise SystemExit('sites disagree: %s' % kinds)
    return kinds[0]


def decode(mem):
    words = {off: mem.u32(SAVE + off) for off in range(0, SAVE_LEN, 4)}
    out = {NAMES.get(o, '+%#x' % o): '%#010x' % v for o, v in words.items()}
    cause = words[0x84]
    out['decoded'] = {
        'magic_ok': words[0] == 0x63726173 and words[4] == 0x68726567,
        'exccode': EXC.get((cause >> 2) & 0x1f, (cause >> 2) & 0x1f),
        'branch_delay': bool(cause >> 31),
        'pending_ip': '%#04x' % ((cause >> 8) & 0xff),
        'status_exl_erl_ie': [(words[0x80] >> 1) & 1, (words[0x80] >> 2) & 1, words[0x80] & 1],
    }
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group()
    for a in ('check', 'apply', 'restore', 'read'):
        g.add_argument('--'+a, action='store_true')
    p.add_argument('--image', help='display.bin file to check/read instead of /dev/mem')
    a = p.parse_args()
    if a.image:
        if a.apply or a.restore or a.read:
            raise SystemExit('--image supports --check only (the save area is runtime memory)')
        print(json.dumps({'state': state(Image(a.image))}, indent=1))
        return
    mem = DevMem(write=a.apply or a.restore)
    if a.read:
        print(json.dumps({'state': state(mem), 'save_area': decode(mem)}, indent=1))
        return
    now = state(mem)
    if a.apply or a.restore:
        want = 'patched' if a.apply else 'original'
        if now != want:
            for addr, old, new in SITES:
                mem.put(addr, new if a.apply else old)
            now = state(mem)
            if now != want:
                raise SystemExit('readback is %s, expected %s' % (now, want))
    print(json.dumps({'state': now, 'sites': {'%#x' % s: '%#010x' % mem.u32(s) for s, _, _ in SITES}}))


if __name__ == '__main__':
    main()
