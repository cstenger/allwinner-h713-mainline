#!/usr/bin/env python3
"""Decode the VIncap IRQ path and capture events in board-B display.bin.

This inspects firmware bytes only. It does not read the live TVCAP register
window, whose ARM-side access has previously locked the board.
"""

import argparse
import hashlib
import json
import struct
from pathlib import Path

BASE = 0x8B100000
EXPECTED_SHA256 = "4380f1b3ed7b62aa50582e7cb16a87bdface1b4300578fe3631a416354da30ce"
TABLE = 0x8B2023F4
STRIDE = 0x2C
HANDLER = 0x8B186388
IRQ_DESCRIPTORS = 0x8B2317AC
IRQ_STRIDE = 0x2C
VINCAP_IRQ_INDEX = 33
VINCAP_HANDLER_TABLE = 0x8B2322BC


def word(image, address):
    return struct.unpack_from("<I", image, address - BASE)[0]


def inspect(path):
    image = path.read_bytes()
    digest = hashlib.sha256(image).hexdigest()
    if digest != EXPECTED_SHA256:
        raise ValueError(f"unvalidated display image: {digest}")
    expected = {
        0x8B2322C8: HANDLER,  # dispatch table contains capture handler
        0x8B186388: 0x3C02BB94,  # lui v0, 0xbb94
        0x8B18638C: 0x8C490100,  # lw t1, 0x100(v0)
        0x8B186390: 0x8C430008,  # lw v1, 0x008(v0)
        0x8B186398: 0x7D293A00,  # extract bits 8..15 from 0x100
        0x8B18639C: 0x7C633A00,  # extract bits 8..15 from 0x008
        0x8B1863A0: 0x01234824,  # mask status with enabled bits
        0x8B1863C4: 0xAC460008,  # write 0x008 in acknowledge sequence
        0x8B184990: 0x00431021,  # dispatcher indexes IRQ descriptor table
        0x8B184998: 0x8C560028,  # descriptor's handler-table pointer
        0x8B1849C0: 0x8EC2000C,  # handler-table slot 3 decodes events
        0x8B1849C8: 0x0040F809,  # call decoder
        0x8B1849EC: 0x8EC30008,  # handler-table slot 2 processes events
        0x8B1849F0: 0x0060F809,  # call event processor
        0x8B184A4C: 0x0EC56062,  # forward decoded event
        0x8B1867FC: 0xAC820000,  # capture event table at output offset 0
        0x8B186824: 0xAC820010,  # third event descriptor
    }
    for address, value in expected.items():
        if word(image, address) != value:
            raise ValueError(f"unexpected instruction/data at {address:#x}")
    entries = []
    for index in range(3):
        address = TABLE + index * STRIDE
        offset = address - BASE
        name = image[offset:offset + 32].split(b"\0", 1)[0].decode("ascii")
        event_id, status_bit, field_28 = struct.unpack_from(
            "<III", image, offset + 0x20)
        entries.append({"name": name, "table_va": f"{address:#010x}",
                        "event_id": event_id, "status_bit": status_bit,
                        "field_28_unidentified": field_28})
    if [entry["name"] for entry in entries] != [
            "cap-vde", "cap-vs", "cap-mode_change"]:
        raise ValueError("capture descriptor table layout changed")
    descriptor_va = IRQ_DESCRIPTORS + VINCAP_IRQ_INDEX * IRQ_STRIDE
    descriptor_off = descriptor_va - BASE
    descriptor_name = image[descriptor_off:descriptor_off + 20].split(
        b"\0", 1)[0].decode("ascii")
    if descriptor_name != "VIncap":
        raise ValueError(f"unexpected IRQ descriptor: {descriptor_name}")
    if word(image, descriptor_va + 0x20) != 0x14:
        raise ValueError("unexpected VIncap IRQ number")
    if word(image, descriptor_va + 0x28) != VINCAP_HANDLER_TABLE:
        raise ValueError("unexpected VIncap handler table")
    handlers = [word(image, VINCAP_HANDLER_TABLE + i * 4)
                for i in range(5)]
    if handlers[3] != HANDLER or handlers[4] != 0x8B1867EC:
        raise ValueError("unexpected VIncap decoder or event-table builder")
    vin_cap_1_va = IRQ_DESCRIPTORS + 26 * IRQ_STRIDE
    if image[vin_cap_1_va - BASE:vin_cap_1_va - BASE + 8] != b"VIncap_1":
        raise ValueError("unexpected VIncap_1 descriptor")
    if word(image, vin_cap_1_va + 0x28) != 0:
        raise ValueError("VIncap_1 unexpectedly has a handler table")
    return {"firmware": str(path), "sha256": digest,
            "handler_va": f"{HANDLER:#010x}",
            "irq_descriptor": {"name": descriptor_name,
                               "table_index": VINCAP_IRQ_INDEX,
                               "table_va": f"{descriptor_va:#010x}",
                               "irq_number": 0x14,
                               "handler_table_va": f"{VINCAP_HANDLER_TABLE:#010x}",
                               "handler_slots": [f"{va:#010x}" for va in handlers]},
            "dispatcher_va": "0x8b184970",
            "event_forwarder_va": "0x8b158188",
            "mips_status_register": "0xbb940100 bits 8..15",
            "mips_mask_ack_register": "0xbb940008 bits 8..15 / low byte",
            "arm_physical_candidates": ["0x06940100", "0x06940008"],
            "entries": entries,
            "scope": "static candidate only; no live MMIO performed"}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("firmware", type=Path)
    args = ap.parse_args()
    print(json.dumps(inspect(args.firmware), indent=2))


if __name__ == "__main__":
    main()
