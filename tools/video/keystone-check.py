#!/usr/bin/env python3
"""Check keystone.lua's matrices against an independent projection model.
RUNS ON THE HOST, on the selftest lines keystone.lua prints on the target:

  ssh root@BOARD 'mpv --no-config --vo=null --ao=null --idle=yes \
      --script=/usr/local/share/h713/keystone.lua \
      --script-opts=keystone-selftest=yes' | tools/video/keystone-check.py

For each matrix (frame position -> picture position), invert it to find where
the picture's corners and centre land in the frame, then cast those frame
positions through the lens as rays -- written here from the geometry, not
copied from the Lua -- onto a wall at unit distance from a projector pitched
by the given angle. The picture must land as an axis-aligned rectangle with
the video's aspect, wholly inside the frame, standing on the frame's near
edge (or touching both sides, when letterboxing makes it the width that binds).
"""
import math
import re
import sys

TOL = 1e-6


def inv3(m):
    a, b, c = m[0]
    d, e, f = m[1]
    g, h, i = m[2]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    return [[(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
            [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
            [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det]]


def apply(m, x, y):
    p = [m[r][0] * x + m[r][1] * y + m[r][2] for r in range(3)]
    return p[0] / p[2], p[1] / p[2]


def wall(u, v, deg, s, tb, tt):
    """Where frame position (u, v) lands on a vertical wall 1 unit ahead."""
    # The ray leaves the lens in the projector's frame: right, up, forward.
    x = s * (2 * u - 1)
    y = tt + (tb - tt) * v
    z = 1.0
    # Pitch the projector up by deg: forward turns toward up.
    a = math.radians(deg)
    y, z = y * math.cos(a) + z * math.sin(a), -y * math.sin(a) + z * math.cos(a)
    assert z > 0, "ray misses the wall"
    return x / z, y / z


def check(deg, s, tb, tt, va, M):
    inv = inv3(M)
    corners = {}
    for name, (pu, pv) in {"tl": (0, 0), "tr": (1, 0), "br": (1, 1), "bl": (0, 1), "c": (0.5, 0.5)}.items():
        u, v = apply(inv, pu, pv)
        if not (-TOL <= u <= 1 + TOL and -TOL <= v <= 1 + TOL):
            return f"{name} lands outside the frame at ({u:.4f}, {v:.4f})"
        corners[name] = (u, v, *wall(u, v, deg, s, tb, tt))
    tl, tr, br, bl, c = (corners[k] for k in ("tl", "tr", "br", "bl", "c"))
    errs = []
    if abs(tl[2] - bl[2]) > 1e-5 or abs(tr[2] - br[2]) > 1e-5:
        errs.append("sides not vertical")
    if abs(tl[3] - tr[3]) > 1e-5 or abs(bl[3] - br[3]) > 1e-5:
        errs.append("top/bottom not level")
    w, h = tr[2] - tl[2], tl[3] - bl[3]
    if abs(w / h - va) > 1e-4:
        errs.append(f"aspect {w / h:.4f}, want {va:.4f}")
    if abs(c[2] - (tl[2] + tr[2]) / 2) > 1e-5 or abs(c[3] - (tl[3] + bl[3]) / 2) > 1e-5:
        errs.append("centre not at the rectangle's centre")
    # Largest possible: a picture with the panel's own aspect fills the
    # corrected rectangle, which stands on the near (narrow) edge of the
    # frame, corner to corner -- the bottom row when pitched up.
    pa = s / (tt - tb) * 2
    if abs(va - pa) < 1e-3:
        a, b = (bl, br) if deg >= 0 else (tl, tr)
        row = 1.0 if deg >= 0 else 0.0
        if max(abs(a[1] - row), abs(b[1] - row), abs(a[0]), abs(b[0] - 1)) > 1e-5:
            errs.append(f"not standing on the near edge: ({a[0]:.4f}, {a[1]:.4f}) to ({b[0]:.4f}, {b[1]:.4f})")
    return "; ".join(errs) or None, (w, h)


def main():
    n = bad = 0
    pat = re.compile(r"selftest (\S+) (\S+) (\S+) (\S+) (\S+) (\S+)")
    for line in sys.stdin:
        m = pat.search(line)
        if not m:
            continue
        deg, s, tb, tt, va = map(float, m.groups()[:5])
        kv = dict(x.split("=") for x in m.group(6).split(","))
        M = [[float(kv[f"k{r}{c}"]) for c in range(3)] for r in range(3)]
        res = check(deg, s, tb, tt, va, M)
        err, (w, h) = res if isinstance(res, tuple) else (res, (0, 0))
        n += 1
        if err:
            bad += 1
        print(f"{'FAIL' if err else 'ok  '} pitch {deg:+5.1f}  aspect {va:.3f}  picture {w:.4f} x {h:.4f}" + (f"  {err}" if err else ""))
    print(f"{n - bad} of {n} matrices land as the right rectangle")
    sys.exit(1 if bad or not n else 0)


if __name__ == "__main__":
    main()
