#!/usr/bin/env python3
"""Prepare an exact-image U-Boot diagnostic table for HDMI audio tracing.

This writes host artifacts only. It replaces the 42-record VIncap diagnostic
overlay, preserving U-Boot's table size and relocation census. The RAM installer
was withdrawn after a read-only mapping fault. --candidate creates a complete
padded image and exact rollback copy; writing bootloader storage requires user
approval. Never install this into a live MIPS firmware.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

FW_SHA = "4380f1b3ed7b62aa50582e7cb16a87bdface1b4300578fe3631a416354da30ce"
UBOOT_SHA = "c882461d5ee69128c79d99b784fde668ee4d57ab09ae308738e3f9ea91fd1ce7"
UBOOT_PADDED_SIZE = 920576
CAVE = 0x8B1004C0
MAILBOX = 0xAD980000
FIELDS = {
    "monitor_calls": 0x100, "status_change_dispatches": 0x104,
    "current_status": 0x108, "previous_status": 0x10C,
    "n": 0x110, "sample_rate_hz": 0x114,
    "audio_object": 0x118,
}

spec = importlib.util.spec_from_file_location(
    "cap_trace", Path(__file__).with_name("make-cap-irq-trace-uboot.py"))
cap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cap)


def jump(address):
    return 0x08000000 | ((address >> 2) & 0x03FFFFFF)


def branch(pc, target, rs=3, rt=2):
    delta = (target - pc - 4) // 4
    if (target - pc - 4) % 4 or not -32768 <= delta <= 32767:
        raise ValueError("branch target outside signed 16-bit reach")
    return 0x10000000 | (rs << 21) | (rt << 16) | (delta & 0xFFFF)


def monitor_records():
    # Hook the comparison, leaving addiu a1,s0,0x78 as its delay slot.
    # Preserve both scratch registers and the stack; no firmware/MMIO writes.
    words = [
        0x27BDFFF8, 0xAFB80000, 0xAFB90004, 0x3C18AD98,
        0x8F190100, 0x27390001, 0xAF190100,
        0xAF020108, 0xAF03010C,
        0x8E390004, 0xAF190110, 0x8E390008, 0xAF190114,
        0xAF110118,
        branch(CAVE + 14 * 4, CAVE + 18 * 4), 0x8F190104,
        0x27390001, 0xAF190104,
        0x8FB80000, 0x8FB90004, 0x27BD0008,
        branch(CAVE + 21 * 4, CAVE + 25 * 4), 0,
        jump(0x8B13A2FC), 0, jump(0x8B13A31C), 0,
    ]
    records = [(CAVE - 0x40000000 + i * 4, 0, w)
               for i, w in enumerate(words)]
    records.append((0x4B13A2F4, 0x10620009, jump(CAVE)))
    # Unreachable after the final jump. These maintain the installed loader's
    # fixed seven-base/seven-store relocation census without using old slots.
    records += [(CAVE - 0x40000000 + (27 + i) * 4, 0, 0x3C18AE34)
                for i in range(7)]
    records += [(CAVE - 0x40000000 + (34 + i) * 4, 0, 0xAF00006C)
                for i in range(7)]
    return records


def fit_uboot_region(data):
    """Locate the inline, uncompressed U-Boot data property in this FIT."""
    if len(data) < 40:
        raise ValueError("truncated FIT header")
    header = struct.unpack_from(">10I", data)
    magic, total, start, names = header[:4]
    names_size, struct_size = header[8:10]
    end = start + struct_size
    if (magic != 0xD00DFEED or not 40 <= total <= len(data) or
            header[5] != 17 or header[6] > 17 or start % 4 or
            not 40 <= start < end <= total or
            not 40 <= names <= names + names_size <= total or
            not (end <= names or names + names_size <= start)):
        raise ValueError("invalid or incomplete version-17 FIT")
    strings = data[names:names + names_size]
    pos = start
    stack = []
    found = []
    root_seen = False
    while pos + 4 <= end:
        token = struct.unpack_from(">I", data, pos)[0]
        pos += 4
        if token == 1:
            nul = data.find(b"\0", pos, end)
            if nul < 0:
                raise ValueError("unterminated FIT node")
            name = data[pos:nul]
            if not stack:
                if root_seen or name:
                    raise ValueError("expected one empty FIT root")
                root_seen = True
            stack.append(name)
            pos = (nul + 4) & ~3
        elif token == 2:
            if not stack:
                raise ValueError("unbalanced FIT nodes")
            stack.pop()
        elif token == 3:
            if not stack or pos + 8 > end:
                raise ValueError("truncated or misplaced FIT property")
            size, nameoff = struct.unpack_from(">II", data, pos)
            pos += 8
            nul = strings.find(b"\0", nameoff)
            if nul < 0 or nameoff >= len(strings):
                raise ValueError("invalid FIT property name")
            if pos + size > end:
                raise ValueError("FIT property exceeds structure block")
            if stack == [b"", b"images", b"uboot"] and strings[nameoff:nul] == b"data":
                found.append((pos, size))
            pos = (pos + size + 3) & ~3
        elif token == 4:
            continue
        elif token == 9:
            if stack or not root_seen or len(found) != 1:
                raise ValueError("expected one inline U-Boot image in complete FIT")
            return found[0]
        else:
            raise ValueError(f"unexpected FIT token {token}")
        if pos > end:
            raise ValueError("FIT padding exceeds structure block")
    raise ValueError("missing FIT end token")


def prepare(uboot, firmware):
    if hashlib.sha256(firmware).hexdigest() != FW_SHA:
        raise ValueError("firmware SHA256 does not match board-B image")
    if (len(uboot) < UBOOT_PADDED_SIZE or
            hashlib.sha256(uboot[:UBOOT_PADDED_SIZE]).hexdigest() != UBOOT_SHA):
        raise ValueError("installed padded U-Boot SHA256 mismatch")
    # Full storage readbacks may include a suffix; only the pinned padded image
    # participates in parsing, table ownership, generation and rollback.
    uboot = uboot[:UBOOT_PADDED_SIZE]
    old = cap.encode(cap.CAPTURE_RECORDS)
    start = uboot.find(old)
    if start < 0 or uboot.find(old, start + 1) >= 0:
        raise ValueError("expected unique capture diagnostic table")
    # Other trace modes have independent tables using the same old caves.
    # Check ownership only within this contiguous firmware patch table.
    lo, hi = start, start + len(old)
    while lo >= 16 and 0x4B100000 <= struct.unpack_from("<Q", uboot, lo - 16)[0] < 0x4B600000:
        lo -= 16
    while hi + 16 <= len(uboot) and 0x4B100000 <= struct.unpack_from("<Q", uboot, hi)[0] < 0x4B600000:
        hi += 16
    outside = uboot[lo:start] + uboot[start + len(old):hi]
    occupied = {cap.RECORD.unpack_from(outside, i)[0]
                for i in range(0, len(outside), cap.RECORD.size)}
    records = monitor_records()
    if len(records) != 42 or cap.census(records) != cap.census(cap.CAPTURE_RECORDS):
        raise ValueError("patch-table size or relocation census changed")
    for address, expected, _ in records:
        actual = struct.unpack_from("<I", firmware, address - 0x4B100000)[0]
        if actual != expected:
            raise ValueError(f"firmware site mismatch at {address:#x}")
        # Refuse a cave or hook already owned by a different installed patch.
        if address in occupied:
            raise ValueError(f"patch address already appears outside replaced table: {address:#x}")
    dataoff, datasize = fit_uboot_region(uboot)
    if not dataoff <= start <= dataoff + datasize - len(old):
        raise ValueError("table not contained in U-Boot data")
    new = cap.encode(records)
    profile = {
        "schema": 1, "scope": "diagnostic firmware patch table; no live MIPS code patching",
        "firmware_sha256": FW_SHA, "installed_uboot_padded_sha256": UBOOT_SHA,
        "fit_table_offset": start, "uboot_data_offset": dataoff,
        "ram_offset_from_relocaddr": start - dataoff,
        "table_bytes": len(old), "old_table_hex": old.hex(),
        "new_table_hex": new.hex(), "records": records,
        "mailbox_physical": 0x4D980000, "fields": FIELDS,
        "removed_feature": "VIncap interrupt-mask counters",
        "preserved_features": "CPU_COMM, source-3, canaries, panel traces",
        "cold_start_required": True,
    }
    return new, profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("uboot", type=Path)
    parser.add_argument("firmware", type=Path)
    parser.add_argument("output", type=Path, help="new output directory (must not exist)")
    parser.add_argument("--candidate", action="store_true",
                        help="also save padded U-Boot candidate and exact rollback image; does not flash")
    args = parser.parse_args()
    original = args.uboot.read_bytes()
    table, profile = prepare(original, args.firmware.read_bytes())
    original = original[:UBOOT_PADDED_SIZE]
    if args.candidate:
        start = profile["fit_table_offset"]
        candidate = original[:start] + table + original[start + len(table):]
        changed = [i for i, (a, b) in enumerate(zip(original, candidate)) if a != b]
        if (len(candidate) != len(original) or not changed or
                any(not start <= i < start + len(table) for i in changed)):
            raise ValueError("candidate changes escape the fixed-size patch table")
        manifest = {
            "bytes": len(candidate), "sectors": len(candidate) // 512,
            "input_sha256": hashlib.sha256(original).hexdigest(),
            "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
            "changed_bytes": len(changed), "first_changed_offset": changed[0],
            "last_changed_offset": changed[-1], "table_offset": start,
            "table_bytes": len(table), "storage_modified": False,
            "scope": "same-size diagnostic table replacement; host artifacts only",
        }
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "audio-monitor-table.bin").write_bytes(table)
    (args.output / "audio-monitor-profile.json").write_text(json.dumps(profile, indent=2) + "\n")
    if args.candidate:
        (args.output / "uboot-before.bin").write_bytes(original)
        (args.output / "uboot-audio-monitor.bin").write_bytes(candidate)
        (args.output / "candidate-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({k: v for k, v in profile.items()
                      if k not in ("old_table_hex", "new_table_hex", "records")}, indent=2))


if __name__ == "__main__":
    main()
