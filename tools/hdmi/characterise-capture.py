#!/usr/bin/env python3
"""Characterise the HDMI capture front end, per input mode, from the pristine ring.

docs/hdmi-panel-source-design-2026-10-23.md section 10.23.1 (Test 1).  For
each mode the host offers on HDMI-A-1: set it (cosmic-randr), wait for the
board to lock, take the reference (what the host actually sends: a
screenshot cropped to HDMI-A-1, the full screenshot deleted at once), read
the board's state and one ring frame (tools/hdmi/capture-probe-board.py, read
only, copied twice), time the ring cadence, and measure:

  geometry   ring w x h vs the input mode; stride from row correlation
  scaling    PSNR / row map of the ring against the reference at ring size
  csc        least-squares RGB -> Y/Cb/Cr fit on flat patches, nearest of
             BT.601 / BT.709 x full / limited
  chroma     horizontal chroma shift (half-pixel steps) against the reference
  vertical   row map y -> s*y+o for Y and for C (1:1 expected for 4:2:2)
  interlace  fraction of identical adjacent line pairs (line doubling) and a
             comb index
  cadence    ring slot changes per second vs the mode's refresh

The host mode is restored in a finally block.  Nothing on the board is
written; the only state change is the host's own HDMI output mode.

    characterise-capture.py run --out DIR [--modes 1280x720@60 ...] [--chart FILE]
    characterise-capture.py plan                  # modes it would use, nothing touched
    characterise-capture.py analyse DIR           # re-run the analysis on saved data
    characterise-capture.py --self-test           # offline, on held data + synthetics
"""
import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUTPUT = "HDMI-A-1"
SSH = ["ssh", "-F", "/dev/null", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "root@192.168.4.1"]
PROBE = HERE / "capture-probe-board.py"
STANDARDS = {  # (Kr, Kb)
    "BT.601": (0.299, 0.114),
    "BT.709": (0.2126, 0.0722),
}


# ---- matrices -----------------------------------------------------------------

def matrix(std, limited):
    """3x4 [R G B 1] -> [Y Cb Cr] in 8-bit code values, inputs 0..255."""
    kr, kb = STANDARDS[std]
    kg = 1 - kr - kb
    ys, cs, yo = (219 / 255, 224 / 255, 16) if limited else (1.0, 1.0, 0)
    y = np.array([kr, kg, kb]) * ys
    cb = np.array([-kr, -kg, 1 - kb]) / (2 * (1 - kb)) * cs
    cr = np.array([1 - kr, -kg, -kb]) / (2 * (1 - kr)) * cs
    return np.array([[*y, yo], [*cb, 128], [*cr, 128]])


def rgb_to_ycc(rgb, m):
    flat = rgb.reshape(-1, 3).astype(float)
    out = flat @ m[:, :3].T + m[:, 3]
    return np.clip(out, 0, 255).reshape(rgb.shape)


def nv16_from_rgb(rgb, m):
    """Synthesise an NV16 frame (Y plane, interleaved CbCr plane) from RGB."""
    ycc = rgb_to_ycc(rgb, m)
    y = np.round(ycc[..., 0]).astype(np.uint8)
    cb = ycc[..., 1].reshape(rgb.shape[0], -1, 2).mean(2)
    cr = ycc[..., 2].reshape(rgb.shape[0], -1, 2).mean(2)
    c = np.empty((rgb.shape[0], rgb.shape[1]), np.uint8)
    c[:, 0::2], c[:, 1::2] = np.round(cb), np.round(cr)
    return y, c


# ---- analysis -----------------------------------------------------------------

