#!/usr/bin/env python3
"""Every display register a letterboxed (unscaled) video picture needs.
Runs on the host. Reads nothing from hardware: it takes a baseline dump.

    letterbox-recipe.py --live native.txt 852x480 214,120
    letterbox-recipe.py --live native.txt 1280x536 0,92 --fmt nv12 --pitch 1280
    letterbox-recipe.py --live native.txt --self-test

`native.txt` is tools/display/letterbox-baseline.py run while 1280x720 video
is on the plane. The model is the MIPS firmware's own window layer
(docs/reference/letterbox-recipe-2026-10-04.md has the derivation and the
firmware address behind every field). This tool is the single place that
arithmetic lives; a kernel patch transcribes it.

HOW A VALUE IS COMPUTED. Two kinds of field:

  abs  the firmware formula gives the value outright (sizes, AFBD geometry,
       line-buffer descriptors, border widths). The self-test checks each one
       reproduces the live native state, so a wrong formula fails loudly.
  rel  a timing position. The firmware derives it from the panel's active
       start plus fixed pipeline delays that differ per register (NR's fetch x
       reads 48 where proc's stream x reads 49), and not every delay is
       derived. So these are `live + f(new) - f(native)`: the dependency on
       W/H/dx/dy comes from the firmware, the constant comes from hardware.

Scope: proc at unity (no magnification) -- Phases 1 and 2 of
docs/letterbox-plan.md. Upscaling (Phase 3) adds proc ratios and phases.

Exit status 1 if a field cannot be expressed (e.g. off-panel, odd size).
"""
import argparse
import json
import math
import sys

PANEL_W, PANEL_H = 1280, 720
# Panel active-area origin in timing coordinates: hs_size + h_back_porch - 28
# and vs_size + v_back_porch (WCETop 0x8b1a87f0/0x8b1a8928; elog 2026-09-04),
# read back as proc+044 = 49 and lvds+0c0[15:0] = 22.
X0, Y0 = 49, 22


def a16(x):
    return (x + 15) & ~15


def a4(x):
    return (x + 3) & ~3


def even(x):
    return (x + 1) & ~1


def rowbyte(w):
    # GetPsuPfuWin's compressed branch, ((x << 3) + 0x7f) >> 7 with
    # x = 0.8 * W bytes, i.e. ceil(W / 20). Reproduces the live 1280 -> 0x40
    # and the firmware's own 852 -> 0x2B (2026-09-05 capture).
    return math.ceil(w / 20)


class P:
    """Picture geometry: source W x H placed unscaled at panel (dx, dy)."""

    def __init__(self, w, h, dx, dy, fmt="nv12", pitch=None):
        self.w, self.h, self.dx, self.dy, self.fmt = w, h, dx, dy, fmt
        cpp = 2 if fmt == "p010" else 1
        self.pitch = pitch if pitch is not None else w * cpp
        self.stride = self.pitch // cpp          # AFBD strides count samples
        self.ybudget = h * cpp                   # fetch lines (P010 doubles,
        self.cbudget = h // 2 * cpp              # driver-measured 2026-09-30)


NATIVE = P(PANEL_W, PANEL_H, 0, 0)

