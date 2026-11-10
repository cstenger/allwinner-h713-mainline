#!/usr/bin/env python3
"""Send one file to U-Boot `loady ADDR` over the UART (YMODEM, CRC16, 1K).

Types `loady ADDR`, sends the file, then runs `crc32 ADDR SIZE` and exits
nonzero unless U-Boot's CRC matches the host's. Never runs the payload.
"""
import argparse
import os
import re
import sys
import time
import zlib
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import console  # noqa: E402

SOH, STX, EOT, ACK, NAK, CAN, C = 1, 2, 4, 6, 0x15, 0x18, ord("C")


def crc16(data):
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
    return crc & 0xffff


def getc(fd, timeout):
    end = time.time() + timeout
    while time.time() < end:
        try:
            b = os.read(fd, 1)
        except BlockingIOError:
            b = b""
        if b:
            return b[0]
        time.sleep(0.01)
    return None


def wait_for(fd, wanted, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        b = getc(fd, end - time.time())
        if b in wanted:
            return b
        if b == CAN:
            raise RuntimeError("receiver cancelled")
    raise RuntimeError(f"timeout waiting for {wanted}")


def block(fd, seq, payload, size):
    data = payload.ljust(size, b"\x00" if seq == 0 else b"\x1a")
    frame = bytes([SOH if size == 128 else STX, seq & 0xff, 0xff - (seq & 0xff)]) + data
    frame += crc16(data).to_bytes(2, "big")
    for _ in range(10):
        os.write(fd, frame)
        if wait_for(fd, (ACK, NAK)) == ACK:
            return
    raise RuntimeError(f"block {seq} rejected")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file", type=Path)
    ap.add_argument("addr")
    ap.add_argument("--port", default="/dev/ttyUSB0")
    args = ap.parse_args()
    data = args.file.read_bytes()
    fd = console.open_port(args.port)
    try:
        console.drain(fd, 0.5, echo=False)
        console.write_slow(fd, f"loady {args.addr}\n".encode())
        wait_for(fd, (C,), 15)
        block(fd, 0, args.file.name.encode() + b"\x00" + str(len(data)).encode() + b"\x00", 128)
        wait_for(fd, (C,))
        for seq, off in enumerate(range(0, len(data), 1024), 1):
            block(fd, seq, data[off:off + 1024], 1024)
        os.write(fd, bytes([EOT]))
        if wait_for(fd, (ACK, NAK)) == NAK:
            os.write(fd, bytes([EOT]))
            wait_for(fd, (ACK,))
        wait_for(fd, (C,))
        block(fd, 0, b"", 128)
        out = console.drain(fd, 1.5, echo=False).decode("utf-8", "replace")
        console.write_slow(fd, f"crc32 {args.addr} {len(data):x}\n".encode())
        out += console.drain(fd, 1.5, echo=False).decode("utf-8", "replace")
        print(out)
        want = f"{zlib.crc32(data):08x}"
        got = re.search(r"==> ([0-9a-f]{8})", out)
        if not got or got.group(1) != want:
            print(f"CRC MISMATCH: host {want}, board {got and got.group(1)}", file=sys.stderr)
            return 1
        print(f"loaded {len(data)} bytes at {args.addr}, crc32 {want} verified")
        return 0
    finally:
        os.close(fd)


if __name__ == "__main__":
    raise SystemExit(main())
