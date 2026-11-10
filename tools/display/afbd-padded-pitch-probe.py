#!/usr/bin/env python3
"""Test a 960x544 AFBD source stored with the panel's 1280-byte pitch."""

import mmap
import os
import struct
import subprocess
import time


AFBD_BASE = 0x05600000
FRAME_BASE = 0x6C500000
WIDTH = 960
HEIGHT = 544
PITCH = 1280
Y_BYTES = PITCH * HEIGHT
MAP_BYTES = Y_BYTES + PITCH * HEIGHT // 2


def main() -> int:
    if os.environ.get("ARMED") != "yes":
        raise SystemExit("set ARMED=yes with an observer watching the panel")

    with open("/root/scaler-testcard-960x544.nv12", "rb") as source:
        packed = source.read()
    if len(packed) != WIDTH * HEIGHT * 3 // 2:
        raise RuntimeError("unexpected test-card size")

    padded = bytearray(MAP_BYTES)
    padded[:Y_BYTES] = bytes([16]) * Y_BYTES
    padded[Y_BYTES:] = bytes([128]) * (MAP_BYTES - Y_BYTES)
    for row in range(HEIGHT):
        padded[row * PITCH:row * PITCH + WIDTH] = \
            packed[row * WIDTH:(row + 1) * WIDTH]
    packed_chroma = WIDTH * HEIGHT
    for row in range(HEIGHT // 2):
        dst = Y_BYTES + row * PITCH
        src = packed_chroma + row * WIDTH
        padded[dst:dst + WIDTH] = packed[src:src + WIDTH]

    mem_fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
    regs = mmap.mmap(mem_fd, 4096, mmap.MAP_SHARED,
                     mmap.PROT_READ | mmap.PROT_WRITE, offset=AFBD_BASE)
    frame = mmap.mmap(mem_fd, MAP_BYTES, mmap.MAP_SHARED,
                      mmap.PROT_READ | mmap.PROT_WRITE, offset=FRAME_BASE)
    process = None

    def read32(offset: int) -> int:
        return struct.unpack_from("<I", regs, offset)[0]

    def write32(offset: int, value: int) -> None:
        struct.pack_into("<I", regs, offset, value)

    def commit(offset: int) -> None:
        write32(offset, 1)
        for _ in range(5000):
            if read32(offset) == 0:
                return
            time.sleep(0.00001)
        raise RuntimeError(f"AFBD commit {offset:#x} did not retire")

    try:
        environment = dict(os.environ, SRC="960x544", ARMED="yes")
        process = subprocess.Popen([
            "/root/kms-nv12-plane-test",
            "/root/scaler-testcard-960x544.nv12",
            "25",
        ], env=environment)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if read32(0x20) == 0x021F03BF and read32(0x40) == WIDTH:
                break
            if process.poll() is not None:
                raise RuntimeError("test card exited before its atomic update")
            time.sleep(0.02)
        else:
            raise RuntimeError("timed out waiting for 960x544 AFBD geometry")

        print("BASELINE: five seconds", flush=True)
        time.sleep(5)

        control = read32(0x10)
        write32(0x10, control & ~3)
        commit(0x14)
        frame[:] = padded
        write32(0x40, PITCH)
        write32(0x44, PITCH)
        for offset in (0x84, 0x88, 0x8C, 0x90):
            write32(offset, FRAME_BASE + Y_BYTES)
        write32(0x10, control)
        commit(0x14)
        commit(0x6C)
        print(f"PADDED: pitch={PITCH}, C={FRAME_BASE + Y_BYTES:#x} for twelve seconds",
              flush=True)
        time.sleep(12)
    finally:
        if process is not None:
            process.terminate()
            process.wait()
        frame.close()
        regs.close()
        os.close(mem_fd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
