#!/usr/bin/env python3
"""Check keystone.lua's matrices against an independent projection model.
RUNS ON THE HOST, on the selftest lines keystone.lua prints on the target:

  ssh root@BOARD 'mpv --no-config --vo=null --ao=null --idle=yes \
      --script=/usr/local/share/h713/keystone.lua \
      --script-opts=keystone-selftest=yes' | tools/video/keystone-check.py

Each line gives a pose (pitch, roll, yaw, upside down, mirror mode), a lens and a
video aspect, and the 3x3 matrix keystone.lua made (frame position ->
picture position). Independently of the Lua:

  * the projector's attitude is built from Euler angles -- a roll about the
    lens axis, then a pitch about the world's horizontal -- solved
    numerically to give the published pitch/roll (the Lua builds it from the
    up vector by Gram-Schmidt), then turned right by the yaw trim about the
    world's vertical (the Lua turns the wall instead);
  * the display mirror is applied to panel positions, not as a matrix;
  * the wall is the plane square to the lens's horizontal direction.

The picture's corners and centre, pulled back through the inverse matrix,
must lie in the frame and land on the wall as a level rectangle with the
video's aspect, oriented the way the unwarped frame lands (its top where the
frame's top points, its left where the frame's left points: upright for front
and ceiling, mirrored for the rear modes). A picture with the panel's aspect
must also be the largest level rectangle that fits: no smaller than a
brute-force search finds.
"""
import math
import re
import sys


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


def matvec(m, v):
    return [sum(m[r][c] * v[c] for c in range(3)) for r in range(3)]


def matmul(a, b):
    return [[sum(a[r][k] * b[k][c] for k in range(3)) for c in range(3)] for r in range(3)]


def rot_lens(g):    # about the lens (forward) axis
    c, s = math.cos(g), math.sin(g)
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]


def rot_pitch(e):   # forward turns toward up by e
    c, s = math.cos(e), math.sin(e)
    return [[1, 0, 0], [0, c, s], [0, -s, c]]


def rot_yaw(a):    # about the world vertical: forward turns to the right
    c, s = math.cos(a), math.sin(a)
    return [[c, 0, s], [0, 1, 0], [-s, 0, c]]


def published(Q):
    """The daemon's pitch, roll and upside-down flag for attitude Q."""
    # Up in projector coordinates (right, up, forward): Q^T (0, 1, 0).
    gx, gy, gf = Q[1][0], Q[1][1], Q[1][2]
    inv = gy < 0
    sgn = -1 if inv else 1
    pitch = math.degrees(math.atan2(gf * sgn, abs(gy)))
    roll = math.degrees(math.atan2(gx, math.hypot(gy, gf)))
    return pitch, roll, inv


def attitude(pitch, roll, inv):
    """Solve Euler angles so the daemon would publish (pitch, roll, inv)."""
    best = None
    for gi in range(-180, 180, 2):
        for ei in range(-80, 81, 2):
            Q = matmul(rot_pitch(math.radians(ei)), rot_lens(math.radians(gi)))
            p, r, i = published(Q)
            if i != inv:
                continue
            err = (p - pitch) ** 2 + (r - roll) ** 2
            if best is None or err < best[0]:
                best = (err, math.radians(ei), math.radians(gi))
    _, e, g = best
    step = math.radians(1)
    while step > 1e-12:
        moved = False
        for de, dg in ((step, 0), (-step, 0), (0, step), (0, -step)):
            Q = matmul(rot_pitch(e + de), rot_lens(g + dg))
            p, r, i = published(Q)
            err = (p - pitch) ** 2 + (r - roll) ** 2
            if i == inv and err < best[0]:
                best, e, g, moved = (err, e + de, g + dg), e + de, g + dg, True
        if not moved:
            step /= 2
    assert best[0] < 1e-16, f"attitude not found for {pitch}, {roll}, {inv}"
    return matmul(rot_pitch(e), rot_lens(g))


class Projector:
    def __init__(self, Q, mode, s, tb, tt):
        self.Q, self.mode, self.s, self.tb, self.tt = Q, mode, s, tb, tt

    def wall(self, u, v):
        """Where frame position (u, v) lands: the display mirrors, then the lens."""
        if self.mode & 1:
            u = 1 - u
        if self.mode & 2:
            v = 1 - v
        ray = [self.s * (2 * u - 1), self.tt - (self.tt - self.tb) * v, 1.0]
        X, Y, Z = matvec(self.Q, ray)
        assert Z > 0, "ray misses the wall"
        return X / Z, Y / Z


