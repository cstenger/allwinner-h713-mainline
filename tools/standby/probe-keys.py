#!/usr/bin/env python3
"""Operator-timed check of the decoded inputs, after kernel 0169/0170: the
case button as a gpio-keys KEY_POWER, the remote as NEC scancodes from rc0.
Prompts go to the panel console (tty1). Runs on the board as root.

  usage: probe-keys.py [OUTDIR] [--short]
"""
import glob, json, os, select, struct, sys, time

OUT = next((a for a in sys.argv[1:] if not a.startswith("--")),
           time.strftime("/root/standby-keys-%Y%m%d-%H%M%S"))
SHORT = "--short" in sys.argv
RC = "/sys/class/rc/rc0/protocols"
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

devs = {}
for p in sorted(glob.glob("/sys/class/input/event*")):
    name = open(f"{p}/device/name").read().strip()
    devs[name] = "/dev/input/" + os.path.basename(p)
log(f"input devices {devs}")
need = {"gpio-keys": devs.get("gpio-keys"), "sunxi-ir": devs.get("sunxi-ir")}
missing = [k for k, v in need.items() if not v]
if missing:
    log(f"MISSING {missing}"); sys.exit(1)

saved = open(RC).read().strip()
if "[nec]" not in saved:
    with open(RC, "w") as f: f.write("+nec")
log(f"protocols {open(RC).read().strip()} (were {saved})")

fds = {os.open(path, os.O_RDONLY | os.O_NONBLOCK): name for name, path in need.items()}
FMT = "llHHi"; SZ = struct.calcsize(FMT)
events = []

def window(secs, label):
    log(f"window {label} {secs}s")
    end = time.monotonic() + secs
    while (left := end - time.monotonic()) > 0:
        for fd in select.select(list(fds), [], [], left)[0]:
            data = os.read(fd, SZ * 64)
            for i in range(0, len(data) - SZ + 1, SZ):
                _, _, typ, code, val = struct.unpack(FMT, data[i:i + SZ])
                if typ == 4 and code == 4:          # MSC_SCAN
                    e = (label, fds[fd], "scan", hex(val & 0xFFFFFFFF))
                elif typ == 1:                      # EV_KEY
                    e = (label, fds[fd], "key", code, val)
                else:
                    continue
                events.append((round(time.monotonic() - t0, 3),) + e)
                log(f"{fds[fd]} {e[2:]}")

try:
    if SHORT:
        window(2, "idle")
    else:
        prompt("CASE BUTTON|press SHORT, 3 times, ~2 s apart")
        window(12, "case")
        prompt("REMOTE: POWER x3, then UP x1|~2 s apart")
        window(15, "power-up")
        for name in ("MIRROR (two squares)", "INPUT (arrow into box)",
                     "MOUSE", "MUTE (speaker with x)"):
            prompt(f"REMOTE: {name}|press it ONCE")
            window(7, name.split()[0].lower())
    prompt("DONE - thank you")
finally:
    if "[nec]" not in saved:            # only undo what we changed
        with open(RC, "w") as f: f.write("-nec")
    log(f"protocols now {open(RC).read().strip()}")
    json.dump(events, open(f"{OUT}/events.json", "w"), indent=1)
    log(f"wrote {OUT}/events.json")
