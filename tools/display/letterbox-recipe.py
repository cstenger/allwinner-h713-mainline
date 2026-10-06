#!/usr/bin/env python3
"""Every display register a letterboxed video picture needs, scaled or not.
Runs on the host. Reads nothing from hardware: it takes a baseline dump.

    letterbox-recipe.py --live native.txt 852x480 214,120
    letterbox-recipe.py --live native.txt 1280x536 0,92 --fmt nv12 --pitch 1280
    letterbox-recipe.py --live native.txt 352x288 200,0 --out 880x720
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

SOURCE AND DESTINATION. The picture is W x H in memory (the source) and
OW x OH on the panel (the destination, default = the source). Everything
upstream of proc -- AFBD, the NR line buffers and fetch window, the route's
source window -- takes the SOURCE size; proc magnifies, and its output, the
route's picture and output windows, the panel's video window and the border
overlay take the DESTINATION size. Positions (dx, dy) are panel positions for
both: NR's output origin and proc's stream position are the same timing
point. This is the firmware's own split: its one scaled log (720x480 ->
1280x720, wce-elog-bringup-2026-09-04.txt) has NR and proc m_in_win at
720x480, proc m_out_win and pic_win at 1280x720, all at (49, 22).

Proc only MAGNIFIES (ProcWinNode::CalcScaleRatio, measured 2026-09-11), so
OW >= W and OH >= H; 4x per axis is the largest ratio measured.
Phases 1-2 of docs/letterbox-plan.md are the OW = W case; Phase 3 the rest.

Exit status 1 if a field cannot be expressed (e.g. off-panel, odd size).
"""
import argparse
import copy
import json
import math
import os
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


U = 0x10000     # proc unity, the firmware constant at 0x8b206dac


