#!/usr/bin/env python3
"""Set BL31-safe placement + bootargs, bootm the smoke FIT, capture console.

Usage: boot_kernel.py [--secs 30] [--addr 0x50000000]
"""
import os, sys, time, termios, argparse

PORT = "/dev/ttyUSB0"
BOOTARGS = ("console=ttyS0,115200 earlycon loglevel=8 panic=10 "
            "rdinit=/init clk_ignore_unused pd_ignore_unused")

def open_port():
    fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    a = termios.tcgetattr(fd)
    a[0] = 0; a[1] = 0
    a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    a[3] = 0
    a[4] = termios.B115200; a[5] = termios.B115200
    a[6][termios.VMIN] = 0; a[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, a)
    return fd

def cmd(fd, s, settle=0.4):
    os.write(fd, s.encode() + b"\n")
    time.sleep(settle)
    out = b""
    t0 = time.time()
    while time.time() - t0 < 1.5:
        try:
            b = os.read(fd, 65536)
        except BlockingIOError:
            b = b""
        if b:
            out += b
        else:
            time.sleep(0.02)
    return out.decode("utf-8", "replace")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--secs", type=float, default=30.0)
    ap.add_argument("--addr", default="0x50000000")
    args = ap.parse_args()

    fd = open_port()
    time.sleep(0.2)
    # drain
    while True:
        try:
            if not os.read(fd, 4096):
                break
        except BlockingIOError:
            break

    print("--- setenv fdt_high ---");   print(cmd(fd, "setenv fdt_high 0x4f000000"))
    print("--- setenv initrd_high ---");print(cmd(fd, "setenv initrd_high 0x4f000000"))
    print("--- setenv bootargs ---");   print(cmd(fd, "setenv bootargs '%s'" % BOOTARGS))
    print("--- iminfo ---");            print(cmd(fd, "iminfo %s" % args.addr))

    print("=== bootm (%s), capturing %.0fs ===" % (args.addr, args.secs), flush=True)
    os.write(fd, ("bootm %s\n" % args.addr).encode())
    t0 = time.time()
    total = 0
    while time.time() - t0 < args.secs:
        try:
            b = os.read(fd, 65536)
        except BlockingIOError:
            b = b""
        except OSError as e:
            print("\n[console EIO: %s]" % e); break
        if b:
            sys.stdout.write(b.decode("utf-8", "replace"))
            sys.stdout.flush()
            total += len(b)
        else:
            time.sleep(0.02)
    os.close(fd)
    print("\n=== capture end (%d bytes) ===" % total)

if __name__ == "__main__":
    main()
