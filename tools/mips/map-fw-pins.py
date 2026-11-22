#!/usr/bin/env python3
"""Map pinned A1 display.bin addresses onto another build by matching code.

The A1 firmware (SHA-256 4380f1b3...) and the native V2 firmware
(16c74a28...) are the same source relinked: code slides by a few hundred
bytes and globals move by a different amount. A pinned address therefore has
to be re-derived, and a string offset or a constant delta is not proof. This
tool matches the code that *uses* each pin and reads the answer off the
matched code:

  global   every A1 instruction that forms the address (lui + lo pair, folded
           by disasm.fold_address_pairs) is located in the other build by its
           surrounding code, and the address formed by the matching
           instruction there is read back. All references must agree.
  routine  every A1 `jal ROUTINE` is located the same way and the jal target
           at the matching instruction is read back; the routine body itself
           must then be identical.

Windows are compared with relocation-sensitive fields masked: jal targets, lui
immediates and the low half of a folded address. Struct offsets, register
choices and everything else must match. A reference is accepted only when its
best match is unique and scores well above the runner-up.

    tools/mips/map-fw-pins.py A1.bin V2.bin --cpu-comm
    tools/mips/map-fw-pins.py A1.bin V2.bin --global 8b22efe4 --routine 8b1227b4
"""
import argparse
import hashlib
import os
import sys

import numpy as np
from capstone import CS_ARCH_MIPS, CS_MODE_32, CS_MODE_LITTLE_ENDIAN, Cs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "disasm", os.path.join(os.path.dirname(os.path.abspath(__file__)), "disasm.py"))
disasm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(disasm)

BASE = disasm.BASE
HALF = 24          # words each side of a reference
MIN_SCORE = 0.85   # fraction of the window that must match exactly
MIN_MARGIN = 0.15  # lead over the second-best window

# The pins cc_discover_channel() and the elog-control readout in kernel 0014
# depend on (A1 addresses).
CPU_COMM_GLOBALS = {
    0x8B22EFE4: "pcpu_comm_dev pointer (channel table base)",
    0x8B48BE9B: "elog mode byte",
    0x8B48C2AD: "elog mode-2 enable byte",
    0x8B48C2B8: "elog mode-2 write pointer",
}
CPU_COMM_ROUTINES = {
    0x8B1227B4: "getCurCPUID (reader self-test)",
}


class Image:
    def __init__(self, path):
        with open(path, "rb") as handle:
            self.data = handle.read()
        self.sha = hashlib.sha256(self.data).hexdigest()
        n = len(self.data) // 4
        self.words = np.frombuffer(self.data[:n * 4], dtype="<u4").copy()
        self.formed = {}   # VA -> address formed by this instruction
        self.lui = set()   # VAs of lui instructions
        md = Cs(CS_ARCH_MIPS, CS_MODE_32 | CS_MODE_LITTLE_ENDIAN)
        md.skipdata = True
        insns = [i for i in md.disasm(self.data, BASE) if i.size == 4]
        # fold in chunks so a skipdata gap cannot carry a register value
        self.formed = disasm.fold_address_pairs(insns)
        self.lui = {i.address for i in insns if i.mnemonic == "lui"}
        self.norm = self.words.copy()
        op = self.words >> 26
        self.norm[op == 3] &= 0xFC000000                 # jal target
        idx = np.array(sorted(self.lui | set(self.formed)), dtype=np.int64)
        idx = (idx - BASE) // 4
        self.norm[idx] &= 0xFFFF0000                     # lui / folded lo

    def va(self, index):
        return BASE + 4 * int(index)

    def index(self, va):
        return (va - BASE) // 4


def best_match(a, b, a_index):
    """Return [(score, b_index)] for the two best windows around a_index."""
    lo = a_index - HALF
    win = a.norm[lo:lo + 2 * HALF + 1]
    n = len(b.norm) - len(win) + 1
    score = np.zeros(n, dtype=np.int32)
    for k, word in enumerate(win):
        score += b.norm[k:k + n] == word
    order = np.argsort(score)[::-1]
    best = order[0]
    # runner-up must be a different place, not the same window shifted by one
    second = next(i for i in order[1:] if abs(int(i) - int(best)) > 2)
    return [(score[best] / len(win), best + HALF),
            (score[second] / len(win), second + HALF)]


