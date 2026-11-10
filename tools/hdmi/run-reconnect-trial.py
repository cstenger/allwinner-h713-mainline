#!/usr/bin/env python3
"""Exercise repeated HDMI disconnect/reconnect without reloading the driver.

The guarded cap-vde trace must already be active. Each cycle asserts the
bounded EDID/HPD window, presents the deterministic motion pattern, captures a
short V4L2 stream, then waits through the driver's no-frame timeout. Ring-hash
phase learning is disabled so every reconnect must bootstrap from AFBD votes.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MODULE = ROOT / "build/hdmi-v4l2/h713-hdmi-v4l2.ko"
PATTERN = Path("/tmp/h713-motion-pattern.mkv")
CONNECTOR = Path("/sys/class/drm/card1-HDMI-A-1")
SSH = ["ssh", "-F", "/dev/null", "-o", "BatchMode=yes",
       "-o", "ConnectTimeout=5", "root@192.168.4.1"]
SCP = ["scp", "-F", "/dev/null", "-o", "BatchMode=yes",
       "-o", "ConnectTimeout=5"]
EXPECTED_KERNEL_VERSION = "#1 SMP Thu Sep 24 01:45:24 PDT 2026"
FRAME_SIZE = 640 * 480 * 2


def run(argv, timeout=30):
    result = subprocess.run(argv, text=True, capture_output=True,
                            timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{argv[0]} exited {result.returncode}: "
                           f"{result.stdout[-1200:]} {result.stderr[-1200:]}")
    return result.stdout


def remote(command, timeout=30):
    return run(SSH + [command], timeout)


def connector_state():
    return ((CONNECTOR / "status").read_text().strip(),
            (CONNECTOR / "enabled").read_text().strip())


def load_module(digest, full, phase_from_hash):
    remote("set -e; "
           "if test -d /sys/module/h713_hdmi_v4l2; then "
           "rmmod h713_hdmi_v4l2; fi; "
           f"test \"$(sha256sum /tmp/h713-hdmi-v4l2.ko | cut -d' ' -f1)\" = {digest}; "
           f"insmod /tmp/h713-hdmi-v4l2.ko verify_full={int(full)} "
           f"phase_from_hash={int(phase_from_hash)}; "
           "test \"$(cat /sys/class/video4linux/video1/name)\" = "
           "\"H713 HDMI1 ring capture\"")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cycles", type=int, choices=range(2, 11), default=3)
    ap.add_argument("--frames", type=int, choices=range(8, 61), default=30)
    args = ap.parse_args()
    output = Path("/tmp") / ("h713-reconnect-trial-" +
                             datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir()
    print(f"Logs: {output}", flush=True)
    if not MODULE.is_file():
        raise RuntimeError(f"build the matching module first: {MODULE}")
    if remote("uname -v").strip() != EXPECTED_KERNEL_VERSION:
        raise RuntimeError("the running projector kernel does not match the module")
    if connector_state() != ("disconnected", "disabled"):
        raise RuntimeError("GPU test connector is not disconnected and disabled")
    print(run([sys.executable, str(HERE / "make-motion-pattern.py"),
               str(PATTERN)]).strip(), flush=True)
    print(run([sys.executable, str(HERE / "prepare-source3.py")],
              timeout=150).strip(), flush=True)
    digest = hashlib.sha256(MODULE.read_bytes()).hexdigest()
    run(SCP + [str(MODULE), "root@192.168.4.1:/tmp/h713-hdmi-v4l2.ko"])
    load_module(digest, full=False, phase_from_hash=False)
    dmesg_start = int(remote("dmesg | wc -l").strip())
    analyses = []

    try:
        for cycle in range(1, args.cycles + 1):
            trial = player = None
            try:
                trial_log = (output / f"cycle-{cycle:02d}-signal.log").open("w")
                trial = subprocess.Popen(
                    [sys.executable, str(HERE / "run-detection-trial.py"),
                     "--seconds", "15"], stdout=trial_log,
                    stderr=subprocess.STDOUT)
                deadline = time.monotonic() + 12
                while time.monotonic() < deadline:
                    if trial.poll() is not None:
                        raise RuntimeError(f"cycle {cycle}: signal trial exited early")
                    if connector_state() == ("connected", "enabled"):
                        break
                    time.sleep(0.1)
                else:
                    raise RuntimeError(f"cycle {cycle}: GPU output did not enable")

                player_log = (output / f"cycle-{cycle:02d}-mpv.log").open("w")
                player = subprocess.Popen(
                    ["mpv", "--no-config", "--no-audio", "--vo=gpu",
                     "--gpu-context=wayland", "--loop-file=inf", "--fullscreen",
                     "--fs-screen-name=HDMI-A-1", "--osc=no", "--osd-level=0",
                     "--no-input-default-bindings", str(PATTERN)],
                    stdout=player_log, stderr=subprocess.STDOUT)
                time.sleep(2)
                if player.poll() is not None:
                    raise RuntimeError(f"cycle {cycle}: player exited early")
                remote_raw = f"/tmp/{output.name}-cycle-{cycle:02d}.nv16"
                remote("timeout -s KILL 8s dd if=/dev/video1 "
                       f"of={remote_raw} bs={FRAME_SIZE} count={args.frames} "
                       "iflag=fullblock status=none", timeout=12)
                player.terminate()
                player.wait(timeout=5)
                player = None
                player_log.close()
                trial.wait(timeout=30)
                trial_log.close()
                if trial.returncode:
                    raise RuntimeError(f"cycle {cycle}: bounded signal trial failed")

                local_raw = output / f"cycle-{cycle:02d}.nv16"
                run(SCP + [f"root@192.168.4.1:{remote_raw}", str(local_raw)],
                    timeout=40)
                if local_raw.stat().st_size != args.frames * FRAME_SIZE:
                    raise RuntimeError(f"cycle {cycle}: short capture")
                analysis = json.loads(run(
                    [sys.executable, str(HERE / "analyze-motion-stream.py"),
                     str(local_raw)], timeout=20))
                (output / f"cycle-{cycle:02d}-analysis.json").write_text(
                    json.dumps(analysis, indent=2) + "\n")
                local_raw.unlink()
                remote(f"rm -f {remote_raw}")
                if (analysis["patterned_frames"] != args.frames or
                        analysis["band_mismatches"] or
                        analysis["stripe_mismatches"]):
                    raise RuntimeError(f"cycle {cycle}: frame-integrity failure")
                analyses.append(analysis)
                time.sleep(4)
                if connector_state() != ("disconnected", "disabled"):
                    raise RuntimeError(f"cycle {cycle}: connector did not restore")
                print(json.dumps({"cycle": cycle,
                                  "sequential_steps": analysis["sequential_steps"],
                                  "duplicate_steps": analysis["duplicate_steps"],
                                  "skipped_steps": analysis["skipped_steps"]}),
                      flush=True)
            finally:
                if player is not None and player.poll() is None:
                    player.terminate()
                    try:
                        player.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        player.kill()
                if trial is not None and trial.poll() is None:
                    trial.wait(timeout=30)

        dmesg = remote(
            f"dmesg | tail -n +{dmesg_start + 1} | "
            "grep -E 'h713-hdmi-v4l2: (stream|learned completion phase)'",
            timeout=20)
        (output / "driver.log").write_text(dmesg)
        learned = re.findall(r"learned completion phase offset=(\d+) from AFBD votes "
                             r"(\d+)/(\d+)/(\d+)", dmesg)
        streams = [line for line in dmesg.splitlines()
                   if "stream polls=" in line and " unstable=0 " in line and
                   " rejected=0 " in line]
        if len(learned) != args.cycles:
            raise RuntimeError(f"expected {args.cycles} AFBD learns, got {len(learned)}")
        if len(streams) != args.cycles:
            raise RuntimeError(f"expected {args.cycles} clean streams, got {len(streams)}")
        result = {"module_sha256": digest, "cycles": args.cycles,
                  "frames_per_cycle": args.frames, "afbd_learns": learned,
                  "clean_stream_summaries": len(streams),
                  "analyses": analyses}
        (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps({"cycles": args.cycles,
                          "afbd_learns": learned,
                          "clean_stream_summaries": len(streams)}), flush=True)
    finally:
        try:
            load_module(digest, full=True, phase_from_hash=True)
        except (RuntimeError, subprocess.TimeoutExpired) as error:
            print(f"warning: full-verification restore failed: {error}",
                  file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        sys.exit(str(error))
