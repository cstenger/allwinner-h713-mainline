#!/usr/bin/env python3
"""Exercise generated MIPS instructions, including branch delay slots."""
import importlib.util
from pathlib import Path
import random

spec = importlib.util.spec_from_file_location(
    "audio_trace", Path(__file__).with_name("make-audio-dispatch-trace.py"))
dispatch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dispatch)
trace = dispatch.monitor


def run_case(current, previous, seed, trace=trace, padding_word=26):
    rng = random.Random(seed)
    regs = [0] + [rng.getrandbits(32) for _ in range(31)]
    regs[2], regs[3] = current, previous
    regs[16], regs[17], regs[20], regs[29] = (
        0x8B831470, 0x8B8314E8, 0x06880000, 0x8BC00000)
    before = regs.copy()
    n, fs = rng.choice([0, 6144]), rng.choice([0, 48000])
    mem = {regs[17] + 4: n, regs[17] + 8: fs,
           trace.MAILBOX + 0x100: 41, trace.MAILBOX + 0x104: 7,
           trace.MAILBOX + 0x110: 333, trace.MAILBOX + 0x114: 444}
    code = {a + 0x40000000: w for a, _, w in trace.monitor_records()}
    code[0x8B13A2F8] = 0x26050078  # original hook's delay slot
    accesses = []

    def execute(pc):
        word = code[pc]
        op, rs, rt = word >> 26, (word >> 21) & 31, (word >> 16) & 31
        imm = word & 0xFFFF
        signed = imm if imm < 0x8000 else imm - 0x10000
        target = None
        if word == 0:
            pass
        elif op == 9:
            regs[rt] = (regs[rs] + signed) & 0xFFFFFFFF
        elif op == 15:
            regs[rt] = imm << 16
        elif op in (35, 43):
            addr = (regs[rs] + signed) & 0xFFFFFFFF
            accesses.append((op, addr))
            assert addr % 4 == 0
            assert (0x8B100000 <= addr < 0x8D961000 or
                    trace.MAILBOX <= addr < trace.MAILBOX + 0x1000)
            if op == 35:
                regs[rt] = mem[addr]
            else:
                mem[addr] = regs[rt]
        elif op == 4:
            target = pc + 4 + signed * 4 if regs[rs] == regs[rt] else pc + 8
        elif op == 2:
            target = ((pc + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)
        else:
            raise AssertionError(f"unexpected instruction {word:08x}")
        regs[0] = 0
        return target

    pc = 0x8B13A2F4
    visited = []
    for _ in range(50):
        if pc in (0x8B13A2FC, 0x8B13A31C):
            break
        visited.append(pc)
        target = execute(pc)
        if target is not None:
            assert execute(pc + 4) is None, "branch in a delay slot"
            pc = target
        else:
            pc += 4
    else:
        raise AssertionError("trampoline did not return")
    assert pc == (0x8B13A31C if current == previous else 0x8B13A2FC)
    expected = before.copy()
    expected[5] = (before[16] + 0x78) & 0xFFFFFFFF
    assert regs == expected, "register or stack corruption"
    assert mem[trace.MAILBOX + 0x110] == (n if current != previous else 333)
    assert mem[trace.MAILBOX + 0x114] == (fs if current != previous else 444)
    assert mem[trace.MAILBOX + 0x100] == 42
    assert mem[trace.MAILBOX + 0x104] == 7 + (current != previous)
    for field, value in {
        "current_status": current, "previous_status": previous,
        "n": n, "sample_rate_hz": fs, "audio_object": before[17],
    }.items():
        if field in trace.FIELDS:
            assert mem[trace.MAILBOX + trace.FIELDS[field]] == value
    assert all(not trace.MAILBOX + 0x80 <= addr < trace.MAILBOX + 0x84
               for _, addr in accesses)
    assert not any(trace.CAVE + padding_word * 4 <= p < trace.CAVE + 40 * 4 for p in visited)


def main():
    records = trace.monitor_records()
    assert len(records) == 42
    assert len({a for a, _, _ in records}) == 42
    assert trace.cap.census(records) == (7, 7)
    for seed in range(100):
        for current, previous in [(0, 0), (16, 16), (16, 0), (0, 16), (240, 32)]:
            run_case(current, previous, seed)
    print("PASS: 500 dispatch-latch paths; registers, stack, delay slots, counters, DRAM-only accesses")
    assert (0x4B180128, 0x0AC56CC1, 0x0AC56CD2) in records


if __name__ == "__main__":
    main()
