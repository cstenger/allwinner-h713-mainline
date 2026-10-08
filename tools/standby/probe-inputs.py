#!/usr/bin/env python3
"""Operator-timed probe of the standby inputs: the case power button (PL4)
and the stock IR remote.  Runs on the board as root, unattended once started;
prompts appear on the panel console (tty1) and in the log.

  1. PL4 idle level under no pull / pull-up / pull-down -> driven or floating?
  2. case-button window(s): every PL4 edge, 2 ms polling
  3. remote POWER window, then a window for a few other keys
     -> NEC/RC5/RC6 scancodes from rc0 (MSC_SCAN) plus raw mode2 from lirc0

PL4's config and pull and rc0's protocols are restored on exit.  R_PIO is
powered and driven by our kernel, so /dev/mem access to it is safe; PL4 is
unclaimed in our DT (pinmux-pins: UNCLAIMED).
"""
import json, mmap, os, select, struct, sys, threading, time

R_PIO = 0x07022000
CFG0, DAT, PULL0 = 0x00, 0x10, 0x1C
PIN = 4                     # PL4
RC = "/sys/class/rc/rc0/protocols"
OUT = sys.argv[1] if len(sys.argv) > 1 else time.strftime("/root/standby-probe-%Y%m%d-%H%M%S")
SHORT = "--short" in sys.argv   # dry run: no operator windows

os.makedirs(OUT, exist_ok=True)
log_f = open(f"{OUT}/log.txt", "w")
t0 = time.monotonic()

def log(msg):
    line = f"{time.monotonic() - t0:8.3f} {msg}"
    print(line, flush=True)
    log_f.write(line + "\n"); log_f.flush()

def prompt(msg):
    log(f"PROMPT {msg}")
    try:
        with open("/dev/tty1", "w") as tty:
            tty.write("\033[2J\033[H\n\n\n" + "\n".join(f"    {l}" for l in msg.split("|")) + "\n")
    except OSError as e:
        log(f"tty1: {e}")

fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=R_PIO)
rd = lambda o: struct.unpack("<I", m[o:o + 4])[0]
def wr(o, v): m[o:o + 4] = struct.pack("<I", v)
def field(o, shift, width, val):
    v = rd(o); mask = ((1 << width) - 1) << shift
    wr(o, (v & ~mask) | (val << shift))
level = lambda: (rd(DAT) >> PIN) & 1
def set_pull(p): field(PULL0, PIN * 2, 2, p)

saved = {"cfg0": rd(CFG0), "pull0": rd(PULL0), "protocols": open(RC).read().strip()}
log(f"saved {saved}")
result = {"saved": {k: (hex(v) if isinstance(v, int) else v) for k, v in saved.items()}}

def restore():
    field(CFG0, PIN * 4, 4, (saved["cfg0"] >> (PIN * 4)) & 0xF)
    field(PULL0, PIN * 2, 2, (saved["pull0"] >> (PIN * 2)) & 3)
    try:
        with open(RC, "w") as f: f.write("lirc")    # leaves only [lirc], as before
    except OSError as e:
        log(f"restore protocols: {e}")
    log(f"restored cfg0={rd(CFG0):08x} pull0={rd(PULL0):08x} protocols={open(RC).read().strip()}")

# ---- IR readers (threads) -------------------------------------------------
stop = threading.Event()
ir_scans, raw_count = [], [0]

def read_event0():
    ev = os.open("/dev/input/event0", os.O_RDONLY | os.O_NONBLOCK)
    fmt = "llHHi"; sz = struct.calcsize(fmt)
    while not stop.is_set():
        if not select.select([ev], [], [], 0.2)[0]: continue
        data = os.read(ev, sz * 64)
        for i in range(0, len(data) - sz + 1, sz):
            _, _, typ, code, val = struct.unpack(fmt, data[i:i + sz])
            if typ == 4 and code == 4:     # EV_MSC / MSC_SCAN
                ir_scans.append((round(time.monotonic() - t0, 3), val & 0xFFFFFFFF))
                log(f"IR scancode 0x{val & 0xFFFFFFFF:x}")
    os.close(ev)

def read_lirc():
    lf = os.open("/dev/lirc0", os.O_RDONLY | os.O_NONBLOCK)
    with open(f"{OUT}/lirc-mode2.txt", "w") as out:
        while not stop.is_set():
            if not select.select([lf], [], [], 0.2)[0]: continue
            data = os.read(lf, 4 * 512)
            for i in range(0, len(data) - 3, 4):
                v = struct.unpack("<I", data[i:i + 4])[0]
                kind = {0x01: "pulse", 0x00: "space", 0x03: "timeout"}.get(v >> 24, f"t{v >> 24:x}")
                out.write(f"{time.monotonic() - t0:.6f} {kind} {v & 0xFFFFFF}\n")
                raw_count[0] += 1
    os.close(lf)

# ---- PL4 ------------------------------------------------------------------
def sample(n=200, dt=0.005):
    ones = 0
    for _ in range(n):
        ones += level(); time.sleep(dt)
    return ones, n

def button_window(secs, pull, label):
    set_pull(pull); time.sleep(0.05)
    edges, last, end = [], level(), time.monotonic() + secs
    log(f"{label}: pull={pull} start level={last}")
    while time.monotonic() < end:
        v = level()
        if v != last:
            edges.append((round(time.monotonic() - t0, 4), v))
            log(f"PL4 -> {v}")
            last = v
        time.sleep(0.002)
    return {"pull": pull, "edges": edges}

try:
    with open(RC, "w") as f: f.write("+nec +rc-5 +rc-6")
    log(f"protocols now {open(RC).read().strip()}")
    threads = [threading.Thread(target=t, daemon=True) for t in (read_event0, read_lirc)]
    for t in threads: t.start()

    prompt("STANDBY INPUT PROBE|HANDS OFF - measuring idle")
    field(CFG0, PIN * 4, 4, 0)           # PL4 -> input
    idle = {}
    for pull, name in ((0, "none"), (1, "up"), (2, "down")):
        set_pull(pull); time.sleep(0.05)
        idle[name] = sample()
        log(f"idle pull={name}: {idle[name][0]}/{idle[name][1]} high")
    result["idle"] = idle
    highs = {k: v[0] for k, v in idle.items()}
    driven = set(highs.values()) in ({0}, {200})   # same level whatever the pull
    result["driven"] = driven
    log(f"PL4 externally driven: {driven}")

    if SHORT:
        log("short run: skipping operator windows")
    else:
        windows = [(0, "button")] if driven else [(1, "button, pull-up"), (2, "button, pull-down")]
        result["button"] = []
        for i, (pull, label) in enumerate(windows):
            prompt(f"CASE BUTTON ({i + 1}/{len(windows)})|press SHORT, 3 times, ~2 s apart|do NOT hold it")
            result["button"].append(button_window(15, pull, label))
        set_pull(0)

        n0 = len(ir_scans)
        prompt("REMOTE: press POWER|3 times, ~2 s apart|point it at the projector")
        time.sleep(15)
        result["ir_power"] = ir_scans[n0:]
        n1 = len(ir_scans)
        prompt("REMOTE, slowly, once each:|UP  DOWN  LEFT  RIGHT  OK|BACK  HOME  MENU  VOL+  VOL-")
        time.sleep(30)
        result["ir_other"] = ir_scans[n1:]
    prompt("PROBE DONE - thank you")
finally:
    stop.set(); time.sleep(0.3)
    restore()
    result["raw_samples"] = raw_count[0]
    with open(f"{OUT}/result.json", "w") as f: json.dump(result, f, indent=1)
    log(f"wrote {OUT}/result.json")