def accept(ranked):
    (s1, _), (s2, _) = ranked
    return s1 >= MIN_SCORE and s1 - s2 >= MIN_MARGIN


def map_global(a, b, addr):
    refs = sorted(va for va, formed in a.formed.items() if formed == addr)
    answers, rows = set(), []
    for va in refs:
        ranked = best_match(a, b, a.index(va))
        (s1, bi), (s2, _) = ranked
        got = b.formed.get(b.va(bi))
        ok = accept(ranked) and got is not None
        rows.append((va, b.va(bi), s1, s2, got, ok))
        if ok:
            answers.add(got)
    return refs, rows, answers


def map_routine(a, b, addr):
    jal = 0x0C000000 | ((addr >> 2) & 0x03FFFFFF)
    refs = [a.va(i) for i in np.nonzero(a.words == jal)[0]]
    answers, rows = set(), []
    for va in refs:
        ranked = best_match(a, b, a.index(va))
        (s1, bi), (s2, _) = ranked
        word = int(b.words[bi])
        got = None
        if word >> 26 == 3:
            got = (b.va(bi) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)
        ok = accept(ranked) and got is not None
        rows.append((va, b.va(bi), s1, s2, got, ok))
        if ok:
            answers.add(got)
    return refs, rows, answers


def body_equal(a, b, a_va, b_va, words=2):
    ai, bi = a.index(a_va), b.index(b_va)
    return (a.words[ai:ai + words] == b.words[bi:bi + words]).all()


def report(kind, name, addr, refs, rows, answers, a, b):
    print(f"\n{kind} {addr:#010x}  {name}")
    print(f"  {len(refs)} A1 reference(s)")
    for va, bva, s1, s2, got, ok in rows:
        g = f"{got:#010x}" if got is not None else "-"
        print(f"    A1 {va:#010x} -> {bva:#010x}  score {s1:.2f} "
              f"(next {s2:.2f})  forms {g}  {'ok' if ok else 'REJECTED'}")
    accepted = sum(r[5] for r in rows)
    if len(answers) == 1 and accepted:
        result = answers.pop()
        print(f"  => {result:#010x}  ({accepted}/{len(rows)} references "
              f"agree, delta {result - addr:+#x})")
        return result
    print(f"  => NO UNIQUE ANSWER {sorted(hex(x) for x in answers)}")
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("a1", help="reference image (A1 display.bin)")
    ap.add_argument("other", help="image to map onto (e.g. V2 display.bin)")
    ap.add_argument("--global", dest="globals", action="append", default=[],
                    type=lambda s: int(s, 16), help="A1 global address (hex)")
    ap.add_argument("--routine", action="append", default=[],
                    type=lambda s: int(s, 16), help="A1 routine address (hex)")
    ap.add_argument("--cpu-comm", action="store_true",
                    help="map the pins used by kernel cpu_comm discovery")
    args = ap.parse_args()

    globals_ = {g: "" for g in args.globals}
    routines = {r: "" for r in args.routine}
    if args.cpu_comm:
        globals_.update(CPU_COMM_GLOBALS)
        routines.update(CPU_COMM_ROUTINES)
    if not globals_ and not routines:
        ap.error("nothing to map")

    a, b = Image(args.a1), Image(args.other)
    print(f"A1    {args.a1}  sha256 {a.sha[:8]}")
    print(f"other {args.other}  sha256 {b.sha[:8]}")

    failed = False
    for addr, name in routines.items():
        result = report("routine", name, addr, *map_routine(a, b, addr), a, b)
        if result is None:
            failed = True
            continue
        same = body_equal(a, b, addr, result)
        ai, bi = a.index(addr), b.index(result)
        print(f"  body A1 {a.words[ai]:08x} {a.words[ai + 1]:08x}  "
              f"other {b.words[bi]:08x} {b.words[bi + 1]:08x}  "
              f"{'identical' if same else 'DIFFERENT'}")
        failed |= not same
    for addr, name in globals_.items():
        result = report("global", name, addr, *map_global(a, b, addr), a, b)
        failed |= result is None
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