def inside(poly, x, y):
    sign = 0
    for i in range(len(poly)):
        (ax, ay), (bx, by) = poly[i], poly[(i + 1) % len(poly)]
        c = (bx - ax) * (y - ay) - (by - ay) * (x - ax)
        if abs(c) < 1e-12:
            continue
        if sign == 0:
            sign = 1 if c > 0 else -1
        elif (c > 0) != (sign > 0):
            return False
    return True


def brute_largest(quad, ar):
    """Largest level rectangle of height/width ar in quad, by grid search."""
    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]
    best = 0.0
    N = 48
    for i in range(1, N):
        for j in range(1, N):
            cx = min(xs) + (max(xs) - min(xs)) * i / N
            cy = min(ys) + (max(ys) - min(ys)) * j / N
            if not inside(quad, cx, cy):
                continue
            lo, hi = best, max(xs) - min(xs)
            def fits(w):
                h = w * ar
                return all(inside(quad, cx + dx * w / 2, cy + dy * h / 2) for dx in (-1, 1) for dy in (-1, 1))
            if not fits(lo):
                continue
            for _ in range(40):
                mid = (lo + hi) / 2
                lo, hi = (mid, hi) if fits(mid) else (lo, mid)
            best = lo
    return best


def check(pitch, roll, yaw, inv, mode, s, tb, tt, va, M):
    proj = Projector(matmul(rot_yaw(math.radians(yaw)), attitude(pitch, roll, inv)), mode, s, tb, tt)
    inv_m = inv3(M)
    pts = {}
    for name, (pu, pv) in {"tl": (0, 0), "tr": (1, 0), "br": (1, 1), "bl": (0, 1), "c": (0.5, 0.5)}.items():
        u, v = apply(inv_m, pu, pv)
        if not (-1e-6 <= u <= 1 + 1e-6 and -1e-6 <= v <= 1 + 1e-6):
            return f"{name} lands outside the frame at ({u:.4f}, {v:.4f})", None
        pts[name] = proj.wall(u, v)
    tl, tr, br, bl, c = (pts[k] for k in ("tl", "tr", "br", "bl", "c"))
    errs = []
    tol = 1e-5
    if abs(tl[0] - bl[0]) > tol or abs(tr[0] - br[0]) > tol:
        errs.append("sides not vertical")
    if abs(tl[1] - tr[1]) > tol or abs(bl[1] - br[1]) > tol:
        errs.append("top/bottom not level")
    w, h = abs(tr[0] - tl[0]), abs(tl[1] - bl[1])
    if h == 0 or abs(w / h - va) > 1e-4:
        errs.append(f"aspect {w / h if h else 0:.4f}, want {va:.4f}")
    if abs(c[0] - (tl[0] + tr[0]) / 2) > tol or abs(c[1] - (tl[1] + bl[1]) / 2) > tol:
        errs.append("centre off")
    # Orientation: as the unwarped frame lands.
    f_up = proj.wall(0.5, 0.25)[1] - proj.wall(0.5, 0.75)[1]
    f_right = proj.wall(0.75, 0.5)[0] - proj.wall(0.25, 0.5)[0]
    if (tl[1] - bl[1]) * f_up <= 0:
        errs.append("upside down relative to the frame")
    if (tr[0] - tl[0]) * f_right <= 0:
        errs.append("mirrored relative to the frame")
    # Largest: only a picture with the panel's aspect fills its rectangle.
    pa = 2 * s / (tt - tb)
    if abs(va - pa) < 1e-3:
        quad = [proj.wall(*p) for p in ((0, 0), (1, 0), (1, 1), (0, 1))]
        b = brute_largest(quad, 1 / pa)
        if w < b * (1 - 2e-3):
            errs.append(f"not the largest: width {w:.4f}, a {b:.4f} fits")
    return "; ".join(errs) or None, (w, h)


def line_dist(p, a, b):
    """Distance of p from the line through a and b."""
    return abs((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])) / math.dist(a, b)