class P:
    """Picture geometry: source W x H, shown as OW x OH at panel (dx, dy)."""

    def __init__(self, w, h, dx, dy, fmt="nv12", pitch=None, ow=None, oh=None,
                 hflip=0, vflip=0):
        self.w, self.h, self.dx, self.dy, self.fmt = w, h, dx, dy, fmt
        # Hardware mirror (WP5), in HARDWARE terms: hflip is the panel's line
        # reversal, vflip AFBD's bottom-up fetch. dx/dy are hardware positions;
        # hw_place() maps a client's rectangle to them.
        self.hflip, self.vflip = int(hflip), int(vflip)
        self.ow = ow if ow is not None else w
        self.oh = oh if oh is not None else h
        cpp = 2 if fmt == "p010" else 1
        self.pitch = pitch if pitch is not None else w * cpp
        self.stride = self.pitch // cpp          # AFBD strides count samples
        self.ybudget = h * cpp                   # fetch lines (P010 doubles,
        self.cbudget = h // 2 * cpp              # driver-measured 2026-09-30)

    # ProcWinNode::CalcScaleRatio (0x8b1a5f98): in * unity / out, truncated,
    # for in < out; unity when equal.
    @property
    def ratio_h(self):
        return self.w * U // self.ow

    @property
    def ratio_v(self):
        return self.h * U // self.oh

    # ProcWinNode::CalcWindow (0x8b1a63d0..0x8b1a6430, 0x8b1a6648): fractional
    # phases (unity + ratio) >> 2 (H) and >> 1 (V); integer phases start at
    # H=3 / V=2, and an axis whose fraction crosses its threshold (only unity
    # does, for a magnifying ratio) advances to 4 / 3 with V wrapping to 0.
    # Reproduces the live native 0x43010000 / 0x8000 / 0.
    def _phase(self):
        ph, pv = (U + self.ratio_h) >> 2, (U + self.ratio_v) >> 1
        ih, iv = 3, 2
        if ph >= 0x8000:
            ih += 1
            if ph >= 0x10000:
                ph = 0
        if pv >= 0x10000:
            pv, iv = 0, iv + 1
        return ph, pv, ih, iv

    phase_h = property(lambda self: self._phase()[0])
    phase_v = property(lambda self: self._phase()[1])
    int_h = property(lambda self: self._phase()[2])
    int_v = property(lambda self: self._phase()[3])

    @property
    def vde(self):
        # WCETop 0x8b1a8928 subtracts the H-mirror flag from the vertical
        # active start (0x8b1a89a0..89b0): the panel's line reversal costs a
        # line, so everything upstream of it starts one line earlier. Stock
        # orient-rear: comp 80c/840/858 and proc +050 all move by -1.
        return Y0 - self.hflip

    @property
    def bypass(self):
        # WriteReg 0x8b1a6730: bypass iff both ratios are unity
        return int(self.ratio_h == U and self.ratio_v == U)


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
    ("comp", 0x80c, 16, 16, "rel", lambda p: p.dy - p.hflip, "read_fetch.y (vde)"),
    # 0x840/0x844 are the flag-0x4000/0x2000 writes at 0x8b1a4cb4..4d34
    ("comp", 0x840, 0, 16, "abs", lambda p: p.vde + p.dy - 1, "read_fetch.y - 1 (vde)"),
    ("comp", 0x840, 16, 16, "abs", lambda p: p.h + 1, "read_fetch.h + 1"),
    ("comp", 0x844, 0, 16, "abs", lambda p: X0 + p.dx - 1, "read_fetch.x - 1"),
    ("comp", 0x844, 16, 16, "abs", lambda p: even(p.w), "read_fetch.w, even"),
    ("comp", 0x858, 0, 16, "rel", lambda p: p.dy - p.hflip, "out.y (vde)"),
    # para[0] in NRWinNode::CalcWindow (0x8b1a3934), the NR out-window height
    # passed in by WCETop: the DESTINATION height, in panel lines. Left at 720
    # it ended every vertically offset picture early (Phase 1 bisect set 3);
    # left at H it starved proc after H panel lines, cutting each magnified
    # picture at H/ratio source lines (Phase 3 bisect p1, 2026-10-05). At unity
    # the two readings agree.
    ("comp", 0x858, 16, 16, "abs", lambda p: p.oh, "out-window height (dst, para[0])"),
    ("comp", 0x85c, 0, 16, "rel", lambda p: p.dx, "crop.x + out.x"),
    ("comp", 0x85c, 16, 16, "abs", lambda p: p.w, "crop.w"),

    # --- route (0x05140000), ProcWinNode::WriteReg 0x8b1a6a08 ---
    ("route", 0x104, 16, 16, "abs", lambda p: even(p.w), "source win w"),
    ("route", 0x108, 16, 16, "abs", lambda p: even(p.h), "source win h"),
    ("route", 0x11c, 16, 16, "abs", lambda p: p.h, "source h"),
    # pic_win {0, s3[8], 0, s3[0xc]} and the out window are the DESTINATION
    # (node+0x9c / +0x7c, 0x8b1a6b50 / 0x8b1a6bb4; the 720x480 log prints
    # pic_win 1280x720). Retired 0111 wrote the source size here.
    ("route", 0x124, 16, 16, "abs", lambda p: p.ow, "picture win w (dst)"),
    ("route", 0x128, 16, 16, "abs", lambda p: p.oh, "picture win h (dst)"),
    ("route", 0xd40, 16, 16, "abs", lambda p: p.ow, "out w (dst)"),
    ("route", 0xd44, 16, 16, "abs", lambda p: p.oh, "out h (dst)"),

    # --- proc instance 0 (0x05180000), WriteReg subroutine 0x8b1a66d0 ---
    ("proc", 0x000, 0, 16, "abs", lambda p: p.phase_h, "H phase"),
    ("proc", 0x008, 0, 22, "abs", lambda p: p.ratio_h, "H ratio (in << 16) / out"),
    ("proc", 0x008, 24, 3, "abs", lambda p: p.int_v, "V integer phase"),
    ("proc", 0x008, 28, 3, "abs", lambda p: p.int_h, "H integer phase"),
    ("proc", 0x014, 27, 1, "abs", lambda p: p.bypass, "bypass iff both ratios unity"),
    ("proc", 0x014, 28, 4, "abs", lambda p: 0, "cleared by WriteReg"),
    ("proc", 0x034, 16, 16, "abs", lambda p: p.w, "in_win.w (src)"),
    ("proc", 0x034, 0, 16, "abs", lambda p: p.h, "in_win.h (src)"),
    ("proc", 0x02c, 0, 16, "abs", lambda p: p.ow, "out_win.w (dst)"),
    ("proc", 0x02c, 16, 16, "rel", lambda p: p.dx, "stream.x + 4"),
    ("proc", 0x030, 0, 16, "abs", lambda p: p.oh, "out_win.h (dst)"),
    ("proc", 0x030, 18, 2, "abs", lambda p: 0, "cleared by WriteReg"),
    ("proc", 0x038, 0, 16, "abs", lambda p: p.phase_v, "V phase"),
    # 0x038[31:16] is NOT modelled: the firmware writes
    # out.w < node+0x90 ? node+0x90 - out.w + 16 : 16, and node+0x90 is never
    # set in ProcWinNode (unknown). Live reads 16; letterbox-test.sh phase3
    # tries the 1280 reading as a variant.
    ("proc", 0x03c, 0, 22, "abs", lambda p: p.ratio_v, "V ratio (in << 16) / out"),
    ("proc", 0x040, 0, 16, "abs", lambda p: p.ow, "out_win.w again (dst)"),
    ("proc", 0x044, 0, 16, "rel", lambda p: p.dx, "stream.x"),
    # line-enable window [start, max(in_h, out_h)] (0x8b1a6470; grey streak)
    ("proc", 0x050, 0, 16, "abs", lambda p: max(p.h, p.oh), "max(in_h, out_h)"),
    ("proc", 0x050, 16, 16, "rel", lambda p: p.dy - p.hflip, "vs_delay+1+vde_start+mb_420"),

    # --- panel (0x051c0000), PanelWinNode::WriteReg 0x8b1a5a38 ---
    # program window 0xbc/0xc0 and crtc 0xfe00/04 stay: stream.x - out.x
    ("lvds", 0x03c, 16, 16, "abs", lambda p: p.ow, "video_win_2.w (dst)"),
    ("lvds", 0x040, 16, 16, "abs", lambda p: p.oh, "video_win_2.h (dst)"),
    ("lvds", 0x0a4, 16, 16, "abs", lambda p: p.ow, "video_win_2.w (dst)"),
    ("lvds", 0x0a8, 16, 16, "abs", lambda p: p.oh, "video_win_2.h (dst)"),
    # H mirror: PanelWinNode::WriteReg 0x8b1a5c38..5c44 inserts node+0x10 (the
    # H flag CalcWindow stores at 0x8b1a537c). Stock orient-rear 80000000 ->
    # 80000001. Global: it reverses whatever the selector feeds the panel.
    ("lvds", 0x0a0, 0, 1, "abs", lambda p: p.hflip, "H mirror (fw 0x8b1a5c44)"),

    # --- border overlay (vblender 0x05200000), WriteBorderOverlay1 0x8b1a55d8 ---
    ("vblend", 0x000, 0, 12, "abs", lambda p: PANEL_W - p.dx - p.ow, "right"),
    ("vblend", 0x000, 16, 12, "abs", lambda p: p.dx, "left"),
    ("vblend", 0x000, 12, 4, "abs", lambda p: p.dy & 0xf, "top[3:0]"),
    ("vblend", 0x000, 28, 4, "abs", lambda p: (p.dy >> 4) & 0xf, "top[7:4]"),
    ("vblend", 0x004, 0, 12, "abs", lambda p: PANEL_H - p.dy - p.oh, "bottom"),
    ("vblend", 0x004, 12, 4, "abs", lambda p: (p.dy >> 8) & 0xf, "top[11:8]"),
    ("vblend", 0x004, 30, 1, "abs", lambda p: 1, "border enable"),
    # the overlays' panel rectangle {x 49, y vde, w 1280, h 720}: node+0x9c is
    # stored at 0x8b1a5460 BEFORE the H mirror's +1 (0x8b1a546c), which only
    # the program window gets, so the overlay y follows vde (elog
    # m_border_overlay_win [49,21] under H). Not in any stock dump.
    ("vblend", 0x010, 0, 16, "abs", lambda p: p.vde, "overlay 1 y (fw 0x8b1a56bc)"),
    ("vblend", 0x024, 0, 16, "abs", lambda p: p.vde, "overlay 2 y (fw 0x8b1a5874)"),
]

