#!/usr/bin/env python3
"""Show a bounded HDMI1 V4L2 stream on the projector's existing KMS panel.

The target converts 640x480 NV16 to letterboxed 1280x720 BGR0 in userspace.
No display-driver or capture-register changes are made. The existing EDID/HPD
trial restores its temporary source connection after 30 seconds.
"""

import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PATTERN = Path("/tmp/h713-motion-pattern.mkv")
CONNECTOR = Path("/sys/class/drm/card1-HDMI-A-1")
SSH = ["ssh", "-F", "/dev/null", "-o", "BatchMode=yes",
       "-o", "ConnectTimeout=5", "root@192.168.4.1"]
KERNEL_VERSION = "#1 SMP Thu Sep 24 01:45:24 PDT 2026"


def run(argv, timeout=20):
    result = subprocess.run(argv, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{argv[0]} exited {result.returncode}: "
                           f"{result.stdout[-800:]} {result.stderr[-800:]}")
    return result.stdout


def remote(command, timeout=20):
    return run(SSH + [command], timeout)


def stop(proc):
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def primary_fb(state):
    match = re.search(r"(?ms)^plane\[\d+\]: plane-0\n(.*?)(?=^plane\[|^crtc\[|\Z)",
                      state)
    fb = re.search(r"(?m)^\s*fb=(\d+)$", match.group(1)) if match else None
    if not fb:
        raise RuntimeError("KMS primary-plane framebuffer was not reported")
    return int(fb.group(1))


