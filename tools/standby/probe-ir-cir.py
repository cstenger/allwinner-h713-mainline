#!/usr/bin/env python3
"""A/B test of the IR sample-config register (CIR, 0x07040034) on kernel 0172.

At boot the rc core enables NEC (keymap) and its s_timeout writes 0x2d04
(NTHR 1, ITHR 0x2d); sunxi_ir_hw_init runs afterwards and writes the vendor
value 0x00200b2a over it. With 0x2d04 the remote decoded (run 1), with the
vendor value nothing decoded (run 2). Window A: CIR = 0x2d04. Window B:
CIR = 0x00200b2a. Each logs scancodes, key events, the sunxi-ir interrupt
count and raw mode2 from lirc0. CIR is set back to the value found at start.
Prompts on tty1. Runs on the board as root.
"""
import glob, mmap, os, select, struct, sys, time

OUT = next((a for a in sys.argv[1:] if not a.startswith("--")),
           time.strftime("/root/ir-cir-%Y%m%d-%H%M%S"))
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

def irqs():
    for line in open("/proc/interrupts"):
        if line.rstrip().endswith("sunxi-ir"):
            return sum(int(x) for x in line.split()[1:5])

fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=0x07040000)
rd = lambda o: struct.unpack("<I", m[o:o + 4])[0]
def wr(o, v): m[o:o + 4] = struct.pack("<I", v)
CIR = 0x34

ev = os.open(next("/dev/input/" + os.path.basename(p) for p in glob.glob("/sys/class/input/event*")
                  if open(f"{p}/device/name").read().strip() == "sunxi-ir"), os.O_RDONLY | os.O_NONBLOCK)
lirc = os.open("/dev/lirc0", os.O_RDONLY | os.O_NONBLOCK)
FMT = "llHHi"; SZ = struct.calcsize(FMT)
saved = rd(CIR)
log(f"CIR at start {saved:#x}, protocols {open('/sys/class/rc/rc0/protocols').read().strip()}")

def window(secs, label, cir):
    wr(CIR, cir); time.sleep(0.05)
    log(f"{label}: CIR now {rd(CIR):#x}")
    n0, scans, keys = irqs(), [], []
    raw = open(f"{OUT}/mode2-{label}.txt", "w")
    end = time.monotonic() + secs
    while (left := end - time.monotonic()) > 0:
        for f in select.select([ev, lirc], [], [], left)[0]:
            if f == lirc:
                data = os.read(lirc, 4 * 512)
                for i in range(0, len(data) - 3, 4):
                    v = struct.unpack("<I", data[i:i + 4])[0]
                    raw.write(f"{v >> 24:x} {v & 0xFFFFFF}\n")
                continue
            data = os.read(ev, SZ * 64)
            for i in range(0, len(data) - SZ + 1, SZ):
                _, _, typ, code, val = struct.unpack(FMT, data[i:i + SZ])
                if typ == 4 and code == 4:
                    scans.append(val); log(f"{label}: scan {val:#x}")
                elif typ == 1:
                    keys.append((code, val)); log(f"{label}: key {code} = {val}")
    raw.close()
    log(f"RESULT {label}: CIR {rd(CIR):#x} irqs +{irqs() - n0} scans {len(scans)} keys {len(keys)}")

try:
    prompt("REMOTE (A): press POWER twice|~2 s apart")
    window(8, "A", 0x2d04)
    prompt("REMOTE (B): press POWER twice|~2 s apart")
    window(8, "B", 0x00200b2a)
    prompt("DONE - thank you")
finally:
    wr(CIR, saved)
    log(f"CIR restored to {rd(CIR):#x}")