# Control bits. They share their word with state letterbox-apply drives
# itself (afbd+010 is source 0's CTRL, written on source on/off; comp+040
# carries the NR hold bit 25), so they are never written as whole words:
# they go out under "ctl" in the JSON and are applied read-modify-write.
# fw 0x8b1a43f0, called from NRWinNode::WriteReg's geometry group (flag
# 0x800, inside the hold bracket), for AFBD source mode 2 (comp+030[11:10]=3,
# ours and stock's). Stock orient-rear-ceiling: 03000013 -> 0300001B and
# 02090208 -> 02090200; nothing else moves -- AFBD flips internally.
CTL_FIELDS = [
    ("afbd", 0x010, 2, 2, "abs", lambda p: 2 if p.vflip else 0, "V mirror: bottom-up fetch"),
    ("comp", 0x040, 3, 1, "abs", lambda p: 0 if p.vflip else 1, "V mirror, source mode 2"),
]

# Fields the H mirror's line shift moves, and the V control bit: the
# self-test's mutations knock these out one group at a time.
HSHIFT = {("comp", 0x80c, 16), ("comp", 0x840, 0), ("comp", 0x858, 0),
          ("proc", 0x050, 16), ("vblend", 0x010, 0), ("vblend", 0x024, 0)}

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
    if p.ow % 2 or p.oh % 2:
        errs.append("destination width and height must be even")
    if p.ow < p.w or p.oh < p.h:
        errs.append("proc only magnifies: the destination cannot be smaller "
                    "than the source (the VE scales down)")
    if p.ow > 4 * p.w or p.oh > 4 * p.h:
        errs.append("more than 4x per axis: nothing measured beyond 0x4000")
    if p.dx < 0 or p.dy < 0 or p.dx + p.ow > PANEL_W or p.dy + p.oh > PANEL_H:
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


