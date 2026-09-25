#!/usr/bin/env python3
"""Create a lossless 60 Hz HDMI test video with four frame-ID bands."""

import argparse
import subprocess
from pathlib import Path

import numpy as np

WIDTH = 640
HEIGHT = 480
RATE = 60
COUNT = 256
BANDS = (0, 144, 288, 432)


def frame_bytes(index):
    frame = np.full((HEIGHT, WIDTH, 3), 32, dtype=np.uint8)
    for top in BANDS:
        frame[top + 8:top + 40, 8:40] = 224
        for bit in range(8):
            left = 64 + 64 * bit
            shade = 224 if index & (1 << bit) else 32
            frame[top + 8:top + 40, left + 8:left + 56] = shade
    left = index * 7 % WIDTH
    for top, bottom in ((48, 144), (192, 288), (336, 432)):
        frame[top:bottom, left:min(left + 16, WIDTH)] = 224
    return frame.tobytes()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()
    process = subprocess.Popen(
        ["ffmpeg", "-nostdin", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size",
         f"{WIDTH}x{HEIGHT}", "-framerate", str(RATE), "-i", "pipe:0",
         "-c:v", "ffv1", "-level", "3", "-pix_fmt", "yuv444p",
         str(args.output)], stdin=subprocess.PIPE)
    assert process.stdin is not None
    try:
        for index in range(COUNT):
            process.stdin.write(frame_bytes(index))
    finally:
        process.stdin.close()
    if process.wait() != 0:
        raise SystemExit("FFmpeg failed to encode the motion pattern")
    print(f"{args.output}: {COUNT} frames at {RATE} Hz")


if __name__ == "__main__":
    main()
