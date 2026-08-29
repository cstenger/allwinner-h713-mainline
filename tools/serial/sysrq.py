#!/usr/bin/env python3
"""Send a Magic SysRq command over the serial console.

A wedged board used to mean walking to the power switch. Kernels built with
`patches/kernel/board/kasan.config` or `builtin-drivers.config` set
CONFIG_MAGIC_SYSRQ + MAGIC_SYSRQ_SERIAL with an empty trigger sequence, so a
UART BREAK followed by one character is a sysrq.

    sysrq.py h      # help — proves sysrq is listening, changes nothing
    sysrq.py b      # reboot immediately, no sync (the way back from a wedge)
    sysrq.py s      # emergency sync
    sysrq.py w      # dump blocked (D-state) tasks

It cannot help against a true hard lockup — if every CPU is spinning with
interrupts disabled, nothing gets to run the handler, and the power switch is
still the answer. Try `h` first: silence there means sysrq is not being reached.
"""
import argparse
import fcntl
import os
import sys
import termios
import time


def open_port(path):
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    a = termios.tcgetattr(fd)
    a[0] = 0
    a[1] = 0
    a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    a[3] = 0
    a[4] = termios.B115200
    a[5] = termios.B115200
    a[6][termios.VMIN] = 0
    a[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, a)
    return fd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("key", help="sysrq command character (h, b, s, w, ...)")
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--listen", type=float, default=6.0)
    ap.add_argument("--break-ms", type=float, default=250.0,
                    help="explicit UART BREAK duration (default: 250 ms)")
    args = ap.parse_args()

    fd = open_port(args.port)
    try:
        # tcsendbreak(fd, 0) is allowed to be implemented as a fixed-duration
        # driver request.  CP210x adapters have occasionally failed to turn
        # that into a receive-side BREAK on this board, so assert/deassert the
        # line explicitly and make the duration selectable.
        fcntl.ioctl(fd, 0x5427)  # TIOCSBRK
        time.sleep(args.break_ms / 1000.0)
        fcntl.ioctl(fd, 0x5428)  # TIOCCBRK
        time.sleep(0.15)
        os.write(fd, args.key[:1].encode())
        end = time.time() + args.listen
        while time.time() < end:
            try:
                chunk = os.read(fd, 4096)
            except BlockingIOError:
                chunk = b""
            if chunk:
                sys.stdout.write(chunk.decode("utf-8", "replace"))
                sys.stdout.flush()
                end = time.time() + args.listen
            else:
                time.sleep(0.05)
    finally:
        os.close(fd)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
