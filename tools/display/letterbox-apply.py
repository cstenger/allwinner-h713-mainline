#!/usr/bin/env python3
"""Apply one letterbox recipe to the live display, hold, then restore.
RUNS ON THE TARGET, as root, with letterbox-card holding the native card.

    letterbox-apply.py --recipe step.json --region ab --hold 10 --pre 5
    letterbox-apply.py --recipe step.json --region ab --dry-run
    letterbox-apply.py --sequence seq.json --pre 30 --gap 5 --hold 10
    letterbox-apply.py --show step.json
    letterbox-apply.py --restore /tmp/letterbox-saved.json     # emergency only

The recipe comes from tools/display/letterbox-recipe.py --json. The region
(the card to show) comes from /tmp/letterbox-card.layout, which letterbox-card
writes once its native card is on the plane.

SEQUENCE, from the firmware (docs/reference/letterbox-recipe-2026-10-04.md):

  source 0 off       CTRL idle, READY, poll READY clear (the driver's stop,
                     minus zeroing the slots and switching to RGB)
  slots              AFBD Y0-3 / C0-3 -> the step card's region
  AFBD geometry      recipe, block afbd
  NR hold            comp+860[17]=1, +138[27]=1, +040[25]=0   (flags 0x100c0)
  NR geometry        recipe, block comp, in WriteReg's flag order
  NR release         +860[17]=0, +138[27]=0 & +82c=1, +040[25]=1  (0x8120)
  route, proc        recipe                                    (0x400000)
  lvds, vblender     recipe                                    (0x800000)
  source 0 on        DIRTY, CTRL active, READY, poll

then hold, then the same in reverse back to the saved values. The restore runs
in `finally`, ignores further signals, and is best effort: it keeps going past
a register that will not stick and reports every one.

WP5 MIRROR (docs/mirror-plan.md). A recipe's "ctl" entries are the V-mirror
bits that share a word with state this script drives: afbd+010[3:2] goes into
the CTRL value source 0 is switched on with, comp+040[3] is written
read-modify-write inside the NR hold (its word also carries the hold bit).
A sequence entry with "kind": "osd" is a primary-route step instead: the card
is letterbox-card --primary on the OSD channel (selector RGB), and the step
flips bits in the OSD control (0x05600140, latched by READY 0x05600144)
and/or the panel's H-mirror bit (0x051c00a0[0]), then restores them.

REFUSES before writing anything unless: the native card is on the plane
(CTRL active, selector on video, all eight slots on the native card); every
register the recipe touches reads exactly the recipe's `old` value; the NR
bracket is in its released state; and the region matches the recipe's
picture and holds the bytes AFBD will fetch.
"""
import argparse
import json
import mmap
import os
import signal
import sys
import time

AFBD = 0x05600000
CTRL, READY, DIRTY = AFBD + 0x010, AFBD + 0x014, AFBD + 0x06c
SLOTS_Y = [AFBD + 0x070 + 4 * i for i in range(4)]
SLOTS_C = [AFBD + 0x084 + 4 * i for i in range(4)]
SELECTOR = 0x051c006c
CTRL_ON, SEL_VIDEO = 0x03000013, 0x39000000
OSD_CTRL, OSD_READY, OSD_SRC = AFBD + 0x140, AFBD + 0x144, AFBD + 0x178
OSD_CTRL_ON, SEL_RGB = 0x03001901, 0x29000000
PANEL_A0 = 0x051c00a0      # [0] = H mirror (PanelWinNode::WriteReg)

COMP = 0x05000000
NR_860, NR_138, NR_040, NR_82C = COMP + 0x860, COMP + 0x138, COMP + 0x040, COMP + 0x82c
# NRWinNode::WriteReg's flag order: 0x4 (A), 0x2 (B), 0x400, 0x1000, 0x2000, 0x4000
COMP_ORDER = [0x0f0, 0x174, 0x178, 0x1b4, 0x1b8,
              0x210, 0x224, 0x274, 0x278, 0x2b4, 0x2b8,
              0x804, 0x808, 0x80c,
              0x854, 0x858, 0x85c, 0x860,
              0x844, 0x840]
