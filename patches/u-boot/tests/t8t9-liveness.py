#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Prove t8/t9 are dead at every comm-trace hook site in the pinned firmware.

The comm-trace markers clobber t8 (trace base) and t9 (marker value). That is
only safe where no path from the hooked instruction reads t8/t9 before writing
them. A path ends safely at a write, a call (jal/jalr/bal: t-registers are
caller-saved) or `jr $ra`. Any read-before-write, an unknown indirect jump
other than a call/return, or an undecodable instruction is reported unsafe.

For a hook that replaces `jal X`, the slot runs X's entry with t8/t9 clobbered,
so X's entry is checked too. The trampoline itself re-executes the displaced
instruction after the marker, so the hooked instruction is analysed as part of
the path.

usage: t8t9-liveness.py display.bin h713_mips.c [--table NAME] [--regs 24,25]
"""
import argparse, re, struct, sys

BASE = 0x8b100000


def load_table(src, name):
    s = open(src).read()
    a = s.index(name + '[] = {')
    b = s.index('\n};', a)
    return [(int(x, 16), int(y, 16), int(z, 16)) for x, y, z in
            re.findall(r'\{\s*(0x[0-9a-f]+),\s*(0x[0-9a-f]+),\s*(0x[0-9a-f]+)\s*\}', s[a:b])]


def regs(w):
    """Return (reads, writes, kind, target) for one instruction word.

    kind: 'seq', 'branch' (cond, target), 'likely' (cond likely, target),
    'jump' (target), 'call', 'ret', 'ijump', 'unknown'.
    """
    op = w >> 26; rs = (w >> 21) & 31; rt = (w >> 16) & 31; rd = (w >> 11) & 31
    fn = w & 63; imm = w & 0xffff
    simm = imm - 0x10000 if imm & 0x8000 else imm
    if w == 0:
        return set(), set(), 'seq', None
    if op == 0:
        if fn in (0, 2, 3):          # sll srl sra
            return {rt}, {rd}, 'seq', None
        if fn in (4, 6, 7):          # sllv srlv srav
            return {rs, rt}, {rd}, 'seq', None
        if fn == 8:                  # jr
            return {rs}, set(), ('ret' if rs == 31 else 'ijump'), None
        if fn == 9:                  # jalr
            return {rs}, {rd}, 'call', None
        if fn in (0x0a, 0x0b):       # movz movn (reads rd too)
            return {rs, rt, rd}, {rd}, 'seq', None
        if fn in (0x0c, 0x0d, 0x0f):  # syscall break sync
            return set(), set(), 'seq', None
        if fn in (0x10, 0x12):       # mfhi mflo
            return set(), {rd}, 'seq', None
        if fn in (0x11, 0x13):       # mthi mtlo
            return {rs}, set(), 'seq', None
        if fn in (0x18, 0x19, 0x1a, 0x1b):  # mult multu div divu
            return {rs, rt}, set(), 'seq', None
        if 0x20 <= fn <= 0x2b:       # add..sltu
            return {rs, rt}, {rd}, 'seq', None
        if fn in (0x30, 0x31, 0x32, 0x33, 0x34, 0x36):  # traps
            return {rs, rt}, set(), 'seq', None
        return set(), set(), 'unknown', None
    if op == 1:                      # REGIMM
        if rt in (0, 1, 2, 3):
            return {rs}, set(), ('likely' if rt & 2 else 'branch'), simm
        if rt in (0x10, 0x11, 0x12, 0x13):  # bltzal bgezal(l)
            return {rs}, {31}, 'call', None
        return set(), set(), 'unknown', None
    if op in (2, 3):
        return set(), ({31} if op == 3 else set()), ('call' if op == 3 else 'jump'), (w & 0x3ffffff) << 2
    if op in (4, 5, 0x14, 0x15):     # beq bne beql bnel
        if op == 4 and rs == 0 and rt == 0:
            return set(), set(), 'jump_rel', simm
        return {rs, rt}, set(), ('likely' if op >= 0x14 else 'branch'), simm
    if op in (6, 7, 0x16, 0x17):     # blez bgtz (likely)
        return {rs}, set(), ('likely' if op >= 0x16 else 'branch'), simm
    if 8 <= op <= 0x0e:              # addi addiu slti sltiu andi ori xori
        return {rs}, {rt}, 'seq', None
    if op == 0x0f:                   # lui
        return set(), {rt}, 'seq', None
    if op == 0x10:                   # COP0
        if rs == 0:  return set(), {rt}, 'seq', None      # mfc0
        if rs == 4:  return {rt}, set(), 'seq', None      # mtc0
        if rs == 0x0b: return set(), {rt}, 'seq', None    # di/ei
        if rs == 0x10: return set(), set(), 'seq', None   # eret/ehb/wait etc
        return set(), set(), 'unknown', None
    if op == 0x1c:                   # SPECIAL2
        if fn == 2:  return {rs, rt}, {rd}, 'seq', None   # mul
        if fn in (0, 1, 4, 5): return {rs, rt}, set(), 'seq', None  # madd(u) msub(u)
        if fn in (0x20, 0x21): return {rs}, {rd}, 'seq', None  # clz clo
        return set(), set(), 'unknown', None
    if op == 0x1f:                   # SPECIAL3
        if fn == 0:  return {rs}, {rt}, 'seq', None       # ext
        if fn == 4:  return {rs, rt}, {rt}, 'seq', None   # ins
        if fn == 0x20: return {rt}, {rd}, 'seq', None     # bshfl: seb seh wsbh
        if fn == 0x3b: return set(), {rt}, 'seq', None    # rdhwr
        return set(), set(), 'unknown', None
    if 0x20 <= op <= 0x26 or op == 0x30:  # loads, ll
        return {rs}, {rt}, 'seq', None
    if 0x28 <= op <= 0x2e:           # stores
        return {rs, rt}, set(), 'seq', None
    if op == 0x38:                   # sc
        return {rs, rt}, {rt}, 'seq', None
    if op in (0x2f, 0x33):           # cache pref
        return {rs}, set(), 'seq', None
    return set(), set(), 'unknown', None


class Analyzer:
    def __init__(self, image, watch, overrides):
        self.b = image; self.watch = frozenset(watch); self.over = overrides

    def word(self, a):
        if a in self.over:
            return self.over[a]
        return struct.unpack_from('<I', self.b, a - BASE)[0]

    def live(self, start, budget=4000):
        """Return None if all watched regs are dead at start, else a reason."""
        seen = {}
        work = [(start, self.watch)]
        steps = 0
        while work:
            pc, live_set = work.pop()
            if not live_set:
                continue
            key = (pc, live_set)
            if key in seen:
                continue
            seen[key] = True
            steps += 1
            if steps > budget:
                return 'budget exhausted at %#x' % pc
            if not (BASE <= pc < BASE + len(self.b)):
                return 'left image at %#x' % pc
            w = self.word(pc)
            rd, wr, kind, tgt = regs(w)
            if kind == 'unknown':
                return 'undecoded %08x at %#x' % (w, pc)
            hit = rd & live_set
            if hit:
                return 'reads %s at %#x (%08x)' % (sorted(hit), pc, w)
            if kind == 'seq':
                work.append((pc + 4, live_set - wr))
                continue
            # control transfer: the delay slot executes first
            d = self.word(pc + 4)
            drd, dwr, dkind, _ = regs(d)
            if dkind not in ('seq',):
                return 'control op in delay slot at %#x' % (pc + 4)
            after = live_set - wr
            if kind == 'ret' or kind == 'call':
                if drd & after:
                    return 'delay slot reads %s at %#x' % (sorted(drd & after), pc + 4)
                continue                      # callee/caller clobber t-regs
            if kind == 'ijump':
                return 'indirect jump at %#x' % pc
            if kind == 'likely':
                # taken: delay executes; not taken: delay annulled
                if drd & after:
                    return 'delay slot reads %s at %#x' % (sorted(drd & after), pc + 4)
                work.append((pc + 4 + (tgt << 2), after - dwr))
                work.append((pc + 8, after))
                continue
            if drd & after:
                return 'delay slot reads %s at %#x' % (sorted(drd & after), pc + 4)
            after2 = after - dwr
            if kind == 'branch':
                work.append((pc + 4 + (tgt << 2), after2))
                work.append((pc + 8, after2))
            elif kind == 'jump_rel':
                work.append((pc + 4 + (tgt << 2), after2))
            elif kind == 'jump':
                work.append((((pc + 4) & 0xf0000000) | tgt, after2))
        return None


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('image'); p.add_argument('source')
    p.add_argument('--table', default='h713_mips_comm_trace_patches')
    p.add_argument('--regs', default='24,25')
    p.add_argument('--k0-only', action='store_true', help='only sites whose slot starts with lui k0')
    a = p.parse_args()
    img = open(a.image, 'rb').read()
    table = load_table(a.source, a.table)
    rep = {addr + 0x40000000: r for addr, e, r in table}
    exp = {addr + 0x40000000: e for addr, e, r in table}
    an = Analyzer(img, [int(x) for x in a.regs.split(',')], {})
    bad = 0; n = 0
    for addr, e, r in table:
        site = addr + 0x40000000
        if e == 0 or (r >> 26) not in (2, 3):
            continue
        slot = ((site + 4) & 0xf0000000) | ((r & 0x3ffffff) << 2)
        slot_first = rep.get(slot)
        is_k0 = slot_first is not None and slot_first >> 26 == 0x0f and ((slot_first >> 16) & 31) == 26
        if a.k0_only and not is_k0:
            continue
        n += 1
        reasons = []
        why = an.live(site)
        if why: reasons.append('site: ' + why)
        if (e >> 26) == 3:   # displaced jal X: X entry runs after the marker
            x = ((site + 4) & 0xf0000000) | ((e & 0x3ffffff) << 2)
            why = an.live(x)
            if why: reasons.append('callee %#x: %s' % (x, why))
        state = 'UNSAFE' if reasons else 'dead'
        bad += bool(reasons)
        print('%s site %#x (%08x) slot %#x %s %s' % (state, site, e, slot, 'k0' if is_k0 else '  ', '; '.join(reasons)))
    print('%d sites, %d unsafe' % (n, bad))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
