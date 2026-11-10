#!/usr/bin/env python3
"""Camera-gated direct-DRM display of a known 1280x720 color-bar frame."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BGR = Path("/tmp/h713-known-720-color-bars.bgr0")
SSH = ["ssh", "-F", "/dev/null", "-o", "BatchMode=yes", "-o",
       "ConnectTimeout=5", "root@192.168.4.1"]
SCP = ["scp", "-F", "/dev/null", "-o", "BatchMode=yes", "-o",
       "ConnectTimeout=5"]


def run(argv, timeout=30):
    result = subprocess.run(argv, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{argv[0]} exited {result.returncode}: "
                           f"{result.stdout[-1000:]} {result.stderr[-1000:]}")
    return result.stdout


def remote(command, timeout=30):
    return run(SSH + [command], timeout)


def primary_fb(state):
    match = re.search(r"(?ms)^plane\[\d+\]: plane-0\n(.*?)(?=^plane\[|^crtc\[|\Z)",
                      state)
    fb = re.search(r"(?m)^\s*fb=(\d+)$", match.group(1)) if match else None
    if not fb:
        raise RuntimeError("KMS primary-plane framebuffer was not reported")
    return int(fb.group(1))


def restore_console():
    remote("echo 0 > /sys/class/graphics/fb0/blank; "
           "test \"$(cat /sys/class/graphics/fb0/blank)\" = 0")


def iommu_fault_count():
    output = remote(
        "dmesg | awk '/sun50i-iommu .*Page fault/{count++} "
        "END{print count+0}'").strip()
    return int(output)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--camera-ready", action="store_true")
    args = ap.parse_args()
    if not args.camera_ready:
        ap.error("stop and obtain operator confirmation before the visible run")

    output = Path("/tmp") / ("h713-panel-bgr-diagnostic-" +
                             datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir()
    print(f"Logs: {output}", flush=True)
    run(["ffmpeg", "-nostdin", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "smptebars=size=1280x720:rate=1",
         "-frames:v", "1", "-pix_fmt", "bgr0",
         "-f", "rawvideo", str(BGR)])
    if BGR.stat().st_size != 1280 * 720 * 4:
        raise RuntimeError("known BGR0 frame has the wrong size")
    digest = hashlib.sha256(BGR.read_bytes()).hexdigest()
    (output / "bgr0-sha256.txt").write_text(digest + "\n")
    run(SCP + [str(BGR), "root@192.168.4.1:/tmp/h713-known-720-color-bars.bgr0"])
    remote(f"test \"$(sha256sum /tmp/h713-known-720-color-bars.bgr0 | cut -d' ' -f1)\" = {digest}")

    kms_before = remote("cat /sys/kernel/debug/dri/0/state")
    scanout_before = remote("/root/mmio-rw r 5600178").strip()
    faults_before = iommu_fault_count()
    fb_before = primary_fb(kms_before)
    (output / "kms-before.log").write_text(kms_before)
    command = (
        "timeout -s INT 8s /usr/local/bin/mpv --no-config --no-audio "
        "--no-terminal --loop-file=inf --vo=drm --drm-device=/dev/dri/card0 "
        "--demuxer=rawvideo --demuxer-rawvideo-w=1280 "
        "--demuxer-rawvideo-h=720 --demuxer-rawvideo-fps=1 "
        "--demuxer-rawvideo-mp-format=bgr0 /tmp/h713-known-720-color-bars.bgr0")
    player = subprocess.Popen(SSH + [command], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True)
    try:
        time.sleep(2)
        if player.poll() is not None:
            raise RuntimeError("direct DRM marker player exited early")
        kms_during = remote("cat /sys/kernel/debug/dri/0/state")
        scanout_during = remote("/root/mmio-rw r 5600178").strip()
        fb_during = primary_fb(kms_during)
        (output / "kms-during.log").write_text(kms_during)
        out, err = player.communicate(timeout=12)
        (output / "mpv.log").write_text(out + err)
    finally:
        if player.poll() is None:
            player.terminate()
            player.wait(timeout=5)
        restore_console()
    kms_after = remote("cat /sys/kernel/debug/dri/0/state")
    scanout_after = remote("/root/mmio-rw r 5600178").strip()
    faults_after = iommu_fault_count()
    fb_after = primary_fb(kms_after)
    (output / "kms-after.log").write_text(kms_after)
    result = {"camera_ready": True, "bgr0_sha256": digest,
              "primary_fb_before": fb_before, "primary_fb_during": fb_during,
              "primary_fb_after": fb_after, "scanout_before": scanout_before,
              "scanout_during": scanout_during, "scanout_after": scanout_after,
              "iommu_faults_before": faults_before,
              "iommu_faults_after": faults_after}
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)
    if fb_during == fb_before or fb_after != fb_before:
        raise RuntimeError("KMS framebuffer did not switch and restore")
    if scanout_during == scanout_before or scanout_after != scanout_before:
        raise RuntimeError("hardware scanout address did not switch and restore")
    if faults_after != faults_before:
        raise RuntimeError("display test introduced an IOMMU fault")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        sys.exit(str(exc))