def cross_point(a, b, c, d):
    """Where line ab meets line cd."""
    x1, y1, x2, y2, x3, y3, x4, y4 = *a, *b, *c, *d
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
    return x1 + t * (x2 - x1), y1 + t * (y2 - y1)


def check_corners(q, va, M):
    """Corner mode: the picture fills quad q (tl, tr, br, bl, frame 0..1)."""
    inv = inv3(M)
    tl, tr, br, bl = q
    pts = {k: apply(inv, *p) for k, p in {"tl": (0, 0), "tr": (1, 0), "br": (1, 1), "bl": (0, 1), "c": (0.5, 0.5)}.items()}
    errs = []
    tol = 1e-6
    # The picture's centre is where the quad's diagonals cross -- any
    # projective map takes the square's centre there, whatever the letterbox.
    if math.dist(pts["c"], cross_point(tl, br, tr, bl)) > tol:
        errs.append("centre is not where the diagonals cross")
    pa = 1280 / 720
    if abs(va - pa) < 1e-3:
        for k, want in zip(("tl", "tr", "br", "bl"), q):
            if math.dist(pts[k], want) > tol:
                errs.append(f"{k} at {pts[k][0]:.5f},{pts[k][1]:.5f}, want {want[0]:.5f},{want[1]:.5f}")
    elif va > pa:   # wide: letterboxed top and bottom, full width
        if max(line_dist(pts["tl"], tl, bl), line_dist(pts["bl"], tl, bl),
               line_dist(pts["tr"], tr, br), line_dist(pts["br"], tr, br)) > tol:
            errs.append("wide picture's sides are not on the quad's sides")
    else:           # narrow: pillarboxed left and right, full height
        if max(line_dist(pts["tl"], tl, tr), line_dist(pts["tr"], tl, tr),
               line_dist(pts["bl"], bl, br), line_dist(pts["br"], bl, br)) > tol:
            errs.append("narrow picture's top and bottom are not on the quad's")
    return "; ".join(errs) or None


def main():
    n = bad = 0
    pat = re.compile(r"selftest (\S+) (\S+) (\S+) (\S+) (\S+) (\S+) (\S+) (\S+) (\S+) (\S+)")
    cpat = re.compile(r"cornertest ((?:\S+ ){8})(\S+) (convex|crossed) (\S+)")
    for line in sys.stdin:
        cm = cpat.search(line)
        if cm:
            v = list(map(float, cm.group(1).split()))
            q = [(v[0], v[1]), (v[2], v[3]), (v[4], v[5]), (v[6], v[7])]
            va = float(cm.group(2))
            kv = dict(x.split("=") for x in cm.group(4).split(","))
            M = [[float(kv[f"k{r}{c}"]) for c in range(3)] for r in range(3)]
            err = check_corners(q, va, M)
            n += 1
            bad += bool(err)
            if err or "-v" in sys.argv:
                print(f"{'FAIL' if err else 'ok  '} corners {cm.group(1).strip()} aspect {va:.3f}" + (f"  {err}" if err else ""))
            continue
        m = pat.search(line)
        if not m:
            continue
        pitch, roll, yaw = float(m.group(1)), float(m.group(2)), float(m.group(3))
        inv, mode = m.group(4) == "1", int(m.group(5))
        s, tb, tt, va = map(float, m.group(6, 7, 8, 9))
        kv = dict(x.split("=") for x in m.group(10).split(","))
        M = [[float(kv[f"k{r}{c}"]) for c in range(3)] for r in range(3)]
        err, size = check(pitch, roll, yaw, inv, mode, s, tb, tt, va, M)
        n += 1
        bad += bool(err)
        if err or "-v" in sys.argv:
            what = f"pitch {pitch:+5.1f} roll {roll:+4.1f} yaw {yaw:+5.1f} {'inv' if inv else 'up '} mode {mode} lens {tb:+.3f} aspect {va:.3f}"
            print(f"{'FAIL' if err else 'ok  '} {what}" + (f"  {err}" if err else f"  picture {size[0]:.4f} x {size[1]:.4f}"))
    print(f"{n - bad} of {n} matrices land as the right rectangle")
    sys.exit(1 if bad or not n else 0)


if __name__ == "__main__":
    main()
