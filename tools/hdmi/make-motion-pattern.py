#!/usr/bin/env python3
"""Create a lossless 60 Hz HDMI test video with four frame-ID bands."""

import argparse
import subprocess
from pathlib import Path

import numpy as np

RATE = 60
COUNT = 256


def frame_bytes(index, width, height):
    frame = np.full((height, width, 3), 32, dtype=np.uint8)
    bands = (0, height * 3 // 10, height * 6 // 10, height * 9 // 10)
    cell = width // 10
    for top in bands:
        frame[top + 8:top + 40, 8:40] = 224
        for bit in range(8):
            left = cell + cell * bit
            shade = 224 if index & (1 << bit) else 32
            frame[top + 8:top + 40, left + 8:left + cell - 8] = shade
    left = index * 7 % width
    for top, bottom in zip((band + 48 for band in bands[:-1]), bands[1:]):
        frame[top:bottom, left:min(left + 16, width)] = 224
    if (width, height) == (1280, 720):
        frame[:, :4] = (224, 32, 32)
        frame[:, -4:] = (32, 224, 224)
    return frame.tobytes()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("output", type=Path)
    ap.add_argument("--width", type=int, choices=(640, 1280), default=640)
    ap.add_argument("--height", type=int, choices=(480, 720), default=480)
    args = ap.parse_args()
    if (args.width, args.height) not in ((640, 480), (1280, 720)):
        ap.error("supported formats are 640x480 and 1280x720")
    process = subprocess.Popen(
        ["ffmpeg", "-nostdin", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size",
         f"{args.width}x{args.height}", "-framerate", str(RATE), "-i", "pipe:0",
         "-c:v", "ffv1", "-level", "3", "-pix_fmt", "yuv444p",
         str(args.output)], stdin=subprocess.PIPE)
    assert process.stdin is not None
    try:
        for index in range(COUNT):
            process.stdin.write(frame_bytes(index, args.width, args.height))
    finally:
        process.stdin.close()
    if process.wait() != 0:
        raise SystemExit("FFmpeg failed to encode the motion pattern")
    print(f"{args.output}: {COUNT} {args.width}x{args.height} frames at {RATE} Hz")


if __name__ == "__main__":
    main()
