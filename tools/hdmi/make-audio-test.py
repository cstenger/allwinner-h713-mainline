#!/usr/bin/env python3
"""Generate a deterministic 48 kHz, stereo, signed-16 HDMI audio test WAV."""

import argparse
import math
import struct
import wave
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seconds", type=float, default=8.0)
    parser.add_argument("--amplitude", type=float, default=0.20)
    args = parser.parse_args()
    if not 0.25 <= args.seconds <= 30:
        parser.error("--seconds must be between 0.25 and 30")
    if not 0 < args.amplitude <= 0.5:
        parser.error("--amplitude must be greater than zero and at most 0.5")

    rate = 48_000
    frames = round(rate * args.seconds)
    scale = round(32767 * args.amplitude)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(args.output), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(rate)
        chunk = bytearray()
        for index in range(frames):
            left = round(scale * math.sin(2 * math.pi * 1000 * index / rate))
            right = round(scale * math.sin(2 * math.pi * 2000 * index / rate))
            chunk += struct.pack("<hh", left, right)
            if len(chunk) >= 65536:
                output.writeframesraw(chunk)
                chunk.clear()
        output.writeframes(chunk)
    print(f"{args.output}: {frames} frames, 48000 Hz, stereo S16_LE, L=1 kHz R=2 kHz")


if __name__ == "__main__":
    main()
