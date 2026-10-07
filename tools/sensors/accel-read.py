#!/usr/bin/env python3
"""Read the H713 projector's accelerometer through IIO. RUNS ON THE BOARD.

The tilt sensor is a Silan SC7A20 on TWI1 at 0x18, driven by mainline st_accel
(kernel 0168). This finds it by IIO name, prints the raw axes, the axes in g
and the projector's tilt. The kernel's mount_matrix (measured, in 0168) maps
chip axes onto the projector frame seen from behind it: X right, Y up, Z back
toward the viewer, so the lens points along -Z.

  elev  lens elevation: 0 level, +90 pointing straight up
  roll  positive when the right side is raised
  ceiling   printed when Y is below -0.5 g (upside down)

  accel-read.py              one line per sample at 5 Hz until ^C
  accel-read.py -n 10        ten samples, then a mean
  accel-read.py --rate 25    sample rate in Hz
  accel-read.py --tag flat   prefix every line, for logs of a posed sequence
"""
import argparse
import glob
import math
import os
import sys
import time

G = 9.80665


def find_device():
    for d in sorted(glob.glob("/sys/bus/iio/devices/iio:device*")):
        try:
            name = open(os.path.join(d, "name")).read().strip()
        except OSError:
            continue
        if "sc7a20" in name:
            return d, name
    return None, None


def read(path):
    with open(path) as f:
        return f.read().strip()


def mount_matrix(dev):
    path = os.path.join(dev, "mount_matrix")
    if not os.path.exists(path):
        return [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    return [[float(v) for v in row.split(",")] for row in read(path).split(";")]


def sample(dev, scale, mm):
    raw = [int(read(os.path.join(dev, f"in_accel_{a}_raw"))) for a in "xyz"]
    chip = [r * scale / G for r in raw]
    g = [sum(m * c for m, c in zip(row, chip)) for row in mm]
    return raw, g


def angles(g):
    x, y, z = g
    # Each axis's angle above the horizon: defined in every pose, unlike
    # Euler angles, which fall apart when the lens points straight up.
    elev = math.degrees(math.atan2(-z, math.hypot(x, y)))
    roll = math.degrees(math.atan2(x, math.hypot(y, z)))
    return elev, roll


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=0, help="samples (0 = forever)")
    ap.add_argument("--rate", type=float, default=5.0)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    dev, name = find_device()
    if not dev:
        sys.exit("no sc7a20 IIO device (kernel 0168 not booted, or probe failed: check dmesg | grep -i st_accel)")
    # st_accel exposes one scale per axis; they are always equal.
    scale = float(read(os.path.join(dev, "in_accel_x_scale")))
    mm = mount_matrix(dev)
    if args.n != 1:
        freq = read(os.path.join(dev, "sampling_frequency")) if os.path.exists(os.path.join(dev, "sampling_frequency")) else "?"
        print(f"# {dev} name={name} scale={scale} m/s^2/LSB odr={freq} Hz mount={mm}", flush=True)

    prefix = f"{args.tag} " if args.tag else ""
    sums = [0.0, 0.0, 0.0]
    i = 0
    try:
        while args.n == 0 or i < args.n:
            raw, g = sample(dev, scale, mm)
            p, r = angles(g)
            mag = math.sqrt(sum(v * v for v in g))
            print(f"{prefix}raw {raw[0]:6d} {raw[1]:6d} {raw[2]:6d}  "
                  f"g {g[0]:+.3f} {g[1]:+.3f} {g[2]:+.3f} |{mag:.3f}|  "
                  f"elev {p:+6.1f} roll {r:+6.1f}{' ceiling' if g[1] < -0.5 else ''}", flush=True)
            sums = [s + v for s, v in zip(sums, g)]
            i += 1
            time.sleep(1.0 / args.rate)
    except KeyboardInterrupt:
        pass
    if i > 1:
        m = [s / i for s in sums]
        p, r = angles(m)
        print(f"{prefix}mean of {i}: g {m[0]:+.3f} {m[1]:+.3f} {m[2]:+.3f}  elev {p:+6.1f} roll {r:+6.1f}")


if __name__ == "__main__":
    main()
