#!/usr/bin/env python3
"""A/B test of PL4's mux for the gpio-keys power key (kernel 0170 running).

Stock's R_PIO is SUNXI_PCTL_HW_TYPE_1 with irq_mux_val 0xE and lists PL4's
"irq" function at muxval 0xE; our pin table says 0x6 and patch 0004 skips the
mux entirely, so the pin sits at 0 (gpio_in). Window A presses with the mux as
the kernel left it, window B with PL4 switched to 0xE behind the kernel's back.
Each window records the "Power" interrupt count, KEY_POWER events from
gpio-keys and the polled DAT level (does the input still read in IRQ mux?).
The mux is put back on exit. Prompts on tty1. Runs on the board as root.
"""
import glob, mmap, os, select, struct, sys, time

OUT = next((a for a in sys.argv[1:] if not a.startswith("--")),
           time.strftime("/root/pl4-mux-%Y%m%d-%H%M%S"))
SHORT = "--short" in sys.argv
os.makedirs(OUT, exist_ok=True)
log_f = open(f"{OUT}/log.txt", "w")
t0 = time.monotonic()

def log(msg):
    line = f"{time.monotonic() - t0:8.3f} {msg}"
    print(line, flush=True); log_f.write(line + "\n"); log_f.flush()

def prompt(msg):
    log(f"PROMPT {msg}")
    try:
        with open("/dev/tty1", "w") as tty:
            tty.write("\033[2J\033[H\n\n\n" + "\n".join(f"    {l}" for l in msg.split("|")) + "\n")
    except OSError as e:
        log(f"tty1: {e}")

def irq_count():
    for line in open("/proc/interrupts"):
        if line.rstrip().endswith(" Power"):
            return sum(int(x) for x in line.split()[1:5])
    return None

fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=0x07022000)
rd = lambda o: struct.unpack("<I", m[o:o + 4])[0]
def wr(o, v): m[o:o + 4] = struct.pack("<I", v)
def set_mux(v):
    x = rd(0x00); wr(0x00, (x & ~(0xF << 16)) | (v << 16))
mux = lambda: (rd(0x00) >> 16) & 0xF
level = lambda: (rd(0x10) >> 4) & 1

ev_path = next("/dev/input/" + os.path.basename(p) for p in glob.glob("/sys/class/input/event*")
               if open(f"{p}/device/name").read().strip() == "gpio-keys")
ev = os.open(ev_path, os.O_RDONLY | os.O_NONBLOCK)
FMT = "llHHi"; SZ = struct.calcsize(FMT)
saved_mux = mux()
log(f"PL4 mux {saved_mux:x}, level {level()}, Power irqs {irq_count()}, {ev_path}")

def window(secs, label):
    n0, keys, edges, last = irq_count(), [], [], level()
    end = time.monotonic() + secs
    while time.monotonic() < end:
        v = level()
        if v != last:
            edges.append(v); last = v
        if select.select([ev], [], [], 0.002)[0]:
            data = os.read(ev, SZ * 32)
            for i in range(0, len(data) - SZ + 1, SZ):
                _, _, typ, code, val = struct.unpack(FMT, data[i:i + SZ])
                if typ == 1:
                    keys.append((code, val)); log(f"{label}: key {code} = {val}")
    log(f"RESULT {label}: mux={mux():x} irqs +{irq_count() - n0} "
        f"key events {len(keys)} DAT edges {len(edges)}")

try:
    if SHORT:
        set_mux(0xE); log(f"mux now {mux():x}, level {level()}")
        window(1, "B-dry")
    else:
        prompt("CASE BUTTON (A)|press SHORT, 3 times, ~2 s apart")
        window(10, "A mux=%x" % saved_mux)
        set_mux(0xE)
        prompt("CASE BUTTON (B)|press SHORT, 3 times, ~2 s apart")
        window(10, "B mux=e")
    prompt("DONE - thank you")
finally:
    set_mux(saved_mux)
    log(f"restored PL4 mux {mux():x}")
