#!/usr/bin/env python3
"""Temporarily test one AFBD window field during smaller-source scanout."""

import mmap
import os
import struct
import subprocess
import sys
import time


AFBD_BASE = 0x05600000
SOURCE_SIZE_M1 = ((544 - 1) << 16) | (960 - 1)
PANEL_SIZE_M1 = ((720 - 1) << 16) | (1280 - 1)


def main() -> int:
    if os.environ.get("ARMED") != "yes":
        raise SystemExit("set ARMED=yes with an observer watching the panel")
    if len(sys.argv) != 2 or sys.argv[1] not in {"0x20", "0x30"}:
        raise SystemExit(f"usage: {sys.argv[0]} 0x20|0x30")

    offset = int(sys.argv[1], 16)
    panel_value = PANEL_SIZE_M1 if offset == 0x20 else (720 << 16) | 1280
    source_value = SOURCE_SIZE_M1 if offset == 0x20 else (544 << 16) | 960
    mem_fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
    regs = mmap.mmap(mem_fd, 4096, mmap.MAP_SHARED,
                     mmap.PROT_READ | mmap.PROT_WRITE, offset=AFBD_BASE)
    process = None

    def read32(reg: int) -> int:
        return struct.unpack_from("<I", regs, reg)[0]

    def write32(reg: int, value: int) -> None:
        struct.pack_into("<I", regs, reg, value)

    def commit() -> None:
        write32(0x14, 1)
        for _ in range(5000):
            if read32(0x14) == 0:
                return
            time.sleep(0.00001)
        raise RuntimeError("AFBD source configuration did not retire")

    def apply_window(value: int) -> None:
        if os.environ.get("RESTART") == "yes":
            control = read32(0x10)
            write32(0x10, control & ~3)
            commit()
            write32(offset, value)
            write32(0x10, control)
            commit()
        else:
            write32(offset, value)
            commit()

    try:
        environment = dict(os.environ, SRC="960x544", ARMED="yes")
        process = subprocess.Popen([
            "/root/kms-nv12-plane-test",
            "/root/scaler-testcard-960x544.nv12",
            "25",
        ], env=environment)

        # Avoid the race that invalidated the first source-window experiment.
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if (read32(0x20) == SOURCE_SIZE_M1 and
                    read32(0x30) == ((544 << 16) | 960)):
                break
            if process.poll() is not None:
                raise RuntimeError("test card exited before its atomic update")
            time.sleep(0.02)
        else:
            raise RuntimeError("timed out waiting for 960x544 AFBD geometry")

        print("BASELINE: five seconds", flush=True)
        time.sleep(5)
        apply_window(panel_value)
        print(f"TEST: {sys.argv[1]}={read32(offset):#010x} for twelve seconds",
              flush=True)
        time.sleep(12)
    finally:
        # Restore the live source value rather than a pre-atomic inherited one.
        apply_window(source_value)
        print(f"RESTORED: {sys.argv[1]}={read32(offset):#010x}", flush=True)
        if process is not None:
            process.wait()
        regs.close()
        os.close(mem_fd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