CTL = {(blk, off) for blk, off, *_ in CTL_FIELDS}

# Mirror modes as stock numbers them (PANEL_CONFIG_MIRROR / mirror_mode):
# bit 0 = H (panel line reversal), bit 1 = V (bottom-up fetch).
MODES = {"front": 0, "rear": 1, "rear-ceiling": 2, "ceiling": 3}


def hw_place(x, y, ow, oh, mode=0, rx=0, ry=0):
    """A client's rectangle and reflection -> hardware (dx, dy, hflip, vflip).

    The installation mode mirrors the whole screen, position included; a
    plane reflection (DRM REFLECT_X/Y) mirrors only the picture inside its
    rectangle. The panel's H reversal moves position AND content, so x is
    pre-mirrored only for a plane reflection; AFBD's V flip moves content
    only, so y is pre-mirrored only for the installation mode.
    """
    ih, iv = mode & 1, mode >> 1 & 1
    dx = PANEL_W - x - ow if rx else x
    dy = PANEL_H - y - oh if iv else y
    return dx, dy, ih ^ rx, iv ^ ry


def _mutant(p, fl, mutate):
    blk, off, lsb = fl[0], fl[1], fl[2]
    if mutate == "no-shift" and (blk, off, lsb) in HSHIFT:
        q = copy.copy(p); q.hflip = 0; return q
    if mutate == "proc-only" and (blk, off, lsb) in HSHIFT and blk != "proc":
        q = copy.copy(p); q.hflip = 0; return q
    if mutate == "v-polarity" and (blk, off) == ("comp", 0x040):
        q = copy.copy(p); q.vflip = 1 - p.vflip; return q
    if mutate == "no-panel-bit" and (blk, off) == ("lvds", 0x0a0):
        q = copy.copy(p); q.hflip = 0; return q
    return p


def recipe(live, p, mutate=None):
    """Return {(blk, off): (old, new, [notes])} for every touched register,
    the control words (CTL) included. `mutate` deliberately breaks one part of
    the mirror model, for the self-test."""
    out = {}
    for fl in FIELDS + CTL_FIELDS:
        blk, off, lsb, width, kind, f, prov = fl
        q = _mutant(p, fl, mutate)
        mask = ((1 << width) - 1) << lsb
        old = out.get((blk, off), (live[(blk, off)],))[0]
        cur = out.get((blk, off), (old, old, []))[1]
        if kind == "abs":
            val = f(q)
        else:
            base = (live[(blk, off)] & mask) >> lsb
            val = base + f(q) - f(NATIVE)
        if not 0 <= val < (1 << width):
            raise ValueError(f"{blk}+{off:03x}[{lsb + width - 1}:{lsb}] = {val} "
                             f"does not fit ({prov})")
        new = (cur & ~mask) | (val << lsb)
        notes = out.get((blk, off), (0, 0, []))[2] + [
            f"[{lsb + width - 1}:{lsb}]={val} {kind} {prov}"]
        out[(blk, off)] = (old, new, notes)
    return out


