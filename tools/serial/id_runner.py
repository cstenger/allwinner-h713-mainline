#!/usr/bin/env python3
"""Run the ID_AA64PFR0_EL1 field probes on the H713 board.

Each probe resets INSTANTLY (~1.3s) if its EL field advertises AArch32
(value >= 2), or after a multi-second delay if AArch64-only. Both
outcomes reset the board, so probes self-recover to the prompt.
"""
import os, sys, time, subprocess

SP = os.path.dirname(os.path.abspath(__file__))
A32 = os.path.join(SP, "a32test")
USBDEV = "/sys/bus/usb/devices/1-4"

def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)

def acm(cmd, timeout=8, wait_prompt=True):
    args = ["python3", os.path.join(SP, "acm.py"), cmd, "--timeout", str(timeout)]
    if not wait_prompt:
        args.append("--no-wait-prompt")
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout+20).stdout

def ymodem(path):
    r = subprocess.run(["python3", os.path.join(SP, "ymodem_send.py"), path],
                       capture_output=True, text=True, timeout=180)
    return r.stdout + r.stderr

def present():
    return os.path.exists(USBDEV)

def wait_gone(deadline, t0):
    while time.time() - t0 < deadline:
        if not present():
            return time.time() - t0
        time.sleep(0.05)
    return None

def wait_back(deadline, t0):
    while time.time() - t0 < deadline:
        if present():
            return time.time() - t0
        time.sleep(0.1)
    return None

def prompt_ok(tries=3):
    for _ in range(tries):
        if "U-Boot 2026" in acm("version", timeout=6):
            return True
        time.sleep(4)
    return False

def recover(label):
    t0 = time.time()
    if wait_back(25, t0) is None:
        log("%s: never re-enumerated -> DEAD" % label); return False
    time.sleep(13)
    if prompt_ok():
        log("%s: prompt OK" % label); return True
    log("%s: NO PROMPT (cold wedge?)" % label); return False

def main():
    if not prompt_ok():
        log("no prompt at start; aborting"); sys.exit(1)

    probes = [
        ("id-el1", "ID_AA64PFR0_EL1.EL1 (our EL2->EL1-A32 target)"),
        ("id-el0", "ID_AA64PFR0_EL1.EL0 (AArch32 userspace)"),
        ("id-el2", "ID_AA64PFR0_EL1.EL2 (AArch32 at Hyp)"),
    ]
    results = []
    for name, desc in probes:
        log("=== %s: %s ===" % (name, desc))
        out = acm("loady 0x50000000", timeout=3, wait_prompt=False)
        if "Ready for binary" not in out:
            log("loady failed"); results.append((name, "LOADY-FAIL")); break
        y = ymodem(os.path.join(A32, name + ".fit"))
        if "Total Size" not in y:
            log("ymodem failed: %r" % y[-160:]); results.append((name, "YMODEM-FAIL")); break
        # insurance: proven 3s armed wdog (in case a probe hangs unexpectedly)
        acm("wdt dev watchdog@2051000", timeout=5)
        t0 = time.time()
        acm("bootm 0x50000000", timeout=4, wait_prompt=False)
        tg = wait_gone(40, t0)
        if tg is None:
            log("%s: NO RESET in 40s -> HANG (unexpected for ID probe)" % name)
            results.append((name, "HANG")); break
        verdict = "AArch32 SUPPORTED (field>=2)" if tg < 2.6 else "AArch64-ONLY (field<2)"
        log("%s: reset t+%.1fs -> %s" % (name, tg, verdict))
        results.append((name, "%.1fs %s" % (tg, verdict)))
        if not recover(name):
            results.append(("(recovery)", "FAILED")); break

    log("=== ID PROBE RESULTS ===")
    for n, r in results:
        log("  %-8s %s" % (n, r))

if __name__ == "__main__":
    main()