LAYOUT = "/tmp/letterbox-card.layout"
SAVED = "/tmp/letterbox-saved.json"
T0 = time.monotonic()
RESTORE_FAILED = False


def log(msg):
    print(f"[{time.monotonic() - T0:7.3f}] {msg}", flush=True)


class Interrupted(Exception):
    pass


def on_signal(sig, _frame):
    raise Interrupted(signal.Signals(sig).name)


class Mem:
    """One aligned 32-bit access per call, through /dev/mem pages."""

    def __init__(self, dry):
        self.dry = dry
        self.fd = os.open("/dev/mem", (os.O_RDONLY if dry else os.O_RDWR) | os.O_SYNC)
        self.pages = {}
        self.failures = []

    def _word(self, addr):
        page = addr & ~0xfff
        if page not in self.pages:
            prot = mmap.PROT_READ if self.dry else mmap.PROT_READ | mmap.PROT_WRITE
            m = mmap.mmap(self.fd, 4096, mmap.MAP_SHARED, prot, offset=page)
            self.pages[page] = (m, memoryview(m).cast("I"))
        return self.pages[page][1], (addr & 0xfff) // 4

    def rd(self, addr):
        mv, i = self._word(addr)
        return mv[i]

    def wr(self, addr, val, what, verify=True):
        if self.dry:
            log(f"  would write {addr:#010x} = {val:08X}  {what}")
            return True
        mv, i = self._word(addr)
        mv[i] = val
        if not verify:
            log(f"  {addr:#010x} <- {val:08X}  {what}")
            return True
        got = mv[i]
        ok = got == val
        log(f"  {addr:#010x} <- {val:08X}  reads {got:08X}  {what}"
            + ("" if ok else "   *** DID NOT STICK"))
        if not ok:
            self.failures.append((addr, val, got, what))
        return ok

    def bits(self, addr, lsb, width, val, what):
        mask = ((1 << width) - 1) << lsb
        return self.wr(addr, (self.rd(addr) & ~mask) | (val << lsb), what)

    def poll_clear(self, addr, what, timeout=0.1):
        if self.dry:
            log(f"  would poll {addr:#010x} until 0  {what}")
            return True
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.rd(addr) == 0:
                return True
            time.sleep(0.0005)
        log(f"  *** {what}: {addr:#010x} still {self.rd(addr):08X} after "
            f"{timeout * 1000:.0f} ms")
        self.failures.append((addr, 0, self.rd(addr), what))
        return False


def load_layout():
    lay = {"regions": {}}
    for line in open(LAYOUT):
        f = line.split()
        if f[0] == "region":
            lay["regions"][f[1]] = dict(zip(
                ("w", "h", "stride", "rows", "y_off", "c_off"), map(int, f[2:8])))
        elif f[0] in ("slot_y", "slot_c"):
            lay[f[0]] = int(f[1], 16)
        elif f[0] == "bo_size":
            lay["bo_size"] = int(f[1])
        elif f[0] == "mode":
            lay["mode"] = f[1]
        elif f[0] in ("osd_ctrl", "osd_src"):
            lay[f[0]] = int(f[1], 16)
    return lay


def field(val, c):
    return (val >> c["lsb"]) & ((1 << c["width"]) - 1)


def ctl_split(rec):
    """A recipe's V-mirror control bits: (afbd CTRL fields, comp+040 fields)."""
    ctl = rec.get("ctl", [])
    return ([c for c in ctl if c["addr"] == CTRL],
            [c for c in ctl if c["addr"] == NR_040])


def with_ctl(word, fields, key):
    for c in fields:
        m = ((1 << c["width"]) - 1) << c["lsb"]
        word = (word & ~m) | (c[key] << c["lsb"])
    return word