def self_test(live, stock=None):
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
    # 3. Scaled, against the firmware's own 720x480 -> 1280x720 log
    #    (wce-elog-bringup-2026-09-04.txt: "ratio [36864 x 43690]",
    #    pic_win [0, 0, 1280, 720]) and the proc words captured live at
    #    1280x640 -> 1280x720 on 2026-09-13 (handoff-2026-09-14 section 5).
    #    That capture's +050 length (640) and H integer phase (3) were the
    #    driver's errors of the day, so they are not compared.
    r = recipe(live, P(720, 480, 0, 0, ow=1280, oh=720))
    f = lambda k, lsb, w: (r[k][1] >> lsb) & ((1 << w) - 1)
    want = [(("proc", 0x008), 0, 22, 36864), (("proc", 0x03c), 0, 22, 43690),
            (("route", 0x124), 16, 16, 1280), (("route", 0x128), 16, 16, 720),
            (("proc", 0x034), 0, 32, 0x02D001E0), (("proc", 0x014), 27, 1, 0),
            (("proc", 0x050), 0, 16, 720)]
    r = recipe(live, P(1280, 640, 0, 0, ow=1280, oh=720))
    want2 = [(("proc", 0x000), 0, 16, 0x8000), (("proc", 0x038), 0, 16, 0xF1C7),
             (("proc", 0x03c), 0, 22, 0xE38E), (("proc", 0x008), 0, 22, 0x10000),
             (("proc", 0x008), 24, 3, 2), (("proc", 0x02c), 0, 16, 0x500),
             (("proc", 0x030), 0, 32, 0x000102D0), (("proc", 0x034), 0, 32, 0x05000280),
             (("proc", 0x040), 0, 32, 0xC0000500),
             # hardware, Phase 3 bisect p1 (2026-10-05): H here cut the picture
             (("comp", 0x858), 16, 16, 720)]
    for label, wl, rr in (("720x480->1280x720", want,
                           recipe(live, P(720, 480, 0, 0, ow=1280, oh=720))),
                          ("1280x640->1280x720", want2, r)):
        for k, lsb, w, v in wl:
            got = (rr[k][1] >> lsb) & ((1 << w) - 1)
            if got != v:
                ok = False
                print(f"FAIL {label} {k[0]}+{k[1]:03x}[{lsb + w - 1}:{lsb}]: "
                      f"model {got:#x} reference {v:#x}")
    if stock:
        ok &= stock_test(live, stock)
    print("self-test", "PASS" if ok else "FAIL",
          f"({len(FIELDS) + len(CTL_FIELDS)} fields, {len(recipe(live, NATIVE))} registers)")
    return ok


# Stock 2026-10-01 captures (local/h713-lab/stock-capture-20261001/out), all
# native 720p H.264 playing: mode 0 = the 1b clip and the keystone case
# (keystone is GPU-only); 1-3 = Installation mode rear / rear ceiling / front
# ceiling, two samples each.
STOCK_CASES = {0: ("1b-h264-1280x720-1", "1b-h264-1280x720-2",
                   "keystone-ltx10-1", "keystone-ltx10-2"),
               1: ("orient-rear-1", "orient-rear-2"),
               2: ("orient-rear-ceiling-1", "orient-rear-ceiling-2"),
               3: ("orient-front-ceiling-1", "orient-front-ceiling-2")}


def load_stock(path):
    words = {}
    for line in open(path):
        a, v = line.split()
        words[int(a, 16)] = int(v, 16)
    return words