def main():
    output = Path("/tmp") / ("h713-panel-preview-" +
                            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir()
    print(f"Logs: {output}", flush=True)
    if remote("uname -v").strip() != KERNEL_VERSION:
        raise RuntimeError("projector kernel differs from the validated V4L2 module")
    if (CONNECTOR / "status").read_text().strip() != "disconnected":
        raise RuntimeError("GPU test connector is not disconnected")
    if not PATTERN.is_file():
        print(run([sys.executable, str(HERE / "make-motion-pattern.py"),
                   str(PATTERN)], timeout=40).strip(), flush=True)
    print(run([sys.executable, str(HERE / "prepare-source3.py")],
              timeout=150).strip(), flush=True)
    remote("set -e; "
           "test \"$(cat /sys/class/video4linux/video1/name)\" = "
           "\"H713 HDMI1 ring capture\"; "
           "test \"$(cat /sys/module/h713_hdmi_v4l2/parameters/verify_full)\" = Y; "
           "test \"$(cat /sys/class/drm/card0-LVDS-1/status)\" = connected; "
           "test \"$(cat /sys/class/drm/card0-LVDS-1/modes | head -1)\" = 1280x720; "
           "test -f /sys/kernel/debug/dri/0/state; "
           "test -x /root/mmio-rw; test -x /usr/local/bin/mpv; "
           "command -v ffmpeg >/dev/null")
    kms_before = remote("cat /sys/kernel/debug/dri/0/state")
    (output / "kms-before.log").write_text(kms_before)
    scanout_before = remote("/root/mmio-rw r 5600178")
    (output / "scanout-before.log").write_text(scanout_before)

    player = None
    trial = None
    preview = None
    preview_result = None
    stamp = output.name
    ffmpeg_log = f"/tmp/{stamp}-ffmpeg.log"
    mpv_log = f"/tmp/{stamp}-mpv.log"
    command = (
        "timeout -s INT 21s bash -o pipefail -c '"
        "ffmpeg -nostdin -hide_banner -loglevel info "
        "-f v4l2 -input_format nv16 -video_size 640x480 -i /dev/video1 "
        "-fps_mode passthrough -frames:v 120 "
        "-vf scale=960:720:flags=fast_bilinear,pad=1280:720:160:0:black,format=bgr0 "
        f"-pix_fmt bgr0 -f rawvideo - 2>{ffmpeg_log} | "
        f"/usr/local/bin/mpv --no-config --no-audio --no-terminal --log-file={mpv_log} "
        "--vo=drm --drm-device=/dev/dri/card0 "
        "--demuxer=rawvideo --demuxer-rawvideo-w=1280 "
        "--demuxer-rawvideo-h=720 --demuxer-rawvideo-fps=10 "
        "--demuxer-rawvideo-mp-format=bgr0 -'")
    try:
        with (output / "trial.log").open("w") as trial_log:
            trial = subprocess.Popen(
                [sys.executable, str(HERE / "run-detection-trial.py"),
                 "--seconds", "30"], stdout=trial_log,
                stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if trial.poll() is not None:
                    raise RuntimeError("EDID/HPD trial ended before GPU output enabled")
                if ((CONNECTOR / "status").read_text().strip() == "connected" and
                        (CONNECTOR / "enabled").read_text().strip() == "enabled"):
                    break
                time.sleep(.1)
            else:
                raise RuntimeError("GPU HDMI output did not enable")
            with (output / "source-mpv.log").open("w") as player_log:
                player = subprocess.Popen(
                    ["mpv", "--no-config", "--no-audio", "--vo=gpu",
                     "--gpu-context=wayland", "--loop-file=inf", "--fullscreen",
                     "--fs-screen-name=HDMI-A-1", "--osc=no", "--osd-level=0",
                     "--no-input-default-bindings", str(PATTERN)],
                    stdout=player_log, stderr=subprocess.STDOUT)
                time.sleep(2)
                if player.poll() is not None:
                    raise RuntimeError("GPU source player exited early")
                preview = subprocess.Popen(SSH + [command],
                                           stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE, text=True)
                time.sleep(2)
                if preview.poll() is not None:
                    raise RuntimeError("panel preview exited early")
                kms_during = remote("cat /sys/kernel/debug/dri/0/state")
                (output / "kms-during.log").write_text(kms_during)
                scanout_during = remote("/root/mmio-rw r 5600178")
                (output / "scanout-during.log").write_text(scanout_during)
                out, err = preview.communicate(timeout=25)
                preview_result = preview.returncode
                (output / "preview-ssh.log").write_text(out + err)
                stop(player)
                player = None
            trial.wait(timeout=50)
            if trial.returncode:
                raise RuntimeError("EDID/HPD trial failed")
        (output / "target-ffmpeg.log").write_text(
            remote(f"cat {ffmpeg_log}"))
        (output / "target-mpv.log").write_text(
            remote(f"cat {mpv_log}"))
        kms_after = remote("cat /sys/kernel/debug/dri/0/state")
        (output / "kms-after.log").write_text(kms_after)
        scanout_after = remote("/root/mmio-rw r 5600178")
        (output / "scanout-after.log").write_text(scanout_after)
        trial_log = (output / "trial.log").read_text()
        if preview_result != 0:
            raise RuntimeError(f"panel preview exited {preview_result}")
        if 'peripheral_restored=1 mismatch=0' not in trial_log:
            raise RuntimeError("EDID/HPD restoration was not verified")
        fb_before, fb_during, fb_after = map(
            primary_fb, (kms_before, kms_during, kms_after))
        if fb_during == fb_before or fb_after != fb_before:
            raise RuntimeError("KMS primary framebuffer did not switch and restore")
        summary = {"preview_exit": preview_result,
                   "source_restored": True,
                   "primary_fb_before": fb_before,
                   "primary_fb_during": fb_during,
                   "primary_fb_after": fb_after,
                   "scanout_before": scanout_before.strip(),
                   "scanout_during": scanout_during.strip(),
                   "scanout_after": scanout_after.strip(),
                   "kms_state_during": str(output / "kms-during.log"),
                   "ffmpeg_log": str(output / "target-ffmpeg.log"),
                   "mpv_log": str(output / "target-mpv.log")}
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps(summary), flush=True)
    finally:
        stop(player)
        if preview is not None and preview.poll() is None:
            stop(preview)
        if trial is not None and trial.poll() is None:
            trial.wait(timeout=50)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        sys.exit(str(exc))