def ordered(regs):
    """Recipe registers grouped and ordered as the firmware writes them."""
    by = {}
    for r in regs:
        by.setdefault(r["block"], []).append(r)
    comp = sorted(by.get("comp", []), key=lambda r: COMP_ORDER.index(r["off"]))
    return (by.get("afbd", []), comp,
            by.get("route", []) + by.get("proc", []),
            by.get("lvds", []) + by.get("vblend", []))


def source_off(mem, idle):
    log("source 0 off")
    mem.wr(CTRL, idle, "CTRL idle")
    mem.wr(READY, 1, "READY", verify=False)
    mem.poll_clear(READY, "source-off commit")


def source_on(mem, ctrl):
    log("source 0 on")
    mem.wr(DIRTY, 1, "DIRTY (publish slots)", verify=False)
    mem.wr(CTRL, ctrl, "CTRL active")
    mem.wr(READY, 1, "READY", verify=False)
    mem.poll_clear(READY, "source-on commit")


def nr_hold(mem):
    log("NR hold (flags 0x100c0)")
    mem.bits(NR_860, 17, 1, 1, "comp+860[17]=1")
    mem.bits(NR_138, 27, 1, 1, "comp+138[27]=1")
    mem.bits(NR_040, 25, 1, 0, "comp+040[25]=0")


def nr_release(mem):
    log("NR release (flags 0x8120)")
    mem.bits(NR_860, 17, 1, 0, "comp+860[17]=0")
    mem.bits(NR_138, 27, 1, 0, "comp+138[27]=0")
    mem.bits(NR_82C, 0, 16, 1, "comp+82c[15:0]=1")
    mem.bits(NR_040, 25, 1, 1, "comp+040[25]=1")


def write_group(mem, regs, key, label):
    ok = True
    for r in regs:
        ok &= mem.wr(r["addr"], r[key], f"{label} {r['block']}+{r['off']:03x}")
    return ok


def recheck(mem, regs, when, ctl=()):
    """Re-read every recipe register during the window. The write-time
    readback cannot see a register the hardware rewrites a few frames later;
    this can. scanout-grab cannot help here: the plane's framebuffer is the
    native card throughout, so it shows the native card for every step."""
    drift = [(r, mem.rd(r["addr"])) for r in regs if mem.rd(r["addr"]) != r["new"]]
    for r, now in drift:
        log(f"  RECHECK {when}: {r['block']}+{r['off']:03x} reads {now:08X}, "
            f"wrote {r['new']:08X}")
    for c in ctl:
        if field(mem.rd(c["addr"]), c) != c["value"]:
            log(f"  RECHECK {when}: ctl {c['block']}+{c['off']:03x}"
                f"[{c['lsb'] + c['width'] - 1}:{c['lsb']}] reads "
                f"{field(mem.rd(c['addr']), c)}, wrote {c['value']}")
    status = " ".join(f"{a:#x}={mem.rd(a):08X}" for a in (CTRL, SELECTOR, SLOTS_Y[0]))
    log(f"RECHECK {when}: {len(regs) - len(drift)}/{len(regs)} registers as written; {status}")


