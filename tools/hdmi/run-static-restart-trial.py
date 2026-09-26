#!/usr/bin/env python3
"""Validate static-image startup and repeated V4L2 stream reopen.

The traced U-Boot completion hook must already be active.  The trial presents
one unchanging image during a bounded HPD window, captures short streams in
both sparse and full verification modes, and requires every reopen to deliver
complete frames without rejection.  It restores full verification on exit.
"""

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
STATIC_IMAGE = Path("/tmp/h713-static-source.png")
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


def load_module(digest, full):
    remote("set -e; "
           "if test -d /sys/module/h713_hdmi_v4l2; then "
           "rmmod h713_hdmi_v4l2; fi; "
           f"test \"$(sha256sum /tmp/h713-hdmi-v4l2.ko | cut -d' ' -f1)\" = {digest}; "
           f"insmod /tmp/h713-hdmi-v4l2.ko verify_full={int(full)}; "
           "test \"$(cat /sys/class/video4linux/video1/name)\" = "
           "\"H713 HDMI1 ring capture\"")


def capture_restarts(output, mode, count):
    prefix = f"/tmp/{output.name}-{mode}"
    command = [
        "set -e",
        f"rm -f {prefix}-*.nv16",
    ]
    for index in range(1, count + 1):
        path = f"{prefix}-{index}.nv16"
        command.extend([
            f"timeout -s KILL 6s dd if=/dev/video1 of={path} "
            "bs=614400 count=8 iflag=fullblock status=none",
            f"test \"$(stat -c %s {path})\" = {8 * FRAME_SIZE}",
            "sleep 0.25",
        ])
    command.append(
        "python3 -c 'import glob,hashlib,json; "
        f"fs=sorted(glob.glob(\"{prefix}-*.nv16\")); "
        "z=[]; "
        "[(lambda b,p: z.append({\"file\":p,\"bytes\":len(b),"
        "\"frame_hashes\":[hashlib.sha256(b[o:o+614400]).hexdigest() "
        "for o in range(0,len(b),614400)]}))(open(p,\"rb\").read(),p) "
        "for p in fs]; print(json.dumps(z))'"
    )
    records = json.loads(remote("; ".join(command), timeout=60))
    if len(records) != count:
        raise RuntimeError(f"{mode}: expected {count} captures, got {len(records)}")
    for record in records:
        hashes = record["frame_hashes"]
        record["unique_frame_hashes"] = len(set(hashes))
        if record["bytes"] != 8 * FRAME_SIZE or len(hashes) != 8:
            raise RuntimeError(f"{mode}: short capture: {record}")
    return records


def main():
    output = Path("/tmp") / ("h713-static-restart-" +
                             datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir()
    print(f"Logs: {output}", flush=True)
    if not MODULE.is_file():
        raise RuntimeError(f"build the matching module first: {MODULE}")
    if remote("uname -v").strip() != EXPECTED_KERNEL_VERSION:
        raise RuntimeError("the running projector kernel does not match the module")
    print(run([sys.executable, str(HERE / "prepare-source3.py")],
              timeout=150).strip(), flush=True)
    run(["ffmpeg", "-nostdin", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "color=c=0x204060:s=640x480:r=1",
         "-frames:v", "1", str(STATIC_IMAGE)])
    digest = hashlib.sha256(MODULE.read_bytes()).hexdigest()
    run(SCP + [str(MODULE), "root@192.168.4.1:/tmp/h713-hdmi-v4l2.ko"])
    load_module(digest, full=False)

    trial = player = None
    try:
        with (output / "signal-trial.log").open("w") as log:
            trial = subprocess.Popen(
                [sys.executable, str(HERE / "run-detection-trial.py"),
                 "--seconds", "30"], stdout=log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if trial.poll() is not None:
                    raise RuntimeError("signal trial ended before HDMI enabled")
                if ((CONNECTOR / "status").read_text().strip() == "connected" and
                        (CONNECTOR / "enabled").read_text().strip() == "enabled"):
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("GPU HDMI output did not enable")

            with (output / "mpv.log").open("w") as log:
                player = subprocess.Popen(
                    ["mpv", "--no-config", "--no-audio", "--vo=gpu",
                     "--gpu-context=wayland", "--fullscreen",
                     "--fs-screen-name=HDMI-A-1", "--osc=no", "--osd-level=0",
                     "--no-input-default-bindings", "--image-display-duration=inf",
                     str(STATIC_IMAGE)], stdout=log, stderr=subprocess.STDOUT)
                time.sleep(3)
                if player.poll() is not None:
                    raise RuntimeError("static-image player exited early")
                dmesg_start = int(remote("dmesg | wc -l").strip())
                sparse = capture_restarts(output, "sparse", 5)
                load_module(digest, full=True)
                full = capture_restarts(output, "full", 3)
                dmesg = remote(
                    f"dmesg | tail -n +{dmesg_start + 1} | "
                    "grep 'h713-hdmi-v4l2: stream'", timeout=20)
                (output / "driver-streams.log").write_text(dmesg)
                summaries = []
                for line in dmesg.splitlines():
                    delivered = re.search(r" delivered=(\d+) ", line)
                    if (delivered and int(delivered.group(1)) >= 8 and
                            " unstable=0 " in line and " rejected=0 " in line):
                        summaries.append(line)
                if len(summaries) != 8:
                    raise RuntimeError(
                        f"expected eight clean stream summaries, got {len(summaries)}")
                result = {"module_sha256": digest, "static_source": True,
                          "sparse": sparse, "full": full,
                          "clean_stream_summaries": len(summaries)}
                (output / "analysis.json").write_text(
                    json.dumps(result, indent=2) + "\n")
                print(json.dumps({"sparse_restarts": len(sparse),
                                  "full_restarts": len(full),
                                  "clean_stream_summaries": len(summaries),
                                  "unique_frames_per_stream":
                                  [r["unique_frame_hashes"]
                                   for r in sparse + full]}), flush=True)
                player.terminate()
                player.wait(timeout=5)
                player = None
            trial.wait(timeout=45)
            if trial.returncode:
                raise RuntimeError("bounded signal trial failed")
    finally:
        if player is not None and player.poll() is None:
            player.terminate()
            try:
                player.wait(timeout=5)
            except subprocess.TimeoutExpired:
                player.kill()
        if trial is not None and trial.poll() is None:
            trial.wait(timeout=45)
        try:
            load_module(digest, full=True)
        except (RuntimeError, subprocess.TimeoutExpired) as error:
            print(f"warning: full-verification restore failed: {error}",
                  file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        sys.exit(str(error))
