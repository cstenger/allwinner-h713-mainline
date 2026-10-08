#!/usr/bin/env python3
"""How hot does the SoC get in standby with the fan off?

PB5 is the light's boost-converter enable AND the fan's power, so a lamp-off
standby is also a fan-off standby. This holds PB5 low (behind the kernel's
gpio-hog), caps the CPU at its lowest OPP, and logs both thermal zones every
10 s. It restores PB5 high and the CPU cap at the end, on any exception, on
SIGTERM, and at once if either zone reaches ABORT_C.

  usage: thermal-fan-off.py [SECONDS] [OUTFILE]      (default 900 s)

Runs on the board as root. The projector goes dark for the duration.
Main PIO is the new register layout: bank B at +0x30, DAT at +0x10.
"""
import mmap, os, signal, struct, sys, time

SECS = int(sys.argv[1]) if len(sys.argv) > 1 else 900
OUT = sys.argv[2] if len(sys.argv) > 2 else time.strftime("/root/thermal-fan-off-%Y%m%d-%H%M%S.log")
ABORT_C = 70.0
PB_DAT, PB5 = 0x30 + 0x10, 5
CPUFREQ = "/sys/devices/system/cpu/cpufreq/policy0"
ZONES = sorted(z for z in os.listdir("/sys/class/thermal") if z.startswith("thermal_zone"))

fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=0x02000000)
rd = lambda o: struct.unpack("<I", m[o:o + 4])[0]
def wr(o, v): m[o:o + 4] = struct.pack("<I", v)
def pb5(v): wr(PB_DAT, (rd(PB_DAT) & ~(1 << PB5)) | (v << PB5))

def temps():
    return [int(open(f"/sys/class/thermal/{z}/temp").read()) / 1000 for z in ZONES]

log_f = open(OUT, "w")
t0 = time.monotonic()
def log(msg):
    line = f"{time.monotonic() - t0:7.1f} {msg}"
    print(line, flush=True); log_f.write(line + "\n"); log_f.flush()

saved_max = open(f"{CPUFREQ}/scaling_max_freq").read().strip()
min_freq = open(f"{CPUFREQ}/cpuinfo_min_freq").read().strip()
assert (rd(PB_DAT) >> PB5) & 1, "PB5 is not high at start"

def restore(*_):
    pb5(1)
    open(f"{CPUFREQ}/scaling_max_freq", "w").write(saved_max)
    log(f"restored PB5={(rd(PB_DAT) >> PB5) & 1} max_freq={saved_max} temps={temps()}")
    sys.exit(0)
signal.signal(signal.SIGTERM, restore)

try:
    log(f"start temps={temps()} zones={ZONES}")
    open(f"{CPUFREQ}/scaling_max_freq", "w").write(min_freq)
    pb5(0)
    log(f"PB5 low, CPU capped at {min_freq} kHz, for {SECS}s, abort at {ABORT_C} C")
    end = time.monotonic() + SECS
    while time.monotonic() < end:
        t = temps()
        log(f"temps={t} cur_freq={open(f'{CPUFREQ}/scaling_cur_freq').read().strip()}")
        if max(t) >= ABORT_C:
            log("ABORT: over limit"); break
        time.sleep(10)
finally:
    restore()
