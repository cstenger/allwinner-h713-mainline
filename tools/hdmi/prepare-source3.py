#!/usr/bin/env python3
"""Reach the known-good HDMI1 diagnostic state from a fresh Linux boot.

Run only after a physical cold power-on. If MIPS is already live, this script
verifies the source-3 trace and finishes module setup without launching it
again. It never flashes storage or changes the installed kernel.
"""

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SSH = ["ssh", "-F", "/dev/null", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
       "root@192.168.4.1"]
SERIAL = ROOT / "tools/serial"


def run(argv, timeout=60):
    p = subprocess.run(argv, text=True, capture_output=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError(f"{argv[0]} exited {p.returncode}: {p.stderr or p.stdout}")
    return p.stdout


def remote(command, timeout=20):
    return run(SSH + [command], timeout)


def serial(*commands, wait=0.8, timeout=30):
    return run([sys.executable, str(SERIAL / "console.py"), "--port", "/dev/ttyUSB0",
                "--wait", str(wait), *commands], timeout)


def require_trace():
    out = remote("python3 /root/hdmi-safe-trace/read-comm-trace-worker.py")
    if not all(token in out for token in ('"guards":"43414e31/43414e31"',
                                     '"source3_transition_complete":1',
                                     '"source3_worker_new":"00000003"')):
        raise RuntimeError(f"MIPS source-3 trace is absent or invalid: {out[-1000:]}")
    print("MIPS source 3 and trace canaries verified", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--postboot-only", action="store_true",
                    help="Only verify live MIPS and prepare Linux modules")
    args = ap.parse_args()
    state = remote("python3 -u /root/mips-shell.py --status")
    if "MIPS core      ALIVE" in state:
        require_trace()
    elif "MIPS core      parked" in state and not args.postboot_only:
        print("MIPS parked; warm-rebooting to the validated U-Boot trace", flush=True)
        out = run([sys.executable, str(SERIAL / "reboot-to-uboot.py"),
                   "/dev/ttyUSB0", "23"], timeout=35)
        if not re.search(r"=>\s*$", out):
            raise RuntimeError("U-Boot prompt not reached; no MIPS command sent")
        out = serial("h713_disp mips-comm-trace 0x34",
                     "h713_disp commcall eaf13de5 chan=0 pid=8b8f275c 3",
                     "h713_disp commtrace", timeout=30)
        if not all(token in out for token in ("firmware identity accepted",
                                              "CALL_ACK", "RETURN_ACK",
                                              "source 3: callback-event0=1 worker-event0=1 transition-complete=1")):
            raise RuntimeError(f"Source-3 trace failed; leaving board at U-Boot: {out[-1800:]}")
        print("U-Boot source-3 transition complete; booting default kernel", flush=True)
        serial("run bootcmd", wait=8, timeout=40)
        for _ in range(20):
            try:
                require_trace()
                break
            except (RuntimeError, subprocess.TimeoutExpired):
                time.sleep(2)
        else:
            raise RuntimeError("Linux did not return with a valid source-3 trace")
    else:
        raise RuntimeError("MIPS state is not a verified parked/live state; leaving board unchanged")

    remote("set -e; test -f /root/hdmi-diagnostic-merged/h713-hdmi-power.ko; "
           "test -f /root/hdmi-diagnostic-merged/h713-edid-clock.ko; "
           "test -f /root/hdmi-diagnostic-merged/h713-ddc-pins.ko; "
           "test -f /root/hdmi-diagnostic-merged/h713-scp-probe.ko; "
           "set -- $(modinfo -F vermagic /root/hdmi-diagnostic-merged/h713-hdmi-power.ko); "
           "test \"$1\" = \"$(uname -r)\"; "
           "cp /root/hdmi-diagnostic-merged/h713-ddc-pins.ko /tmp/; "
           "cp /root/hdmi-diagnostic-merged/h713-scp-probe.ko /tmp/; "
           "if ! test -d /sys/module/h713_hdmi_power; then "
           "insmod /root/hdmi-diagnostic-merged/h713-hdmi-power.ko domain_count=2 clock_count=0; fi; "
           "test \"$(cat /sys/devices/h713-hdmi-tvfe/power/runtime_status)\" = active; "
           "test \"$(cat /sys/devices/h713-hdmi-tvcap/power/runtime_status)\" = active")
    for n in range(1, 5):
        remote(f"set -e; current=$(cat /sys/module/h713_hdmi_power/parameters/clock_count); "
               f"if test \"$current\" -lt {n}; then echo {n} > "
               "/sys/module/h713_hdmi_power/parameters/clock_count; fi; "
               "timeout 5s python3 -u /root/mips-shell.py --cmd 'help win' "
               f">/tmp/h713-mips-clock-{n}.log; "
               f"grep -q 'VS:/' /tmp/h713-mips-clock-{n}.log")
    remote("set -e; if ! test -d /sys/module/h713_edid_clock; then "
           "insmod /root/hdmi-diagnostic-merged/h713-edid-clock.ko; fi; "
           "test -L /sys/bus/platform/devices/h713-edid-clock-hold/driver")
    print("Ready: source 3, MIPS responsive, TVFE/TVCAP and four clocks held, EDID clock on", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        sys.exit(str(e))
