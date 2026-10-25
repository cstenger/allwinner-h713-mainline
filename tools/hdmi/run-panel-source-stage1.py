#!/usr/bin/env python3
"""Host runner for stage 1 (read-only) of the HDMI panel-source design.

docs/hdmi-panel-source-design-2026-10-23.md section 10.1.  Every board-side
action is a read: the snapshot script opens /dev/mem read-only and the
staged copies live in /run (gone at reboot).  The only state this changes
is the host's own HDMI output, through cosmic-randr, which is how the
NO_SIGNAL state is produced.

    run-panel-source-stage1.py preflight
    run-panel-source-stage1.py snap LABEL          # e.g. locked, nosignal, relocked
    run-panel-source-stage1.py host-output off|on
    run-panel-source-stage1.py report

Raw elog dumps (2 MiB each) go to local/hdmi-stage1/<run>/ (not in git);
metadata, register dumps, port caches and the report go to
docs/hdmi-evidence/2026-10-23-panel-source-stage1/.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import io
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/hdmi-evidence/2026-10-23-panel-source-stage1"
RAW = ROOT / "local/hdmi-stage1/2026-10-23"
STOCK = ROOT / "docs/hdmi-evidence/2026-10-07-android-audio/locked-elog/elog.bin"
SSH = ["ssh", "-F", "/dev/null", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
       "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=2", "root@192.168.4.1"]
STAGE = "/run/h713-stage1"
FILES = [ROOT / "tools/hdmi/panel-source-snapshot.py",
         ROOT / "tools/display/letterbox-baseline.py",
         ROOT / "tools/hdmi/read-mips-port-cache.py"]
CONNECTOR = Path("/sys/class/drm/card1-HDMI-A-1")


def ssh(cmd, data=None, timeout=60):
    p = subprocess.run(SSH + [cmd], input=data, capture_output=True, timeout=timeout)
    if p.returncode:
        raise SystemExit(f"ssh failed ({p.returncode}): {cmd}\n{p.stderr.decode(errors='replace')}")
    return p.stdout


def host_connector():
    return {k: (CONNECTOR / k).read_text().strip() for k in ("status", "enabled")}


def log(event):
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    event = {"time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **event}
    with open(EVIDENCE / "events.jsonl", "a") as f:
        f.write(json.dumps(event) + "\n")
    print(json.dumps(event))


def preflight():
    out = ssh("cat /proc/sys/kernel/random/boot_id; cut -d' ' -f1 /proc/uptime; "
              "test -e /proc/device-tree/chosen/h713,hdmi-boot-v1 && echo handoff || echo no-handoff; "
              "systemctl is-active h713-hdmi-capture h713-hdmi-signal h713-hdmi-speaker; "
              "cat /sys/module/h713_hdmi_signal/parameters/ready 2>&1").decode().split()
    log({"event": "preflight", "board": out, "host": host_connector()})


def snap(label):
    tar = io.BytesIO()
    with tarfile.open(fileobj=tar, mode="w") as t:
        for f in FILES:
            t.add(f, arcname=f.name)
    ssh(f"rm -rf {STAGE} && mkdir -p {STAGE} && tar -x -C {STAGE}", data=tar.getvalue())
    host_before = host_connector()
    meta = ssh(f"python3 {STAGE}/panel-source-snapshot.py {STAGE}/out {label}", timeout=90)
    blob = ssh(f"tar -c -C {STAGE}/out .", timeout=60)
    dest = EVIDENCE / label
    raw = RAW / label
    for d in (dest, raw):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
    sums = {}
    with tarfile.open(fileobj=io.BytesIO(blob)) as t:
        for m in t.getmembers():
            if not m.isfile():
                continue
            data = t.extractfile(m).read()
            name = Path(m.name).name
            target = (raw if name.endswith(".bin") else dest) / name
            target.write_bytes(data)
            sums[name] = hashlib.sha256(data).hexdigest()
    (dest / "sha256.json").write_text(json.dumps(sums, indent=1) + "\n")
    ssh(f"rm -rf {STAGE}")
    log({"event": "snap", "label": label, "host_before": host_before,
         "host_after": host_connector(), "meta": json.loads(meta)})


def host_output(state):
    subprocess.run(["cosmic-randr", "enable" if state == "on" else "disable", "HDMI-A-1"], check=True)
    time.sleep(3)
    log({"event": f"host-output {state}", "host": host_connector()})


def report():
    lines = []
    labels = sorted(p.name for p in RAW.iterdir() if p.is_dir())
    for label in labels:
        dumps = sorted(str(p) for p in (RAW / label).glob("*-elog-*.bin"))
        p = subprocess.run([sys.executable, str(ROOT / "tools/mips/elog-sequence-diff.py"),
                            str(STOCK), *dumps], text=True, capture_output=True)
        lines += [f"## {label}: firmware log against stock 10-07", "", "```",
                  p.stdout.rstrip() + p.stderr.rstrip(), "```", ""]
    regs = {}
    for label in labels:
        f = EVIDENCE / label / f"{label}-regs.txt"
        if f.exists():
            regs[label] = dict(l.split(" ", 1) for l in f.read_text().splitlines() if " " in l)
    if len(regs) > 1:
        names = list(regs)
        keys = sorted(set().union(*regs.values()))
        changed = [k for k in keys if len({regs[n].get(k) for n in names}) > 1]
        lines += ["## Registers that differ between snapshots", "", "```",
                  "register " + " ".join(names)]
        lines += [f"{k} " + " ".join(regs[n].get(k, "-").split()[-1] for n in names) for k in changed]
        lines += ["```", ""]
    (EVIDENCE / "report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("preflight")
    s = sub.add_parser("snap"); s.add_argument("label")
    h = sub.add_parser("host-output"); h.add_argument("state", choices=["on", "off"])
    sub.add_parser("report")
    a = ap.parse_args()
    {"preflight": preflight, "report": report}.get(a.cmd, lambda: None)()
    if a.cmd == "snap":
        snap(a.label)
    elif a.cmd == "host-output":
        host_output(a.state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