def detect_stride(buf, w, h, span):
    """Stride with the best adjacent-row correlation, among w..span (16-aligned and w)."""
    plane = np.frombuffer(buf, np.uint8)[:h * span]
    best = None
    for s in sorted({w, *range((w + 15) // 16 * 16, span + 1, 16)}):
        if s * h > len(plane):
            continue
        rows = plane[:s * h].reshape(h, s)[:, :w].astype(float)
        a, b = rows[:-1], rows[1:]
        score = np.mean(np.abs(a - b))
        if best is None or score < best[0]:
            best = (score, s)
    return best[1]


def split_frame(data, w, h, span, stride):
    yb, cb = data[:h * span], data[h * span:2 * h * span]
    y = np.frombuffer(yb, np.uint8)[:h * stride].reshape(h, stride)[:, :w]
    c = np.frombuffer(cb, np.uint8)[:h * stride].reshape(h, stride)[:, :w]
    return y, c


def flat_mask(rgb, k=2):
    """Pixels whose (2k+1)^2 neighbourhood is flat in the reference."""
    g = rgb.astype(float).sum(2)
    m = np.ones_like(g, bool)
    for dy in range(-k, k + 1):
        for dx in range(-k, k + 1):
            m &= np.abs(np.roll(np.roll(g, dy, 0), dx, 1) - g) < 6
    m[:k], m[-k:], m[:, :k], m[:, -k:] = False, False, False, False
    return m


def csc_fit(rgb, y, c):
    """Fit [R G B 1] -> Y, Cb, Cr on flat patches; return fit, nearest standard, residuals."""
    h, w = y.shape
    mask = flat_mask(rgb) & np.repeat(flat_mask(rgb)[:, 0::2] & flat_mask(rgb)[:, 1::2], 2, 1)[:, :w]
    rgbf = rgb.reshape(-1, 3).astype(float)
    A = np.c_[rgbf, np.ones(len(rgbf))]
    sel = mask.reshape(-1)
    if sel.sum() < 1000:
        raise ValueError("too few flat pixels for a colour fit")
    cbp = np.repeat(c[:, 0::2], 2, 1).reshape(-1).astype(float)
    crp = np.repeat(c[:, 1::2], 2, 1).reshape(-1).astype(float)
    fit, res = [], []
    for target in (y.reshape(-1).astype(float), cbp, crp):
        coef, *_ = np.linalg.lstsq(A[sel], target[sel], rcond=None)
        fit.append(coef)
        res.append(float(np.sqrt(np.mean((A[sel] @ coef - target[sel]) ** 2))))
    fit = np.array(fit)
    # coefficients (unitless) and offsets (code values) are judged separately
    dist = {f"{s} {'limited' if lim else 'full'}": float(np.abs(fit[:, :3] - matrix(s, lim)[:, :3]).max())
            for s in STANDARDS for lim in (True, False)}
    nearest = min(dist, key=dist.get)
    std, rng = nearest.split()
    off_err = float(np.abs(fit[:, 3] - matrix(std, rng == "limited")[:, 3]).max())
    return {"fit": [[round(v, 4) for v in r] for r in fit.tolist()], "rms": [round(r, 2) for r in res],
            "nearest": nearest, "max_coef_error": round(dist[nearest], 4), "max_offset_error": round(off_err, 2),
            "distances": {k: round(v, 4) for k, v in dist.items()}, "flat_pixels": int(sel.sum())}


def rowmap(ring_plane, ref_plane, lo=40):
    """Mean |ring - ref| for row maps y -> round(s*y+o), s in {0.5, 1}, o in [-24, 24]."""
    h = ring_plane.shape[0]
    ys = np.arange(lo, h)
    res = []
    for s in (0.5, 1.0):
        for o in range(-24, 25):
            src = np.round(s * ys + o).astype(int)
            ok = (src >= 0) & (src < ref_plane.shape[0])
            e = float(np.abs(ring_plane[ys[ok]].astype(float) - ref_plane[src[ok]].astype(float)).mean())
            res.append((round(e, 2), s, o))
    res.sort()
    return {"best": res[0], "best_half": min(r for r in res if r[1] == 0.5)}


def chroma_shift(c, ref_c):
    """Horizontal shift (luma pixels, step 2 = one chroma sample) minimising |Cr - refCr|."""
    cr, rcr = c[:, 1::2].astype(float), ref_c[:, 1::2].astype(float)
    best = None
    for d in range(-3, 4):
        a = np.roll(rcr, d, 1)[:, 4:-4]
        e = float(np.abs(cr[:, 4:-4] - a).mean())
        if best is None or e < best[0]:
            best = (e, d)
    return {"shift_chroma_samples": best[1], "error": round(best[0], 2)}


def interlace(y):
    yf = y.astype(float)
    pairs_equal = float(np.mean(np.all(yf[0:-1:2] == yf[1::2], 1)))
    d1 = np.abs(yf[1:-1] - (yf[:-2] + yf[2:]) / 2).mean()
    d2 = np.abs(yf[2:] - yf[:-2]).mean() / 2 + 1e-9
    return {"adjacent_pairs_identical": round(pairs_equal, 3), "comb_index": round(float(d1 / d2), 3)}


def psnr(a, b):
    e = float(((a.astype(float) - b.astype(float)) ** 2).mean())
    return round(10 * np.log10(255 ** 2 / e), 2) if e else 99.0


def cadence(changes, hz):
    if len(changes) < 3:
        return {"rate": 0.0, "slots": 0, "expected_hz": hz}
    t = [c[0] for c in changes]
    rate = (len(t) - 1) / (t[-1] - t[0])
    return {"rate": round(rate, 2), "slots": len({c[1] for c in changes}), "expected_hz": hz,
            "matches": abs(rate - hz) < 0.1 * hz}


def analyse(ref_rgb, data, meta):
    w, h, span = meta["w"], meta["h"], meta["span"]
    stride = detect_stride(data, w, h, span)
    y, c = split_frame(data, w, h, span, stride)
    ref = np.asarray(Image.fromarray(ref_rgb).resize((w, h), Image.BICUBIC)) if ref_rgb.shape[:2] != (h, w) else ref_rgb
    csc = csc_fit(ref, y, c)
    m = np.array(csc["fit"])
    ry, rc = nv16_from_rgb(ref, np.vstack([m[0], m[1], m[2]]))
    return {
        "geometry": {"ring": [w, h], "stride": stride, "input": meta.get("input"),
                     "scaled": meta.get("input") not in (None, [w, h])},
        "psnr_y": psnr(y[40:], ry[40:]), "csc": csc,
        "rowmap_y": rowmap(y, ry), "rowmap_c": rowmap(c, rc),
        "chroma": chroma_shift(c, rc), "interlace": interlace(y),
    }


# ---- host control -------------------------------------------------------------

def parse_randr(text):
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    outs, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^(\S+) \((enabled|disabled)\)", line)
        if m:
            cur = outs.setdefault(m.group(1), {"enabled": m.group(2) == "enabled", "modes": [], "pos": (0, 0), "scale": 1.0})
            continue
        if cur is None:
            continue
        m = re.match(r"\s+Position:\s+(-?\d+),(-?\d+)", line)
        if m:
            cur["pos"] = (int(m.group(1)), int(m.group(2)))
        m = re.match(r"\s+Scale:\s+(\d+)%", line)
        if m:
            cur["scale"] = int(m.group(1)) / 100
        m = re.match(r"\s+(\d+)x(\d+) @\s+([\d.]+) Hz(.*)", line)
        if m:
            cur["modes"].append({"w": int(m.group(1)), "h": int(m.group(2)), "hz": float(m.group(3)),
                                 "current": "current" in m.group(4), "preferred": "preferred" in m.group(4)})
    return outs


WANT = [(640, 480, 60), (720, 480, 60), (720, 576, 50), (1280, 720, 60), (1280, 720, 50),
        (1920, 1080, 60), (1920, 1080, 50), (1920, 1080, 24)]


def choose_modes(outs, want=None):
    """The nearest offered refresh for each wanted (w, h, hz), deduplicated."""
    modes = outs[OUTPUT]["modes"]
    chosen = []
    for w, h, hz in want or WANT:
        cands = [m for m in modes if (m["w"], m["h"]) == (w, h)]
        if not cands:
            continue
        m = min(cands, key=lambda m: abs(m["hz"] - hz))
        if abs(m["hz"] - hz) < 1.5 and m not in chosen:
            chosen.append(m)
    return chosen


def crop_box(outs, out=OUTPUT):
    """HDMI-A-1's rectangle inside a full-layout screenshot."""
    en = {n: o for n, o in outs.items() if o["enabled"]}
    minx = min(o["pos"][0] for o in en.values())
    miny = min(o["pos"][1] for o in en.values())
    o = outs[out]
    cur = next(m for m in o["modes"] if m["current"])
    x, y = o["pos"][0] - minx, o["pos"][1] - miny
    return (x, y, x + round(cur["w"] / o["scale"]), y + round(cur["h"] / o["scale"]))


class Host:
    def randr(self):
        return parse_randr(subprocess.run(["cosmic-randr", "list"], capture_output=True, text=True, check=True).stdout)

    def set_mode(self, m):
        subprocess.run(["cosmic-randr", "mode", OUTPUT, str(m["w"]), str(m["h"]), "--refresh", f"{m['hz']:g}"],
                       capture_output=True, text=True, check=True)

    def screenshot(self, outs):
        """The HDMI-A-1 rectangle of a full screenshot; the full image is deleted at once."""
        d = Path(tempfile.mkdtemp(prefix="cc-shot-"))
        try:
            subprocess.run(["cosmic-screenshot", "--interactive=false", "--modal=false", "--notify=false",
                            "-s", str(d)], capture_output=True, text=True, timeout=30, check=True)
            shots = sorted(d.glob("*.png"))
            if not shots:
                raise RuntimeError("cosmic-screenshot saved nothing")
            img = Image.open(shots[-1]).convert("RGB")
            return np.asarray(img.crop(crop_box(outs)))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def board(self, *args, binary=False):
        p = subprocess.run(SSH + ["python3 - " + " ".join(map(str, args))], input=PROBE.read_bytes(),
                           capture_output=True, timeout=120)
        if p.returncode:
            raise RuntimeError(f"board {args}: {p.stderr.decode(errors='replace')[-300:]}")
        if binary:
            nl = p.stdout.index(b"\n")
            return json.loads(p.stdout[:nl]), p.stdout[nl + 1:]
        return json.loads(p.stdout)


def wait_lock(host, timeout=20):
    t0, last = time.monotonic(), None
    while time.monotonic() - t0 < timeout:
        st = host.board("state")
        geo = st.get("fb_in", {})
        key = (geo.get("w"), geo.get("h"))
        if st.get("locked") == 1 and key == last and all(key):
            cad = host.board("cadence", 0.3)
            if len({c[1] for c in cad["changes"]}) >= 2:
                return st
        last = key
        time.sleep(1)
    raise TimeoutError("no lock / stable geometry / cycling ring")


def run(host, out, modes, chart=None):
    out.mkdir(parents=True, exist_ok=False)
    outs = host.randr()
    original = next(m for m in outs[OUTPUT]["modes"] if m["current"])
    report = {"original_mode": original, "modes": []}
    try:
        for m in modes:
            tag = f"{m['w']}x{m['h']}@{m['hz']:g}"
            entry = {"mode": tag}
            report["modes"].append(entry)
            try:
                host.set_mode(m)
                time.sleep(2)
                st = wait_lock(host)
                outs = host.randr()
                ref = np.asarray(Image.open(chart).convert("RGB").resize((m["w"], m["h"]), Image.BICUBIC)) \
                    if chart else host.screenshot(outs)
                w, h = st["fb_in"]["w"], st["fb_in"]["h"]
                span = min(((w + 255) // 256) * 256 + 256, 0x1FF000 // h)
                meta, data = host.board("frame", w, h, span, binary=True)
                cad = host.board("cadence", 1.0)
                d = out / tag
                d.mkdir()
                (d / "state.json").write_text(json.dumps(st, indent=1) + "\n")
                (d / "frame.json").write_text(json.dumps({**meta, "w": w, "h": h, "span": span,
                                                          "input": [m["w"], m["h"]]}, indent=1) + "\n")
                (d / "frame.nv16raw").write_bytes(data)
                Image.fromarray(ref).save(d / "reference.png")
                (d / "cadence.json").write_text(json.dumps(cad) + "\n")
                res = analyse(ref, data, {"w": w, "h": h, "span": span, "input": [m["w"], m["h"]]})
                res["cadence"] = cadence(cad["changes"], m["hz"])
                res["firmware"] = {k: st.get(k) for k in ("afbd_source_mode", "nr_colour_format", "fb_in")}
                entry.update(res)
            except Exception as e:  # one mode failing must not stop the others or the restore
                entry["error"] = f"{type(e).__name__}: {e}"
            print(json.dumps({k: entry.get(k) for k in ("mode", "error", "geometry", "psnr_y")}), flush=True)
    finally:
        host.set_mode(original)
        report["restored"] = True
        (out / "report.json").write_text(json.dumps(report, indent=1) + "\n")
    return report


# ---- self-test ----------------------------------------------------------------

def load_probe():
    spec = importlib.util.spec_from_file_location("probe", PROBE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


RANDR_SAMPLE = """\x1b[1mDP-1\x1b[0m \x1b[1;32m(enabled)\x1b[0m
  Position: 0,0
  Scale: 100%
  Modes:
     3840x2160 @  60.000 Hz (current) (preferred)
HDMI-A-1 (enabled)
  Make: Hitachi Computer Products Inc
  Position: 3840,0
  Scale: 100%
  Modes:
     1920x1080 @  60.000 Hz (current) (preferred)
     1920x1080 @  50.000 Hz
     1920x1080 @  24.000 Hz
     1280x720 @  59.943 Hz
     1280x720 @  50.000 Hz
      640x480 @  59.940 Hz
"""


def self_test():
    fails = []
    rng = np.random.default_rng(1)
    # 1. colour fit recovers each standard from a synthetic patch chart
    blocks = rng.integers(0, 256, (12, 16, 3))
    rgb = np.kron(blocks, np.ones((24, 32, 1))).astype(np.uint8)  # 288 x 512, flat 24x32 patches
    for std in STANDARDS:
        for lim in (True, False):
            y, c = nv16_from_rgb(rgb, matrix(std, lim))
            r = csc_fit(rgb, y, c)
            want = f"{std} {'limited' if lim else 'full'}"
            if r["nearest"] != want or r["max_coef_error"] > 0.01 or r["max_offset_error"] > 1.5:
                fails.append(f"csc fit {want}: got {r['nearest']} coef {r['max_coef_error']} off {r['max_offset_error']}")
    # 2. stride detection: a 512-wide frame stored at stride 544 inside a 640 span
    y, c = nv16_from_rgb(rgb, matrix("BT.709", True))
    pad = lambda p: np.pad(p, ((0, 0), (0, 544 - 512)), constant_values=0)
    span = 640
    yb = np.zeros(288 * span, np.uint8); yb[:288 * 544] = pad(y).reshape(-1)
    cb_ = np.zeros(288 * span, np.uint8); cb_[:288 * 544] = pad(c).reshape(-1)
    data = yb.tobytes() + cb_.tobytes()
    if detect_stride(data, 512, 288, span) != 544:
        fails.append(f"stride: got {detect_stride(data, 512, 288, span)}, want 544")
    y2, c2 = split_frame(data, 512, 288, span, 544)
    if not (np.array_equal(y2, y) and np.array_equal(c2, c)):
        fails.append("split_frame did not recover the planes")
    # 3. interlace: line doubling is detected, progressive is not (on an image with vertical detail)
    yn = rng.integers(16, 236, (288, 512)).astype(np.uint8)
    ld = np.repeat(yn[0::2], 2, 0)
    if interlace(ld)["adjacent_pairs_identical"] < 0.9 or interlace(yn)["adjacent_pairs_identical"] > 0.1:
        fails.append("interlace line-doubling metric wrong")
    # 4. the real ring frame (10-23, 1280x720) against the chart: 1:1 rows, a sane fit
    ringf = ROOT / "local/panel-source-t5/ring/ring3.nv16"
    chart = ROOT / "local/panel-source-t5/ring/chart.webp"
    if ringf.exists() and chart.exists():
        raw = ringf.read_bytes()[:1280 * 720 * 2]
        ref = np.asarray(Image.open(chart).convert("RGB").resize((1280, 720), Image.BICUBIC))
        r = analyse(ref, raw, {"w": 1280, "h": 720, "span": 1280, "input": [1280, 720]})
        if r["geometry"]["stride"] != 1280:
            fails.append(f"real ring stride {r['geometry']['stride']}")
        if r["rowmap_c"]["best"][1:] != (1.0, 0) or r["rowmap_y"]["best"][1:] != (1.0, 0):
            fails.append(f"real ring rowmap {r['rowmap_y']['best']} / {r['rowmap_c']['best']}")
        # the colour fit on held data is informational: the chart file is not what COSMIC rendered
        # (top bar, its own scaler); real runs use the cropped screenshot of what the host sends
        real = r
    else:
        fails.append("held ring data missing (local/panel-source-t5/ring/)")
        real = None
    # 5. the probe against the held O2 MIPS image and a fake register file
    pm = load_probe()
    img = (ROOT / "local/panel-source-t5/sweeps/O2-a/mips-image.bin").read_bytes()
    ring = (ROOT / "local/panel-source-t5/ring/ring3.nv16").read_bytes()
    slots = {0x4C3EF000 + n * 0x1FF000: ring[(n % 3) * 1843200:(n % 3) * 1843200 + 921600] if n < 3
             else ring[((n - 3) % 3) * 1843200 + 921600:((n - 3) % 3) * 1843200 + 1843200] for n in range(6)}
    seq = [(0x4C3EF000, 0x4C9EC000), (0x4C5EE000, 0x4CBEB000), (0x4C7ED000, 0x4CDEA000)]
    clock = {"n": 0}

    def word(pa):
        if pa in pm.PAIR:
            clock["n"] += 1
            p = seq[(clock["n"] // 40) % 3]
            return p[pm.PAIR.index(pa)]
        return struct_word(raw_(pa, 4))

    def raw_(pa, n):
        if pm.PHYS <= pa < pm.IMG_END:
            o = pa - pm.PHYS
            return img[o:o + n]
        for base, data in slots.items():
            if base <= pa < base + 0x1FF000:
                o = pa - base
                return (data + bytes(0x1FF000))[o:o + n]
        return bytes(n)

    import struct as _s
    struct_word = lambda b: _s.unpack("<I", b)[0]
    pm.time.sleep = lambda s: None  # fake board: no real waiting
    real_mono = pm.time.monotonic
    tick = {"t": 0.0}
    pm.time.monotonic = lambda: tick.__setitem__("t", tick["t"] + 0.001) or tick["t"]
    try:
        p = pm.Probe(word, raw_)
        st = p.state()
        fb = st.get("fb_in", {})
        if (st.get("locked"), fb.get("w"), fb.get("h"), fb.get("colour_format"), st.get("nr")) != \
                (1, 1280, 720, 4, "8b89bfc0"):
            fails.append(f"probe state from the O2 image: {st.get('locked')} {fb} {st.get('nr')}")
        if not st.get("cap"):
            fails.append("probe did not find CapWinNode")
        meta, data = p.frame(720, 1280)
        ys, cs = int(meta["y"], 16), int(meta["c"], 16)
        if data != slots[ys][:921600] + slots[cs][:921600] or meta["copy_max_diff"] != 0:
            fails.append("probe frame is not the slot it named")
        # copies that differ by more than 1 LSB (a writer racing the read) are refused; +-1 noise is accepted
        for delta, ok in ((5, False), (1, True)):
            calls = {"n": 0}

            def noisy(pa, n, delta=delta):
                b = raw_(pa, n)
                if pa >= 0x4C3EF000 and n > 4:
                    calls["n"] += 1
                    if (calls["n"] - 1) % 4 >= 2 and b:  # Y and C of every second copy
                        b = bytes([min(255, b[0] + delta)]) + b[1:]
                return b
            try:
                meta2, _ = pm.Probe(word, noisy).frame(720, 1280)
                if not ok:
                    fails.append(f"probe accepted copies differing by {delta}")
                elif meta2["copy_max_diff"] != 1:
                    fails.append(f"probe copy_max_diff {meta2['copy_max_diff']} for 1-LSB noise")
            except RuntimeError:
                if ok:
                    fails.append("probe refused 1-LSB noise")
        # a stuck pair (no signal) refuses
        stuck = pm.Probe(lambda pa: 0x4C3EF000 if pa in pm.PAIR else struct_word(raw_(pa, 4)), raw_)
        try:
            stuck.frame(720, 1280)
            fails.append("probe read a frame with the pair not cycling")
        except RuntimeError:
            pass
        # forbidden window refused by the real reader's guard
        try:
            pm.devmem_probe  # exists
            src = PROBE.read_text()
            if "0x06900000 <= pa < 0x06A00000" not in src or "0x07090000 <= pa < 0x070A0000" not in src:
                fails.append("probe reader lost its forbidden-window guard")
        except AttributeError:
            fails.append("probe has no devmem reader")
    finally:
        pm.time.monotonic = real_mono
    # 6. randr parsing, mode choice and the screenshot crop
    outs = parse_randr(RANDR_SAMPLE)
    if outs[OUTPUT]["pos"] != (3840, 0) or len(outs[OUTPUT]["modes"]) != 6:
        fails.append(f"randr parse: {outs.get(OUTPUT)}")
    ch = [f"{m['w']}x{m['h']}@{m['hz']:g}" for m in choose_modes(outs)]
    if ch != ["640x480@59.94", "1280x720@59.943", "1280x720@50", "1920x1080@60", "1920x1080@50", "1920x1080@24"]:
        fails.append(f"mode choice: {ch}")
    if choose_modes(outs, [(1920, 1080, 30)]) or choose_modes(outs, [(1280, 720, 30)]):
        fails.append("mode choice took a refresh the host does not offer")
    if crop_box(outs) != (3840, 0, 5760, 1080):
        fails.append(f"crop box {crop_box(outs)}")
    # 7. run(): the host mode is restored even when a mode fails and when the run aborts
    class FakeHost:
        def __init__(self, fail_on=None, abort=False):
            self.sets, self.fail_on, self.abort = [], fail_on, abort

        def randr(self):
            return parse_randr(RANDR_SAMPLE)

        def set_mode(self, m):
            self.sets.append((m["w"], m["h"], m["hz"]))
            if self.abort and len(self.sets) == 2:
                raise KeyboardInterrupt

        def board(self, *a, binary=False):
            if a[0] == "state":
                return {"locked": 1, "fb_in": {"w": 1280, "h": 720}}
            if a[0] == "cadence":
                return {"changes": [[0, "a", "x"], [0.0167, "b", "y"], [0.0333, "c", "z"]]}
            if a[0] == "frame":
                if self.fail_on:
                    raise RuntimeError("boom")
                w, h, span = a[1], a[2], a[3]
                return {"y": "0"}, (ring[:921600] + bytes(h * span))[:h * span] * 2

        def screenshot(self, outs):
            return np.asarray(Image.open(chart).convert("RGB").resize((1920, 1080)))

    for fh in (FakeHost(fail_on=True), FakeHost(abort=True)):
        d = Path(tempfile.mkdtemp(prefix="cc-test-")) / "run"
        try:
            run(fh, d, choose_modes(parse_randr(RANDR_SAMPLE))[:2])
        except KeyboardInterrupt:
            pass
        finally:
            if fh.sets[-1] != (1920, 1080, 60.0):
                fails.append(f"host mode not restored: {fh.sets}")
            shutil.rmtree(d.parent, ignore_errors=True)
    for f in fails:
        print("FAIL:", f)
    if real:
        print("real ring 1280x720:", json.dumps({k: real[k] for k in ("psnr_y", "rowmap_c", "chroma", "interlace")}),
              "csc nearest", real["csc"]["nearest"], real["csc"]["max_coef_error"])
    print("self-test", "FAILED" if fails else "passed (7 groups)")
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=("run", "plan", "analyse"))
    ap.add_argument("dir", nargs="?", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--modes", nargs="*")
    ap.add_argument("--chart", type=Path)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    host = Host()
    want = [tuple(float(x) if i == 2 else int(x) for i, x in enumerate(re.split("[x@]", s))) for s in a.modes] \
        if a.modes else None
    if a.cmd == "plan":
        outs = host.randr()
        print(json.dumps([f"{m['w']}x{m['h']}@{m['hz']:g}" for m in choose_modes(outs, want)]))
        return 0
    if a.cmd == "analyse":
        for d in sorted(p for p in a.dir.iterdir() if (p / "frame.json").exists()):
            meta = json.loads((d / "frame.json").read_text())
            res = analyse(np.asarray(Image.open(d / "reference.png").convert("RGB")),
                          (d / "frame.nv16raw").read_bytes(), meta)
            print(d.name, json.dumps(res))
        return 0
    if a.cmd == "run":
        if not a.out:
            ap.error("run needs --out")
        run(host, a.out, choose_modes(host.randr(), want), a.chart)
        return 0
    ap.error("a command or --self-test")


if __name__ == "__main__":
    sys.exit(main())
