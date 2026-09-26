#!/usr/bin/env python3
"""Add the guarded VIncap trace to an installed H713 U-Boot proper image.

This is the narrow deployment form of the source implementation in
external/u-boot.  It replaces seven expendable CPU_COMM progress-marker patch
groups with an equal-size capture patch set.  The patch-table length and its
seven trace-base/seven counted-store relocation census remain unchanged, so no
executable U-Boot code, FIT metadata, SPL, BL31, DTB, or sector-tail byte moves.
The input and output are equally sized padded U-Boot-proper readbacks.
"""

import argparse
import hashlib
import json
import struct
from pathlib import Path


RECORD = struct.Struct("<QII")


def progress_group(cave, marker, target, hook, expected, replacement):
    return [
        (cave, 0, 0x3C1AAE34),
        (cave + 4, 0, 0x341B0000 | marker),
        (cave + 8, 0, 0xAF5B0000),
        (cave + 12, 0, target),
        (cave + 16, 0, 0),
        (hook, expected, replacement),
    ]


OLD_RECORDS = sum((
    progress_group(0x4B1004C0, 0xA002, 0x0AC54252,
                   0x4B118E5C, 0x0EC54252, 0x0EC40130),
    progress_group(0x4B1004E0, 0xA003, 0x0AC46097,
                   0x4B118E64, 0x0EC46097, 0x0EC40138),
    progress_group(0x4B100500, 0xA004, 0x0AC4610C,
                   0x4B118E9C, 0x0EC4610C, 0x0EC40140),
    progress_group(0x4B100520, 0xA005, 0x0AC57074,
                   0x4B118EAC, 0x0EC57074, 0x0EC40148),
    progress_group(0x4B100540, 0xA105, 0x0AC54252,
                   0x4B118EEC, 0x0EC54252, 0x0EC40150),
    progress_group(0x4B100560, 0xA006, 0x0AC54252,
                   0x4B118F64, 0x0EC54252, 0x0EC40158),
    progress_group(0x4B100580, 0xA007, 0x0AC54252,
                   0x4B118F8C, 0x0EC54252, 0x0EC40160),
), [])


CAPTURE_RECORDS = [
    (0x4B100BA0, 0, 0x27BDFFF8),
    (0x4B100BA4, 0, 0xAFB80000),
    (0x4B100BA8, 0, 0xAFB90004),
    (0x4B100BAC, 0, 0x3C18AE34),
    (0x4B100BB0, 0, 0x31390001),
    (0x4B100BB4, 0, 0x13200003),
    (0x4B100BB8, 0, 0x8F190088),
    (0x4B100BBC, 0, 0x27390001),
    (0x4B100BC0, 0, 0xAF190088),
    (0x4B100BC4, 0, 0x31390002),
    (0x4B100BC8, 0, 0x13200003),
    (0x4B100BCC, 0, 0x8F19008C),
    (0x4B100BD0, 0, 0x27390001),
    (0x4B100BD4, 0, 0xAF19008C),
    (0x4B100BD8, 0, 0x31390004),
    (0x4B100BDC, 0, 0x13200003),
    (0x4B100BE0, 0, 0x8F190090),
    (0x4B100BE4, 0, 0x27390001),
    (0x4B100BE8, 0, 0xAF190090),
    (0x4B100BEC, 0, 0x8F190084),
    (0x4B100BF0, 0, 0x27390001),
    (0x4B100BF4, 0, 0xAF190084),
    (0x4B100BF8, 0, 0x8FB80000),
    (0x4B100BFC, 0, 0x8FB90004),
    (0x4B100C00, 0, 0x27BD0008),
    (0x4B100C04, 0, 0x8C470008),
    (0x4B100C08, 0, 0x0AC618EB),
    (0x4B100C0C, 0, 0),
    (0x4B1863A4, 0x8C470008, 0x0AC402E8),
]

# These records are never executed: the capture trampoline returns at c08.
# They preserve the old table's relocation census exactly (six additional
# trace-base loads and seven stores with offsets inside the old +0x7c limit).
CAPTURE_RECORDS += [
    (0x4B100C10 + 4 * i, 0, 0x3C18AE34) for i in range(6)
]
CAPTURE_RECORDS += [
    (0x4B100C28 + 4 * i, 0, 0xAF00006C) for i in range(7)
]


def encode(records):
    return b"".join(RECORD.pack(*record) for record in records)


def census(records):
    bases = stores = 0
    for _, _, word in records:
        op = word >> 26
        reg = (word >> 16) & 0x1F
        if op == 0x0F and reg in (24, 26) and word & 0xFFFF == 0xAE34:
            bases += 1
        elif (op == 0x2B and ((word >> 21) & 0x1F) in (24, 26)
              and word & 0xFFFF <= 0x7C):
            stores += 1
    return bases, stores


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path,
                        help="exact padded U-Boot-proper readback")
    parser.add_argument("output", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    original = args.input.read_bytes()
    old = encode(OLD_RECORDS)
    new = encode(CAPTURE_RECORDS)
    if len(OLD_RECORDS) != 42 or len(CAPTURE_RECORDS) != 42 or len(old) != len(new):
        raise SystemExit("internal patch-table length error")
    if census(OLD_RECORDS) != census(CAPTURE_RECORDS) or census(OLD_RECORDS) != (7, 7):
        raise SystemExit("internal relocation-census mismatch")
    first = original.find(old)
    if first < 0 or original.find(old, first + 1) >= 0:
        raise SystemExit("expected unique progress-marker table was not found")
    candidate = original[:first] + new + original[first + len(old):]
    if len(candidate) != len(original):
        raise SystemExit("candidate size changed")
    args.output.write_bytes(candidate)
    changed = [i for i, (a, b) in enumerate(zip(original, candidate)) if a != b]
    manifest = {
        "input": str(args.input), "output": str(args.output),
        "input_bytes": len(original), "output_bytes": len(candidate),
        "input_sha256": sha256(original), "output_sha256": sha256(candidate),
        "table_offset": first, "table_bytes": len(old),
        "changed_bytes": len(changed),
        "first_changed_offset": changed[0] if changed else None,
        "last_changed_offset": changed[-1] if changed else None,
        "removed_relocation_census": list(census(OLD_RECORDS)),
        "added_relocation_census": list(census(CAPTURE_RECORDS)),
        "scope": "equal-size U-Boot patch-table replacement only",
    }
    if args.manifest:
        args.manifest.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