def restore(mem, saved):
    """Back to the saved state. Best effort: never stops early."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    mem.failures = []
    log("=== WINDOW CLOSED: restoring ===")
    if saved.get("kind") == "osd":
        return restore_osd(mem, saved)
    afbd, comp, route_proc, panel = ordered(saved["regs"])
    _ctl_afbd, ctl_comp = ctl_split(saved)
    source_off(mem, saved["ctrl"] & ~0x3)
    for a, v in zip(SLOTS_Y + SLOTS_C, saved["slots"]):
        mem.wr(a, v, "slot (native)")
    write_group(mem, afbd, "old", "restore")
    nr_hold(mem)
    for c in ctl_comp:
        mem.bits(NR_040, c["lsb"], c["width"], c["old"], "comp+040 V-mirror bit (native)")
    write_group(mem, list(reversed(comp)), "old", "restore")
    nr_release(mem)
    for a, v in saved["bracket"].items():
        mem.wr(int(a), v, "bracket (saved)")
    write_group(mem, list(reversed(route_proc)), "old", "restore")
    write_group(mem, list(reversed(panel)), "old", "restore")
    source_on(mem, saved["ctrl"])
    bad = [(r["addr"], r["old"], mem.rd(r["addr"])) for r in saved["regs"]
           if mem.rd(r["addr"]) != r["old"]]
    bad += [(a, v, mem.rd(a)) for a, v in zip(SLOTS_Y + SLOTS_C, saved["slots"])
            if mem.rd(a) != v]
    if mem.rd(CTRL) != saved["ctrl"]:
        bad.append((CTRL, saved["ctrl"], mem.rd(CTRL)))
    bad += [(NR_040, c["old"], field(mem.rd(NR_040), c)) for c in ctl_comp
            if field(mem.rd(NR_040), c) != c["old"]]
    for a, want, got in bad:
        log(f"  *** {a:#010x} reads {got:08X}, saved {want:08X}")
    if bad or mem.failures:
        log("RESTORE INCOMPLETE -- run: letterbox-apply.py --restore " + SAVED)
        return False
    log("RESTORED: every touched register reads its saved value")
    return True


def preflight(mem, rec, lay, region):
    errs = []
    pic = rec["picture"]
    rg = lay["regions"].get(region)
    if rg is None:
        return [f"no region {region} in {LAYOUT}"], None
    if (rg["w"], rg["h"], rg["stride"]) != (pic["w"], pic["h"], pic["stride"]):
        errs.append(f"region {region} is {rg['w']}x{rg['h']} stride {rg['stride']}, "
                    f"recipe is {pic['w']}x{pic['h']} stride {pic['stride']}")
    if rg["stride"] * rg["rows"] < rec["buffer"]["luma_bytes"] or \
       rg["stride"] * rg["rows"] // 2 < rec["buffer"]["chroma_bytes"]:
        errs.append("region is smaller than the block-aligned fetch")
    if rg["c_off"] + rg["stride"] * rg["rows"] // 2 > lay["bo_size"]:
        errs.append("region runs past the buffer object")
    if mem.rd(CTRL) != CTRL_ON:
        errs.append(f"source 0 CTRL {mem.rd(CTRL):08X}, want {CTRL_ON:08X} (card not up?)")
    if mem.rd(SELECTOR) != SEL_VIDEO:
        errs.append(f"selector {mem.rd(SELECTOR):08X}, want {SEL_VIDEO:08X}")
    for a in SLOTS_Y:
        if mem.rd(a) != lay["slot_y"]:
            errs.append(f"Y slot {a:#010x} = {mem.rd(a):08X}, card's is {lay['slot_y']:08X}")
    for a in SLOTS_C:
        if mem.rd(a) != lay["slot_c"]:
            errs.append(f"C slot {a:#010x} = {mem.rd(a):08X}, card's is {lay['slot_c']:08X}")
    for r in rec["regs"]:
        cur = mem.rd(r["addr"])
        if cur != r["old"]:
            errs.append(f"{r['block']}+{r['off']:03x} reads {cur:08X}, recipe's old is "
                        f"{r['old']:08X} -- the baseline does not match this board state")
    for c in rec.get("ctl", []):
        if field(mem.rd(c["addr"]), c) != c["old"]:
            errs.append(f"ctl {c['block']}+{c['off']:03x} field reads "
                        f"{field(mem.rd(c['addr']), c)}, native is {c['old']} -- "
                        "a mirror is already on")
    if not mem.rd(NR_040) >> 25 & 1 or mem.rd(NR_860) >> 17 & 1 or mem.rd(NR_138) >> 27 & 1:
        errs.append("NR bracket is not in its released state")
    base = lay["slot_y"] - lay["regions"]["native"]["y_off"]
    return errs, (base + rg["y_off"], base + rg["c_off"])


def run_step(mem, lay, rec, region, hold, pre, dry, name=""):
    """Preflight, apply, hold, restore. 0 = done and restored."""
    global RESTORE_FAILED
    mem.failures = []
    pic = rec["picture"]
    shown = (pic.get("ow", pic["w"]), pic.get("oh", pic["h"]))
    log(f"step {name}: {pic['w']}x{pic['h']} stride {pic['stride']}"
        + (f" -> {shown[0]}x{shown[1]}" if shown != (pic["w"], pic["h"]) else "")
        + " at "
        f"({pic['dx']},{pic['dy']}), region {region}, hold {hold:g}s"
        + ("  [DRY RUN]" if dry else ""))

    errs, addrs = preflight(mem, rec, lay, region)
    if errs:
        for e in errs:
            log("REFUSED: " + e)
        log("nothing was written")
        return 1
    y_addr, c_addr = addrs
    log(f"preflight OK; card slots Y {y_addr:08X} C {c_addr:08X}")

    saved = {"ctrl": mem.rd(CTRL),
             "slots": [mem.rd(x) for x in SLOTS_Y + SLOTS_C],
             "bracket": {str(x): mem.rd(x) for x in (NR_860, NR_138, NR_82C, NR_040)},
             "regs": rec["regs"], "ctl": rec.get("ctl", [])}
    if not dry:
        with open(SAVED + ".tmp", "w") as f:
            json.dump(saved, f)
        os.replace(SAVED + ".tmp", SAVED)
        log(f"saved state in {SAVED}")

    afbd, comp, route_proc, panel = ordered(rec["regs"])
    ctl_afbd, ctl_comp = ctl_split(rec)
    ctrl_on = with_ctl(saved["ctrl"], ctl_afbd, "value")
    for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(s, on_signal)
    applied = False
    ok = True
    try:
        if pre > 0 and not dry:
            log(f"window opens in {pre:g} s")
            time.sleep(pre)
        applied = not dry
        source_off(mem, saved["ctrl"] & ~0x3)
        for x in SLOTS_Y:
            ok &= mem.wr(x, y_addr, "slot Y -> card")
        for x in SLOTS_C:
            ok &= mem.wr(x, c_addr, "slot C -> card")
        ok &= write_group(mem, afbd, "new", "apply")
        nr_hold(mem)
        for c in ctl_comp:
            ok &= mem.bits(NR_040, c["lsb"], c["width"], c["value"], "comp+040 V-mirror bit")
        ok &= write_group(mem, comp, "new", "apply")
        nr_release(mem)
        ok &= write_group(mem, route_proc, "new", "apply")
        ok &= write_group(mem, panel, "new", "apply")
        source_on(mem, ctrl_on)
        if not ok or mem.failures:
            log("*** a write did not stick or a commit did not retire: aborting")
            return 1
        if dry:
            log("dry run complete; nothing was written")
            return 0
        log(f"=== WINDOW OPEN: step {name} {pic['w']}x{pic['h']} at "
            f"({pic['dx']},{pic['dy']}) for {hold:g} s === wall {time.time():.3f}")
        end = time.monotonic() + hold
        mid = time.monotonic() + hold / 2
        checked = False
        while time.monotonic() < end - 0.5:
            time.sleep(max(0.0, min(1.0, end - 0.5 - time.monotonic())))
            if not checked and time.monotonic() >= mid:
                recheck(mem, rec["regs"], "mid-hold", rec.get("ctl", []))
                checked = True
        recheck(mem, rec["regs"], "end of hold", rec.get("ctl", []))
        while time.monotonic() < end:
            time.sleep(min(1.0, end - time.monotonic()))
        return 0
    except Interrupted as e:
        log(f"interrupted by {e}")
        return 1
    finally:
        if applied and not restore(mem, saved):
            RESTORE_FAILED = True


def preflight_osd(mem, lay):
    errs = []
    if lay.get("mode") != "primary":
        errs.append(f"{LAYOUT} is not a primary-card layout (run letterbox-card --primary)")
        return errs
    if mem.rd(SELECTOR) != SEL_RGB:
        errs.append(f"selector {mem.rd(SELECTOR):08X}, want {SEL_RGB:08X} (RGB route)")
    if mem.rd(OSD_CTRL) != OSD_CTRL_ON or lay["osd_ctrl"] != OSD_CTRL_ON:
        errs.append(f"OSD ctrl {mem.rd(OSD_CTRL):08X} (layout {lay['osd_ctrl']:08X}), "
                    f"want {OSD_CTRL_ON:08X}")
    src = mem.rd(OSD_SRC)
    if src != lay["osd_src"]:
        errs.append(f"OSD source {src:08X} is not the card's {lay['osd_src']:08X}")
    if mem.rd(PANEL_A0) & 1:
        errs.append(f"panel {PANEL_A0:#x} bit 0 already set -- a mirror is on")
    time.sleep(0.1)
    if mem.rd(OSD_SRC) != src:
        errs.append("the OSD source moved within 100 ms: something is flipping the "
                    "primary plane, and the driver rewrites the OSD control on every flip")
    return errs


def osd_commit(mem, ctrl, what):
    ok = mem.wr(OSD_CTRL, ctrl, what)
    mem.wr(OSD_READY, 1, "OSD READY", verify=False)
    return mem.poll_clear(OSD_READY, "OSD commit") and ok


def restore_osd(mem, saved):
    osd_commit(mem, saved["osd_ctrl"], "OSD ctrl (saved)")
    mem.wr(PANEL_A0, saved["panel"], "panel 0x0a0 (saved)")
    bad = [(a, v, mem.rd(a)) for a, v in ((OSD_CTRL, saved["osd_ctrl"]),
                                          (PANEL_A0, saved["panel"])) if mem.rd(a) != v]
    for a, want, got in bad:
        log(f"  *** {a:#010x} reads {got:08X}, saved {want:08X}")
    if bad or mem.failures:
        log("RESTORE INCOMPLETE -- run: letterbox-apply.py --restore " + SAVED)
        return False
    log("RESTORED: every touched register reads its saved value")
    return True


def run_osd_step(mem, lay, rec, hold, pre, dry, name=""):
    """A primary-route mirror step: OSD control bits and/or the panel bit."""
    global RESTORE_FAILED
    mem.failures = []
    bits, panel_h = rec.get("osd_bits"), rec.get("panel_h", 0)
    log(f"step {name}: primary route, OSD bits "
        + (f"[{bits['lsb'] + bits['width'] - 1}:{bits['lsb']}]={bits['value']}" if bits else "none")
        + f", panel H {panel_h}, hold {hold:g}s" + ("  [DRY RUN]" if dry else ""))
    errs = preflight_osd(mem, lay)
    if errs:
        for e in errs:
            log("REFUSED: " + e)
        log("nothing was written")
        return 1
    log("preflight OK")
    saved = {"kind": "osd", "osd_ctrl": mem.rd(OSD_CTRL), "panel": mem.rd(PANEL_A0)}
    if not dry:
        with open(SAVED + ".tmp", "w") as f:
            json.dump(saved, f)
        os.replace(SAVED + ".tmp", SAVED)
    ctrl = saved["osd_ctrl"]
    if bits:
        m = ((1 << bits["width"]) - 1) << bits["lsb"]
        ctrl = (ctrl & ~m) | (bits["value"] << bits["lsb"])
    for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(s, on_signal)
    applied = False
    try:
        if pre > 0 and not dry:
            log(f"window opens in {pre:g} s")
            time.sleep(pre)
        applied = not dry
        ok = True
        if bits:
            ok &= osd_commit(mem, ctrl, "OSD ctrl (mirror bits)")
        if panel_h:
            ok &= mem.bits(PANEL_A0, 0, 1, 1, "panel H mirror")
        if not ok or mem.failures:
            log("*** a write did not stick or a commit did not retire: aborting")
            return 1
        if dry:
            log("dry run complete; nothing was written")
            return 0
        log(f"=== WINDOW OPEN: step {name} === wall {time.time():.3f}")
        end = time.monotonic() + hold
        while time.monotonic() < end:
            time.sleep(min(1.0, end - time.monotonic()))
            if mem.rd(OSD_CTRL) != ctrl or (panel_h and not mem.rd(PANEL_A0) & 1):
                log(f"  RECHECK: OSD ctrl {mem.rd(OSD_CTRL):08X} (wrote {ctrl:08X}), "
                    f"panel {mem.rd(PANEL_A0):08X}")
        return 0
    except Interrupted as e:
        log(f"interrupted by {e}")
        return 1
    finally:
        if applied and not restore(mem, saved):
            RESTORE_FAILED = True


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--recipe")
    ap.add_argument("--region", help="card region from the layout: native, ab, c, s640, s352 or s720")
    ap.add_argument("--sequence", metavar="FILE",
                    help='JSON list of {"name", "recipe", "region"}, run in order; '
                         "stops at the first refusal, failure or interruption")
    ap.add_argument("--hold", type=float, default=10.0)
    ap.add_argument("--pre", type=float, default=5.0,
                    help="seconds of countdown before the (first) step writes anything")
    ap.add_argument("--gap", type=float, default=5.0,
                    help="seconds of control card between sequence steps")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--show", metavar="RECIPE")
    ap.add_argument("--restore", metavar="SAVED")
    a = ap.parse_args()

    if a.show:
        rec = json.load(open(a.show))
        mem = Mem(dry=True)
        for r in rec["regs"]:
            cur = mem.rd(r["addr"])
            state = "old" if cur == r["old"] else "NEW" if cur == r["new"] else "???"
            print(f"{r['addr']:#010x} {r['block']}+{r['off']:03x} {cur:08X}  "
                  f"old {r['old']:08X} new {r['new']:08X}  {state}")
        print(f"CTRL {mem.rd(CTRL):08X} selector {mem.rd(SELECTOR):08X} "
              f"Y0 {mem.rd(SLOTS_Y[0]):08X} C0 {mem.rd(SLOTS_C[0]):08X}")
        return 0

    if a.restore:
        saved = json.load(open(a.restore))
        return 0 if restore(Mem(dry=False), saved) else 1

    lay = load_layout()
    mem = Mem(dry=a.dry_run)
    if a.sequence:
        seq = json.load(open(a.sequence))
        total = a.pre + len(seq) * a.hold + (len(seq) - 1) * a.gap
        log(f"sequence {' '.join(s['name'] for s in seq)}: first window in "
            f"{a.pre:g} s, about {total:.0f} s in all")
        for i, st in enumerate(seq):
            wait = a.pre if i == 0 else a.gap
            if st.get("kind") == "osd":
                rc = run_osd_step(mem, lay, st, a.hold, wait, a.dry_run, st["name"])
            else:
                rc = run_step(mem, lay, json.load(open(st["recipe"])), st["region"],
                              a.hold, wait, a.dry_run, st["name"])
            if rc or RESTORE_FAILED:
                log(f"SEQUENCE ABORTED at step {st['name']}")
                return rc or 1
        log("SEQUENCE COMPLETE" + (" (dry run)" if a.dry_run else ""))
        return 0
    if not (a.recipe and a.region):
        ap.error("--recipe and --region, --sequence, or --show / --restore")
    return run_step(mem, lay, json.load(open(a.recipe)), a.region,
                    a.hold, a.pre, a.dry_run)


if __name__ == "__main__":
    rc = main()
    sys.exit(3 if RESTORE_FAILED else rc)