def stock_test(live, stock_dir):
    """The mirror model against the firmware's own mirrored states.

    Stock never dumped the vblender, so those words come from our baseline;
    every other recipe register comes from stock's own mode-0 capture. Then
    the model, asked for each mode, must reproduce every recipe register the
    stock capture of that mode holds, and each mutation of the mirror model
    must fail somewhere."""
    ok = True
    caps = {m: [load_stock(os.path.join(stock_dir, c, "display.txt")) for c in cs]
            for m, cs in STOCK_CASES.items()}
    keys = list(recipe(live, NATIVE))
    addr = lambda k: BASES[k[0]] + k[1]
    # 1. our native baseline against stock mode 0 (diff against known-good).
    #    Only the words the mirror moves must agree: elsewhere our parked-MIPS
    #    state may legitimately differ (comp+278/2b8 bit 31 does), and those
    #    words keep our value.
    moved = {k for m in (1, 2, 3)
             for k, (old, new, _n) in recipe(live, P(PANEL_W, PANEL_H, 0, 0, hflip=m & 1,
                                                     vflip=m >> 1 & 1)).items()
             if old != new}
    for k in keys:
        for w in caps[0]:
            if addr(k) in w and w[addr(k)] != live[k]:
                if k in moved:
                    ok = False
                print(f"{'FAIL' if k in moved else '  note'} stock mode 0 "
                      f"{k[0]}+{k[1]:03x}: stock {w[addr(k)]:08X}, ours {live[k]:08X}"
                      + ("" if k in moved else " (the mirror does not move it)"))
                break
    base = dict(live)
    for k in keys:
        if addr(k) in caps[0][0]:
            base[k] = caps[0][0][addr(k)]
    print(f"  mirror moves {len(moved)} registers: "
          + " ".join(f"{k[0]}+{k[1]:03x}" for k in sorted(moved, key=addr)))
    compared = sum(addr(k) in caps[0][0] for k in keys)

    def mismatches(mode, mutate=None):
        p = P(PANEL_W, PANEL_H, 0, 0, hflip=mode & 1, vflip=mode >> 1 & 1)
        r = recipe(base, p, mutate)
        bad = []
        for k, (_old, new, _n) in r.items():
            for w in caps[mode]:
                if addr(k) in w and w[addr(k)] != new:
                    bad.append((k, w[addr(k)], new))
                    break
        return bad

    # 2. the model reproduces every mode
    for mode in (0, 1, 2, 3):
        for k, want, got in mismatches(mode):
            ok = False
            print(f"FAIL stock mode {mode} {k[0]}+{k[1]:03x}: stock {want:08X}, "
                  f"model {got:08X}")
    # 3. each mutation is caught
    for mutate in ("no-shift", "proc-only", "v-polarity", "no-panel-bit"):
        caught = sum(len(mismatches(m, mutate)) for m in (1, 2, 3))
        if not caught:
            ok = False
            print(f"FAIL mutation {mutate} is not caught by the stock captures")
        else:
            print(f"  mutation {mutate}: caught ({caught} mismatches)")
    print(f"  stock mirror: {compared} recipe registers in the stock dumps, "
          f"modes 0-3 x {sum(map(len, caps.values()))} captures")
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--live", required=True, help="letterbox-baseline.py dump, native 720p video on")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--stock", metavar="DIR",
                    help="with --self-test: also check the mirror model against "
                         "the stock captures (local/h713-lab/stock-capture-20261001/out)")
    ap.add_argument("--mirror", default="0",
                    help="installation mode: 0-3 or front|rear|rear-ceiling|ceiling "
                         "(bit 0 H, bit 1 V); mirrors the whole screen")
    ap.add_argument("--reflect", default="", choices=("", "x", "y", "xy", "180"),
                    help="plane reflection (DRM REFLECT_X/Y; 180 = both): mirrors the "
                         "picture inside its rectangle")
    ap.add_argument("--fmt", choices=("nv12", "p010"), default="nv12")
    ap.add_argument("--pitch", type=int, help="bytes per line (default: tight)")
    ap.add_argument("--out", metavar="OWxOH",
                    help="destination size on the panel (default: the source "
                         "size, unscaled); proc magnifies W x H up to it")
    ap.add_argument("size", nargs="?", help="WxH of the picture in memory")
    ap.add_argument("at", nargs="?", default="centre", help="X,Y on the panel, or 'centre'")
    ap.add_argument("--json", metavar="FILE",
                    help="also write the recipe for letterbox-apply.py")
    a = ap.parse_args()
    live = load_live(a.live)
    if a.self_test:
        return 0 if self_test(live, a.stock) else 1
    mode = MODES[a.mirror] if a.mirror in MODES else int(a.mirror, 0)
    if not 0 <= mode <= 3:
        ap.error("--mirror is 0-3")
    rx = int(a.reflect in ("x", "xy", "180"))
    ry = int(a.reflect in ("y", "xy", "180"))
    if not a.size:
        ap.error("give WxH, or --self-test")
    w, h = (int(v) for v in a.size.lower().split("x"))
    ow, oh = (int(v) for v in a.out.lower().split("x")) if a.out else (w, h)
    if a.at == "centre":
        dx, dy = (PANEL_W - ow) // 2 & ~1, (PANEL_H - oh) // 2
    else:
        dx, dy = (int(v) for v in a.at.split(","))
    cx, cy = dx, dy
    if not (0 <= cx and 0 <= cy and cx + ow <= PANEL_W and cy + oh <= PANEL_H):
        print("refused: picture must lie fully on the panel", file=sys.stderr)
        return 1
    dx, dy, hflip, vflip = hw_place(cx, cy, ow, oh, mode, rx, ry)
    p = P(w, h, dx, dy, a.fmt, a.pitch, ow, oh, hflip, vflip)
    errs = check(p)
    if errs:
        for e in errs:
            print("refused:", e, file=sys.stderr)
        return 1
    ylen, clen = buffer_needs(p)
    print(f"# {w}x{h} {a.fmt} pitch {p.pitch} shown {ow}x{oh} at ({dx},{dy}); "
          f"borders L{dx} R{PANEL_W - dx - ow} T{dy} B{PANEL_H - dy - oh}")
    if mode or rx or ry:
        print(f"# mirror mode {mode}, reflect {a.reflect or 'none'}: client ({cx},{cy}) "
              f"-> hardware ({dx},{dy}), panel H {hflip}, fetch V {vflip}")
        if vflip and h % 16:
            print(f"# WARNING: V flip with a height ({h}) not a multiple of 16 -- "
                  "AFBD reads whole blocks; whether the padding rows flip into "
                  "view is untested (WP5 Phase 1 step ab-v)")
    if (ow, oh) != (w, h):
        print(f"# proc ratio H {p.ratio_h:#x} V {p.ratio_v:#x}, phase H "
              f"{p.phase_h:#x}/{p.int_h} V {p.phase_v:#x}/{p.int_v}")
    print(f"# buffer must cover luma {ylen} B and chroma {clen} B from the "
          f"plane offsets (AFBD reads {a16(w)}x{a16(h)})")
    print("# write order (firmware): source 0 off; NR hold (comp+040[25]=0, "
          "+860[17]=1, +138[27]=1); afbd; comp; NR release (+040[25]=1, "
          "+860[17]=0, +138[27]=0, +82c[15:0]=1); route+proc; lvds; vblend; "
          "source 0 on with the frame queued")
    for (blk, off), (old, new, notes) in sorted(recipe(live, p).items(),
                                                key=lambda kv: BASES[kv[0][0]] + kv[0][1]):
        mark = ("" if old == new else "  *") + ("  (ctl: read-modify-write)"
                                                 if (blk, off) in CTL else "")
        print(f"{BASES[blk] + off:#010x} {blk}+{off:03x} {old:08X} -> {new:08X}{mark}")
        for n in notes:
            print(f"    {n}")
    if a.json:
        regs = recipe(live, p)
        doc = {
            "picture": {"w": w, "h": h, "ow": ow, "oh": oh, "dx": dx, "dy": dy,
                        "fmt": a.fmt, "hflip": hflip, "vflip": vflip,
                        "mirror": mode, "reflect": a.reflect,
                        "pitch": p.pitch, "stride": p.stride},
            "buffer": {"luma_bytes": ylen, "chroma_bytes": clen},
            "live": a.live,
            # FIELDS order: afbd, comp, route, proc, lvds, vblend
            "regs": [{"block": blk, "off": off, "addr": BASES[blk] + off,
                      "old": old, "new": new, "notes": notes}
                     for (blk, off), (old, new, notes) in regs.items()
                     if (blk, off) not in CTL],
            # words shared with source on/off and the NR hold: apply only the
            # mirror bits, read-modify-write (afbd+010 with source 0's CTRL,
            # comp+040 inside the hold bracket)
            "ctl": [{"block": blk, "off": off, "addr": BASES[blk] + off,
                     "lsb": lsb, "width": width,
                     "value": (regs[(blk, off)][1] >> lsb) & ((1 << width) - 1),
                     "notes": prov}
                    for blk, off, lsb, width, _k, _f, prov in CTL_FIELDS],
        }
        with open(a.json, "w") as f:
            json.dump(doc, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
