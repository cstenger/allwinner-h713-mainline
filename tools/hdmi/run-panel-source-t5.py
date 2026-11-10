#!/usr/bin/env python3
"""Host runner for T5 (docs/hdmi-panel-source-design-2026-10-23.md section 10.14).

The sequence itself is tools/hdmi/t5-board.py, run on the board as the
transient unit h713-t5 so its revert never depends on this ssh session.

    run-panel-source-t5.py stage            # copy t5-board.py to /run/h713-t5, verify hash
    run-panel-source-t5.py check            # board-side preconditions, reads only
    run-panel-source-t5.py run --output DIR --confirm-t5
    run-panel-source-t5.py revert           # the revert alone, any time

Add --with-nr to check/run/revert for T6 (section 10.16): NR history DMA
(agents 5/6) on before agent 4, off after it.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOARD = HERE / "t5-board.py"
REMOTE = "/run/h713-t5/t5-board.py"
SSH = ["ssh", "-F", "/dev/null", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "root@192.168.4.1"]


def ssh(cmd, timeout=60, **kw):
    return subprocess.run(SSH + [cmd], capture_output=True, text=True, timeout=timeout, **kw)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=("stage", "check", "run", "revert"))
    ap.add_argument("--output", type=Path)
    ap.add_argument("--confirm-t5", action="store_true")
    ap.add_argument("--with-nr", action="store_true")
    ap.add_argument("--matrix", action="store_true", help="Test 2 (10.23.2): routing x format cells after stage B")
    ap.add_argument("--hold-b", type=float, help="stage B hold, 15..120 s (the board checks the bound)")
    a = ap.parse_args()
    want = hashlib.sha256(BOARD.read_bytes()).hexdigest()
    if a.mode == "stage":
        p = ssh(f"mkdir -p /run/h713-t5 && cat > {REMOTE} && sha256sum {REMOTE}", input=BOARD.read_text())
        ok = p.stdout.split()[:1] == [want]
        print(p.stdout.strip(), "OK" if ok else "HASH MISMATCH")
        return 0 if ok else 1
    got = ssh(f"sha256sum {REMOTE}").stdout.split()[:1]
    if got != [want]:
        raise SystemExit(f"staged t5-board.py {got} != {want[:12]}; run stage")
    nr = " --with-nr" if a.with_nr else ""
    hold = f" --hold-b {a.hold_b:g}" if a.hold_b else ""
    hold += " --matrix" if a.matrix else ""
    if a.mode == "check":
        p = ssh(f"python3 {REMOTE} check{nr}")
        print(p.stdout, p.stderr, end="")
        return p.returncode
    if a.mode == "revert":
        p = ssh(f"python3 {REMOTE} revert{nr}")
        print(p.stdout, p.stderr, end="")
        return p.returncode
    if not (a.confirm_t5 and a.output):
        raise SystemExit("run needs --output DIR and --confirm-t5")
    a.output.mkdir(parents=True, exist_ok=False)
    (a.output / "board-script.sha256").write_text(want + "\n")
    since = ssh("date +%s").stdout.strip()
    p = ssh(f"systemd-run --unit=h713-t5 --collect --property=Type=exec python3 -u {REMOTE} run --confirm-t5{nr}{hold}")
    (a.output / "start.txt").write_text(p.stdout + p.stderr)
    if p.returncode:
        raise SystemExit("systemd-run failed: " + p.stderr)
    started = time.time()
    while time.time() - started < 120 + (a.hold_b or 0) + (120 if a.matrix else 0):
        time.sleep(2)
        if ssh("systemctl is-active h713-t5").stdout.strip() not in ("active", "activating"):
            break
    # only this run: the unit name is reused, and the journal keeps earlier runs
    log = ssh(f"journalctl -o cat -u h713-t5 --since @{since} --no-pager", timeout=30).stdout
    (a.output / "events.jsonl").write_text(log)
    events = [json.loads(l) for l in log.splitlines() if l.startswith("{")]
    done = [e for e in events if e["ev"] == "done"]
    print(json.dumps({"done": done[-1] if done else None,
                      "aborts": [e for e in events if e["ev"] in ("abort", "refused")]}, indent=1))
    return 0 if done and done[-1]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
