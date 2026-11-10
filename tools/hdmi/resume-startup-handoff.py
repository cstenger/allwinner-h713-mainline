#!/usr/bin/env python3
"""Resume a guarded cold autoboot that stopped only at the FDT handoff command.

For the 2026-10-14 bare-PID failure: launch, source-3 CALL and trace guards
passed, then `fdt set /chosen h713,hdmi-boot-v1` rejected the PID. Everything
needed for Linux is already in RAM (FIT 0x50000000, patched FDT 0x4f000000).

Read-only checks first; any mismatch stops before a single write. Then only
the corrected handoff property is written and read back. `bootm` runs only
with --boot. Never reruns hdmi_source/hdmi_launch/bootcmd or touches RTC GP6.
"""
import argparse
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "serial"))
import console  # noqa: E402

FDT = "0x4f000000"
IRQ = "<0x00000000 0x00000073 0x00000004 0x00000000 0x00000071 0x00000004>"


class Uboot:
    def __init__(self, port, log):
        self.fd = console.open_port(port)
        self.log = log

    def cmd(self, text, wait=1.5):
        console.write_slow(self.fd, text.encode() + b"\n")
        time.sleep(0.3)
        out = console.drain(self.fd, wait, echo=False).decode("utf-8", "replace")
        self.log.write(out)
        self.log.flush()
        if not out.rstrip().endswith("=>"):
            raise RuntimeError(f"no U-Boot prompt after {text!r}")
        return out


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def word(out, addr):
    match = re.search(rf"^{addr:08x}: ([0-9a-f]{{8}})", out, re.M)
    require(match, f"no readback of {addr:#x}")
    return int(match.group(1), 16)


def check(u):
    env = dict(re.findall(r"^(hdmi_\w+)=(\S*)", u.cmd("printenv hdmi_pid hdmi_count hdmi_bad hdmi_ccu"), re.M))
    require(env.get("hdmi_count") == "1" and env.get("hdmi_bad") == "0", f"channel census not 1/0: {env}")
    require(re.fullmatch(r"[0-9a-f]{1,8}", env.get("hdmi_pid", "")) and int(env["hdmi_pid"], 16), "hdmi_pid missing/zero")
    pid = int(env["hdmi_pid"], 16)
    require(word(u.cmd("md.l 0x0306101c 1"), 0x0306101c) == 1, "MIPS status is not exactly 1")
    require(word(u.cmd("md.l 0x07090118 1"), 0x07090118) == 0x48444d49, "RTC GP6 launch latch not set")
    trace = u.cmd("h713_disp commtrace")
    require("H713 source 3: callback-event0=1 worker-event0=1 transition-complete=1 "
            "worker-old=00000000 worker-new=00000003" in trace, "source-3 trace is not the completed transition")
    guards = {0x4d980004: 0x434f4d4d, 0x4d980080: 0x43414e31, 0x4d980ffc: 0x43414e31,
              0x4d980078: 3, 0x4d98007c: 1}
    for addr, want in guards.items():
        require(word(u.cmd(f"md.l {addr:#x} 1"), addr) == want, f"trace guard {addr:#x} mismatch")
    live = re.findall(r"chan=(\w+) pid=(\w+) .*<== LIVE", u.cmd("h713_disp commdev"))
    require(live == [("0000", f"{pid:08x}")], f"live channel table {live} does not match hdmi_pid {pid:08x}")
    u.cmd(f"fdt addr {FDT}")
    require(IRQ in u.cmd("fdt print /soc/audio-bridge@203042c interrupts"), "audio-bridge IRQ fix absent")
    ccu = int(env["hdmi_ccu"], 16)
    node = u.cmd("fdt print /soc/hdmi-mips-shutdown")
    require("h713,hdmi-mips-shutdown-bench" in node, "shutdown consumer missing")
    c = f"0x{ccu:08x}"
    require(f"resets = <{c} 0x00000001 {c} 0x00000002 {c} 0x00000003>" in node, "shutdown resets mismatch")
    require(f"clocks = <{c} 0x00000013 {c} 0x00000014>" in node, "shutdown clocks mismatch")
    require("hdmi-boot-v1" not in u.cmd("fdt list /chosen"), "handoff property already present")
    u.cmd("iminfo 0x50000000", wait=4)
    return pid


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("log", type=Path, help="new serial transcript file")
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--boot", action="store_true", help="after all checks, write the handoff and bootm")
    args = ap.parse_args()
    with args.log.open("x") as log:
        u = Uboot(args.port, log)
        try:
            pid = check(u)
            print(f"all read-only guards passed; pid={pid:08x}", flush=True)
            if not args.boot:
                return 0
            u.cmd(f"fdt set /chosen h713,hdmi-boot-v1 <0x48444d49 0 0x{pid:x}>")
            got = u.cmd("fdt print /chosen h713,hdmi-boot-v1")
            require(f"<0x48444d49 0x00000000 0x{pid:08x}>" in got, "handoff readback mismatch; not booting")
            print("handoff written and read back; booting prepared image", flush=True)
            console.write_slow(u.fd, f"bootm 0x50000000 - {FDT}\n".encode())
            log.write(console.drain(u.fd, 8, echo=False).decode("utf-8", "replace"))
            return 0
        except RuntimeError as error:
            print(f"STOPPED: {error}", file=sys.stderr)
            return 1
        finally:
            os.close(u.fd)


if __name__ == "__main__":
    raise SystemExit(main())
