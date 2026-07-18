#!/usr/bin/env python3
"""Boot smoke5 over CDC, let the autonomous init write eMMC + reboot,
then verify the write from U-Boot by reading the sector back."""
import os, glob, time, termios

VID_DIR = "/sys/bus/usb/devices"
ABS_LBA_HEX = "0x54c400"   # p26 start = 5555200

def acm_tty():
    for d in glob.glob(VID_DIR + "/*/"):
        try:
            if open(d + "idVendor").read().strip() != "1f3a":
                continue
        except OSError:
            continue
        t = glob.glob(d + "*:*/tty/*")
        if t:
            return "/dev/" + os.path.basename(t[0])
    return None

def gadget_present():
    return acm_tty() is not None

def open_port(path):
    for _ in range(50):
        try:
            fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            break
        except OSError:
            time.sleep(0.1)
    else:
        raise SystemExit("cannot open " + path)
    a = termios.tcgetattr(fd)
    a[0] = 0; a[1] = 0
    a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    a[3] = 0; a[4] = termios.B115200; a[5] = termios.B115200
    a[6][termios.VMIN] = 0; a[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, a)
    return fd

def cmd(fd, s, wait=2.5):
    os.write(fd, s.encode() + b"\n")
    out = b""; t0 = time.time()
    while time.time() - t0 < wait:
        try:
            b = os.read(fd, 65536)
        except (BlockingIOError, OSError):
            b = b""
        if b: out += b
        else: time.sleep(0.02)
    return out.decode("utf-8", "replace")

def main():
    port = acm_tty()
    print("boot port:", port)
    fd = open_port(port)
    time.sleep(0.2)
    # drain
    while True:
        try:
            if not os.read(fd, 4096): break
        except (BlockingIOError, OSError): break
    print(">>> bootm 0x50000000 (kernel will write eMMC + self-reboot)")
    os.write(fd, b"bootm 0x50000000\n")
    time.sleep(1.0)
    try: os.close(fd)
    except OSError: pass

    # wait for gadget to drop (kernel took musb) then return (U-Boot reboot)
    t0 = time.time()
    while gadget_present() and time.time() - t0 < 25:
        time.sleep(0.2)
    print("[t+%.1f] gadget dropped (kernel running)" % (time.time() - t0))
    while not gadget_present() and time.time() - t0 < 75:
        time.sleep(0.3)
    if not gadget_present():
        raise SystemExit("[t+%.1f] gadget never returned -> kernel hung?" % (time.time() - t0))
    print("[t+%.1f] gadget back (rebooted to U-Boot)" % (time.time() - t0))
    time.sleep(2)

    port = acm_tty()
    print("verify port:", port)
    fd = open_port(port)
    time.sleep(0.3)
    while True:
        try:
            if not os.read(fd, 4096): break
        except (BlockingIOError, OSError): break
    cmd(fd, "mmc dev 1", 2)
    print(cmd(fd, "mmc read 0x50000000 %s 0x200" % ABS_LBA_HEX, 3))
    out = cmd(fd, "md.l 0x50000000 8", 3)
    print(out)
    os.close(fd)

    firstline = ""
    for ln in out.splitlines():
        if ln.strip().startswith("50000000:"):
            firstline = ln; break
    print("=== VERDICT ===")
    if "45545257" in out:
        print("eMMC WRITE VERIFIED: kernel-written 'WRTE' pattern read back by "
              "U-Boot at sector %s  ->  %s" % (ABS_LBA_HEX, firstline.strip()))
    else:
        print("NOT FOUND: 'WRTE' magic (45545257) absent -> write did not land")
        print("first data line:", firstline.strip())

if __name__ == "__main__":
    main()
