#!/usr/bin/env python3
"""Disassemble a window of the H713 MIPS display firmware.

The firmware is a raw little-endian MIPS32 image with no headers, so every
lookup is `file offset = VA - BASE`. BASE is the single fact this tool exists to
centralise: it is 0x8b100000.

That matters because it has already gone wrong once. A previous helper carried
0x8b101000 -- 4 KiB high -- and consequently disassembled unrelated code while
describing it as the registered CPU_COMM adapter, which is how a bogus
zero-argument ABI for THal_Vp_Init came to be believed. Anything that resolves
addresses in this image should go through here rather than recomputing the base.

The base is checkable, not assumed: the routines known to be stubs
(THal_Vp_SetImageBufferAddr at 0x8b10ada8, GetImageBufferAddr at 0x8b10adb0)
must disassemble as `jr ra; nop`, and routines known to be real must show a
genuine prologue. `--self-test` asserts exactly that.

    tools/mips/disasm.py FIRMWARE 8b109dc0 -n 40
    tools/mips/disasm.py FIRMWARE --self-test

lui/addiu and lui/lw pairs are folded into the absolute address they compute,
because in this codebase those pairs are how every global is reached and reading
them by hand is where transcription errors come from.
"""
import argparse
import sys

from capstone import CS_ARCH_MIPS, CS_MODE_32, CS_MODE_LITTLE_ENDIAN, Cs

BASE = 0x8B100000

# (VA, is_real_routine) -- see the module docstring. These are load-bearing
# controls, not documentation: a wrong BASE has to fail the self-test.
KNOWN = [
    (0x8B10ADA8, False),  # THal_Vp_SetImageBufferAddr -- stub
    (0x8B10ADB0, False),  # THal_Vp_GetImageBufferAddr -- stub
    (0x8B109D54, True),   # THal_Vp_Wce_SetWindow
    (0x8B109DC0, True),   # THal_Vp_Wce_GetWindow
    (0x8B109E2C, True),   # THal_Vp_Wce_GetActiveWindow
]


def parse_address(text):
    """Accept 8b109dc0, 0x8b109dc0 or a bare file offset below the base."""
    value = int(text, 16)
    return value if value >= BASE else value + BASE


def disassemble(image, va, count):
    offset = va - BASE
    if offset < 0 or offset >= len(image):
        sys.exit(f"VA {va:#x} is outside the image (offset {offset:#x})")
    md = Cs(CS_ARCH_MIPS, CS_MODE_32 | CS_MODE_LITTLE_ENDIAN)
    md.detail = True
    window = image[offset:offset + count * 4]
    return list(md.disasm(window, va))


def fold_address_pairs(instructions):
    """Annotate `lui rX, hi` + `<op> rY, lo(rX)` with the address it forms.

    MIPS has no 32-bit immediate, so every global access is a two-instruction
    pair. Reporting only the halves is how digits get transposed.

    Tracking must be *retired* as well as established. An earlier version only
    ever added to the known map, so a register that had held a lui value kept
    being credited with it after it was overwritten -- which printed confident,
    wrong addresses for `addiu $v0, $v1, imm` sequences where $v0 had a stale
    entry. A helper that emits plausible wrong addresses is worse than one that
    emits none, so every instruction now invalidates the registers it writes
    unless it is one of the two forms that propagate a known value.
    """
    notes = {}
    known = {}
    for insn in instructions:
        parts = [p.strip() for p in insn.op_str.split(",")]
        written = written_registers(insn, parts)

        if insn.mnemonic == "lui" and len(parts) == 2:
            try:
                known[parts[0]] = int(parts[1], 0) << 16
                continue
            except ValueError:
                pass
        elif insn.mnemonic == "addiu" and len(parts) == 3:
            # Propagates: rD becomes a known address if rS was one.
            try:
                value = known[parts[1]] + sign16(int(parts[2], 0))
            except (KeyError, ValueError):
                pass
            else:
                known[parts[0]] = value
                notes[insn.address] = value
                continue
        elif "(" in insn.op_str:
            body = insn.op_str.rsplit(",", 1)[-1].strip()
            imm, _, reg = body.partition("(")
            reg = reg.rstrip(")")
            if reg in known:
                try:
                    notes[insn.address] = known[reg] + sign16(int(imm, 0))
                except ValueError:
                    pass

        for reg in written:
            known.pop(reg, None)
    return notes


# capstone does not implement regs_access() for MIPS, so the destination has to
# come from the operand form. On MIPS the first operand is the destination for
# everything except stores, branches and jumps.
STORES = {"sw", "sh", "sb", "swl", "swr", "sc", "swc1", "sdc1"}
CALLER_SAVED = {"$v0", "$v1", "$a0", "$a1", "$a2", "$a3", "$ra",
                "$t0", "$t1", "$t2", "$t3", "$t4", "$t5", "$t6", "$t7",
                "$t8", "$t9", "$at"}


def written_registers(insn, parts):
    mnemonic = insn.mnemonic
    # A call clobbers every caller-saved register, so no value may be carried
    # across one. Being conservative here is the whole point of the pass.
    if mnemonic in ("jal", "jalr", "bal"):
        return set(CALLER_SAVED)
    if mnemonic in STORES or mnemonic.startswith(("b", "j")):
        return set()
    if parts and parts[0].startswith("$"):
        return {parts[0]}
    return set()


def sign16(value):
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def self_test(image):
    md = Cs(CS_ARCH_MIPS, CS_MODE_32 | CS_MODE_LITTLE_ENDIAN)
    failures = []
    for va, expect_real in KNOWN:
        head = list(md.disasm(image[va - BASE:va - BASE + 8], va))
        if len(head) < 2:
            failures.append(f"{va:#x}: did not decode")
            continue
        is_stub = head[0].mnemonic == "jr" and head[1].mnemonic == "nop"
        text = f"{head[0].mnemonic} {head[0].op_str}; {head[1].mnemonic}"
        status = "real" if not is_stub else "stub"
        want = "real" if expect_real else "stub"
        ok = status == want
        print(f"  {va:#010x}  {status:4}  expected {want:4}  "
              f"{'ok' if ok else 'MISMATCH'}   {text}")
        if not ok:
            failures.append(f"{va:#x}: got {status}, expected {want}")
    if failures:
        sys.exit("self-test FAILED -- base is wrong or the image is not the "
                 "one these notes describe:\n  " + "\n  ".join(failures))
    print("self-test passed: base 0x8b100000 discriminates stubs from real "
          "routines")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", help="raw firmware, e.g. display.bin")
    ap.add_argument("address", nargs="?", help="VA (hex) or file offset (hex)")
    ap.add_argument("-n", "--count", type=int, default=32,
                    help="instructions to decode (default 32)")
    ap.add_argument("--self-test", action="store_true",
                    help="verify the base against known stub/real routines")
    args = ap.parse_args()

    with open(args.image, "rb") as handle:
        image = handle.read()

    if args.self_test:
        self_test(image)
        return
    if not args.address:
        ap.error("address is required unless --self-test is given")

    va = parse_address(args.address)
    instructions = disassemble(image, va, args.count)
    notes = fold_address_pairs(instructions)
    for insn in instructions:
        raw = int.from_bytes(image[insn.address - BASE:insn.address - BASE + 4],
                             "little")
        note = notes.get(insn.address)
        suffix = f"        # -> {note:#010x}" if note is not None else ""
        print(f"{insn.address:#010x}  {raw:08x}  "
              f"{insn.mnemonic:<8} {insn.op_str}{suffix}")


if __name__ == "__main__":
    main()