# (block, offset, lsb, width, kind, f(P), provenance)
FIELDS = [
    # --- AFBD source 0 (0x05600000), sun50i-h713-afbd + firmware 0x8b1a40e0 ---
    ("afbd", 0x020, 0, 13, "abs", lambda p: a16(p.w) - 1, "fw 0x8b1a40fc"),
    ("afbd", 0x020, 16, 13, "abs", lambda p: a16(p.h) - 1, "fw 0x8b1a4120"),
    ("afbd", 0x024, 0, 9, "abs", lambda p: a16(p.w) // 16 - 1, "fw 0x8b1a4168"),
    ("afbd", 0x024, 16, 9, "abs", lambda p: a16(p.h) // 16 - 1, "fw 0x8b1a417c"),
    ("afbd", 0x030, 0, 13, "abs", lambda p: even(p.w), "fw 0x8b1a4154"),
    ("afbd", 0x030, 16, 13, "abs", lambda p: p.ybudget, "fw 0x8b1a4138; P010 x2 measured"),
    ("afbd", 0x040, 0, 16, "abs", lambda p: a16(p.stride), "fw 0x8b1a41f0"),
    ("afbd", 0x044, 0, 16, "abs", lambda p: a16(p.stride), "fw 0x8b1a4204"),
    ("afbd", 0x048, 0, 16, "abs", lambda p: a4(p.w), "fw 0x8b1a42c4"),
    ("afbd", 0x048, 16, 13, "abs", lambda p: p.ybudget, "fw 0x8b1a42d8; P010 x2 measured"),
    ("afbd", 0x04c, 0, 16, "abs", lambda p: a4(p.w), "fw 0x8b1a42e8"),
    ("afbd", 0x04c, 16, 13, "abs", lambda p: p.cbudget, "fw 0x8b1a4320 (4:2:0 halves)"),

    # --- composition / NR (0x05000000), NRWinNode::WriteReg 0x8b1a48cc ---
    # line-buffer descriptors: Rowbyte [15:0], LineBufLevel [27:16]
    ("comp", 0x1b4, 0, 16, "abs", lambda p: rowbyte(p.w), "Y rowbyte, A"),
    ("comp", 0x1b4, 16, 12, "abs", lambda p: rowbyte(p.w), "Y level, A"),
    ("comp", 0x174, 0, 16, "abs", lambda p: rowbyte(p.w), "C rowbyte, A"),
    ("comp", 0x174, 16, 12, "abs", lambda p: rowbyte(p.w), "C level, A"),
    ("comp", 0x2b4, 0, 16, "abs", lambda p: rowbyte(p.w), "Y rowbyte, B"),
    ("comp", 0x2b4, 16, 12, "abs", lambda p: rowbyte(p.w), "Y level, B"),
    ("comp", 0x274, 0, 16, "abs", lambda p: rowbyte(p.w), "C rowbyte, B"),
    ("comp", 0x274, 16, 12, "abs", lambda p: rowbyte(p.w), "C level, B"),
    ("comp", 0x0f0, 0, 8, "abs", lambda p: rowbyte(p.w), "Y level 8-bit, A"),
    ("comp", 0x0f0, 8, 8, "abs", lambda p: rowbyte(p.w), "C level 8-bit, A"),
    ("comp", 0x210, 0, 8, "abs", lambda p: rowbyte(p.w), "Y level 8-bit, B"),
    ("comp", 0x210, 8, 8, "abs", lambda p: rowbyte(p.w), "C level 8-bit, B"),
    # channel B line numbers; A's 1080/540 is the firmware's hardcoded path
    ("comp", 0x2b8, 0, 16, "abs", lambda p: p.h, "Y LineNumber, B"),
    ("comp", 0x278, 0, 16, "abs", lambda p: p.h // 2, "C LineNumber, B"),
    ("comp", 0x224, 0, 16, "abs", lambda p: p.w, "picture w (node+0x44)"),
    ("comp", 0x224, 16, 16, "abs", lambda p: p.h, "picture h (node+0x48)"),
    # fetch window: NEVER dumped or poked before 2026-10-04 (09-12 stopped at
    # comp+0x2ff) -- the 1280-pixel line step the 09-12 shear measured
    ("comp", 0x804, 0, 16, "abs", lambda p: even(p.w), "read_fetch.w"),
    ("comp", 0x804, 16, 16, "rel", lambda p: p.dx, "read_fetch.x - 5"),
    ("comp", 0x808, 0, 16, "rel", lambda p: p.dx, "out.x + crop.x"),
    ("comp", 0x80c, 0, 16, "rel", lambda p: p.h, "read_fetch.h"),
    ("comp", 0x80c, 16, 16, "rel", lambda p: p.dy, "read_fetch.y"),
    # 0x840/0x844 are the flag-0x4000/0x2000 writes at 0x8b1a4cb4..4d34
    ("comp", 0x840, 0, 16, "abs", lambda p: Y0 + p.dy - 1, "read_fetch.y - 1"),
    ("comp", 0x840, 16, 16, "abs", lambda p: p.h + 1, "read_fetch.h + 1"),
    ("comp", 0x844, 0, 16, "abs", lambda p: X0 + p.dx - 1, "read_fetch.x - 1"),
    ("comp", 0x844, 16, 16, "abs", lambda p: even(p.w), "read_fetch.w, even"),
    ("comp", 0x858, 0, 16, "rel", lambda p: p.dy, "out.y"),
    # para[0] in NRWinNode::CalcWindow (0x8b1a3934): the PICTURE height.
    # Left at 720 it ends the NR output early when dy > 0 (b lost 73 lines);
    # = H gives the full picture. Hardware-confirmed 2026-10-05 (bisect set 3).
    ("comp", 0x858, 16, 16, "abs", lambda p: p.h, "picture height (para[0])"),
    ("comp", 0x85c, 0, 16, "rel", lambda p: p.dx, "crop.x + out.x"),
    ("comp", 0x85c, 16, 16, "abs", lambda p: p.w, "crop.w"),

    # --- route (0x05140000), ProcWinNode::WriteReg 0x8b1a6a08 ---
    ("route", 0x104, 16, 16, "abs", lambda p: even(p.w), "source win w"),
    ("route", 0x108, 16, 16, "abs", lambda p: even(p.h), "source win h"),
    ("route", 0x11c, 16, 16, "abs", lambda p: p.h, "source h"),
    ("route", 0x124, 16, 16, "abs", lambda p: p.w, "picture win w"),
    ("route", 0x128, 16, 16, "abs", lambda p: p.h, "picture win h"),
    ("route", 0xd40, 16, 16, "abs", lambda p: p.w, "out w"),
    ("route", 0xd44, 16, 16, "abs", lambda p: p.h, "out h"),

    # --- proc instance 0 (0x05180000) at unity, 0x8b1a66d0 ---
    ("proc", 0x034, 16, 16, "abs", lambda p: p.w, "in_win.w"),
    ("proc", 0x034, 0, 16, "abs", lambda p: p.h, "in_win.h"),
    ("proc", 0x02c, 0, 16, "abs", lambda p: p.w, "out_win.w"),
    ("proc", 0x02c, 16, 16, "rel", lambda p: p.dx, "stream.x + 4"),
    ("proc", 0x030, 0, 16, "abs", lambda p: p.h, "out_win.h"),
    ("proc", 0x040, 0, 16, "abs", lambda p: p.w, "out_win.w again"),
    ("proc", 0x044, 0, 16, "rel", lambda p: p.dx, "stream.x"),
    ("proc", 0x050, 0, 16, "abs", lambda p: p.h, "max(in_h, out_h)"),
    ("proc", 0x050, 16, 16, "rel", lambda p: p.dy, "vs_delay+1+vde_start+mb_420"),

    # --- panel (0x051c0000), PanelWinNode::WriteReg 0x8b1a5a38 ---
    # program window 0xbc/0xc0 and crtc 0xfe00/04 stay: stream.x - out.x
    ("lvds", 0x03c, 16, 16, "abs", lambda p: p.w, "video_win_2.w"),
    ("lvds", 0x040, 16, 16, "abs", lambda p: p.h, "video_win_2.h"),
    ("lvds", 0x0a4, 16, 16, "abs", lambda p: p.w, "video_win_2.w"),
    ("lvds", 0x0a8, 16, 16, "abs", lambda p: p.h, "video_win_2.h"),

    # --- border overlay (vblender 0x05200000), WriteBorderOverlay1 0x8b1a55d8 ---
    ("vblend", 0x000, 0, 12, "abs", lambda p: PANEL_W - p.dx - p.w, "right"),
    ("vblend", 0x000, 16, 12, "abs", lambda p: p.dx, "left"),
    ("vblend", 0x000, 12, 4, "abs", lambda p: p.dy & 0xf, "top[3:0]"),
    ("vblend", 0x000, 28, 4, "abs", lambda p: (p.dy >> 4) & 0xf, "top[7:4]"),
    ("vblend", 0x004, 0, 12, "abs", lambda p: PANEL_H - p.dy - p.h, "bottom"),
    ("vblend", 0x004, 12, 4, "abs", lambda p: (p.dy >> 8) & 0xf, "top[11:8]"),
    ("vblend", 0x004, 30, 1, "abs", lambda p: 1, "border enable"),
]

BASES = {"afbd": 0x05600000, "comp": 0x05000000, "route": 0x05140000,
         "proc": 0x05180000, "lvds": 0x051c0000, "vblend": 0x05200000}


def load_live(path):
    live = {}
    for line in open(path):
        name, _addr, val = line.split()
        blk, off = name.split("+")
        live[(blk, int(off, 16))] = int(val, 16)
    return live


def check(p):
    errs = []
    if p.w % 2 or p.h % 2:
        errs.append("width and height must be even (4:2:0)")
    if p.dx < 0 or p.dy < 0 or p.dx + p.w > PANEL_W or p.dy + p.h > PANEL_H:
        errs.append("picture must lie fully on the panel")
    if p.dx % 2:
        errs.append("x offset must be even (4:2:0 chroma)")
    cpp = 2 if p.fmt == "p010" else 1
    if p.pitch % (16 * cpp):
        errs.append("stride must be a multiple of 16 samples: AFBD rounds "
                    "+0x040/+0x044 up to 16 (fw 0x8b1a41e8) and would shear")
    if p.stride < a16(p.w):
        errs.append("stride below ALIGN16(width): AFBD fetches whole 16-pixel "
                    "blocks (+0x020/+0x024)")
    return errs


def buffer_needs(p):
    """Bytes AFBD may read from each plane: whole 16x16 blocks (+0x020/+0x024)."""
    return p.pitch * a16(p.h), p.pitch * a16(p.h) // 2


def recipe(live, p):
    """Return {(blk, off): (old, new, [notes])} for every touched register."""
    out = {}
    for blk, off, lsb, width, kind, f, prov in FIELDS:
        mask = ((1 << width) - 1) << lsb
        old = out.get((blk, off), (live[(blk, off)],))[0]
        cur = out.get((blk, off), (old, old, []))[1]
        if kind == "abs":
            val = f(p)
        else:
            base = (live[(blk, off)] & mask) >> lsb
            val = base + f(p) - f(NATIVE)
        if not 0 <= val < (1 << width):
            raise ValueError(f"{blk}+{off:03x}[{lsb + width - 1}:{lsb}] = {val} "
                             f"does not fit ({prov})")
        new = (cur & ~mask) | (val << lsb)
        notes = out.get((blk, off), (0, 0, []))[2] + [
            f"[{lsb + width - 1}:{lsb}]={val} {kind} {prov}"]
        out[(blk, off)] = (old, new, notes)
    return out


def self_test(live):
    ok = True
    # 1. The model must reproduce the live native state exactly.
    for (blk, off), (old, new, notes) in recipe(live, NATIVE).items():
        if old != new:
            ok = False
            print(f"FAIL native {blk}+{off:03x}: live {old:08X} model {new:08X}")
            for n in notes:
                print("     ", n)
    # 2. The firmware's own 852x480 numbers (2026-09-05, top-left placement).
    r = recipe(live, P(852, 480, 0, 0))
    want = {("afbd", 0x030): 0x01E00354, ("comp", 0x174): 0x002B002B,
            ("comp", 0x274): 0x002B002B}
    for k, v in want.items():
        if r[k][1] != v:
            ok = False
            print(f"FAIL 852x480 {k[0]}+{k[1]:03x}: model {r[k][1]:08X} firmware {v:08X}")
    vb0, vb4 = r[("vblend", 0x000)][1], r[("vblend", 0x004)][1]
    borders = (vb0 & 0xfff, (vb0 >> 16) & 0xfff, vb4 & 0xfff)
    if borders != (428, 0, 240):
        ok = False
        print(f"FAIL 852x480 borders right/left/bottom {borders}, firmware (428, 0, 240)")
    print("self-test", "PASS" if ok else "FAIL",
          f"({len(FIELDS)} fields, {len(recipe(live, NATIVE))} registers)")
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--live", required=True, help="letterbox-baseline.py dump, native 720p video on")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--fmt", choices=("nv12", "p010"), default="nv12")
    ap.add_argument("--pitch", type=int, help="bytes per line (default: tight)")
    ap.add_argument("size", nargs="?", help="WxH of the picture")
    ap.add_argument("at", nargs="?", default="centre", help="X,Y on the panel, or 'centre'")
    ap.add_argument("--json", metavar="FILE",
                    help="also write the recipe for letterbox-apply.py")
    a = ap.parse_args()
    live = load_live(a.live)
    if a.self_test:
        return 0 if self_test(live) else 1
    if not a.size:
        ap.error("give WxH, or --self-test")
    w, h = (int(v) for v in a.size.lower().split("x"))
    if a.at == "centre":
        dx, dy = (PANEL_W - w) // 2 & ~1, (PANEL_H - h) // 2
    else:
        dx, dy = (int(v) for v in a.at.split(","))
    p = P(w, h, dx, dy, a.fmt, a.pitch)
    errs = check(p)
    if errs:
        for e in errs:
            print("refused:", e, file=sys.stderr)
        return 1
    ylen, clen = buffer_needs(p)
    print(f"# {w}x{h} {a.fmt} pitch {p.pitch} at ({dx},{dy}); "
          f"borders L{dx} R{PANEL_W - dx - w} T{dy} B{PANEL_H - dy - h}")
    print(f"# buffer must cover luma {ylen} B and chroma {clen} B from the "
          f"plane offsets (AFBD reads {a16(w)}x{a16(h)})")
    print("# write order (firmware): source 0 off; NR hold (comp+040[25]=0, "
          "+860[17]=1, +138[27]=1); afbd; comp; NR release (+040[25]=1, "
          "+860[17]=0, +138[27]=0, +82c[15:0]=1); route+proc; lvds; vblend; "
          "source 0 on with the frame queued")
    for (blk, off), (old, new, notes) in sorted(recipe(live, p).items(),
                                                key=lambda kv: BASES[kv[0][0]] + kv[0][1]):
        mark = "" if old == new else "  *"
        print(f"{BASES[blk] + off:#010x} {blk}+{off:03x} {old:08X} -> {new:08X}{mark}")
        for n in notes:
            print(f"    {n}")
    if a.json:
        regs = recipe(live, p)
        doc = {
            "picture": {"w": w, "h": h, "dx": dx, "dy": dy, "fmt": a.fmt,
                        "pitch": p.pitch, "stride": p.stride},
            "buffer": {"luma_bytes": ylen, "chroma_bytes": clen},
            "live": a.live,
            # FIELDS order: afbd, comp, route, proc, lvds, vblend
            "regs": [{"block": blk, "off": off, "addr": BASES[blk] + off,
                      "old": old, "new": new, "notes": notes}
                     for (blk, off), (old, new, notes) in regs.items()],
        }
        with open(a.json, "w") as f:
            json.dump(doc, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
