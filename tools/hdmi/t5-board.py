#!/usr/bin/env python3
"""T5 (board side): show the firmware's HDMI picture on the panel, then revert.

docs/hdmi-panel-source-design-2026-10-23.md section 10.14.  Runs on the
board as a transient systemd unit, so the revert does not depend on the ssh
session.  It must be on a boot with kernel 0188's pool identity map (the T4
FIT).  The writes are exactly these, checked against an allowlist:

  firmware shell        memory_agent en 4 / memory_agent dis 4
                        (T6, --with-nr: also en/dis 5 and 6, NR history DMA)
  0x051c006c selector   0x29000000 (console) <-> 0x39000000 (video)
  0x05140508 chroma     gain_idle (read at start) <-> 0x144c0000 (the KMS value)

Timeline after `start` (the operator films the panel):
  t=0      en 4; require the fetch tell (AFBD +0x58/+0x5c moving) and 0 faults
  t~5 s    stage A: selector -> video; chroma gain still idle = greyscale
  t~20 s   stage B: chroma gain -> 0x144c0000 = colour
  t~35 s   revert: gain idle, selector console, dis 4

Revert runs in a finally block on every path, and at once on an IOMMU
interrupt status bit, a new kernel fault line, a TCON 720p word changing, or
the panel mirror word changing.  Reads 0x07091xxx, 0x0694xxxx and RTC GP7
never.

T6 (section 10.16) is the same sequence with --with-nr: before en 4 it runs
en 5 and en 6, the NR history pairs the firmware's own signal set 0x78 has
on, and requires their enable bits (composition 0x178/0x1b8, 0x278/0x2b8
bit 31); the revert ends with dis 6 and dis 5.

    t5-board.py check [--with-nr]            # preconditions only, no writes
    t5-board.py run --confirm-t5 [--with-nr] # the sequence
    t5-board.py revert           # the revert alone, idempotent
    t5-board.py --self-test      # offline: fake registers and shell
"""
import argparse
import json
import mmap
import os
import re
import subprocess
import sys
import time

SEL, GAIN = 0x051C006C, 0x05140508
SEL_CONSOLE, SEL_VIDEO, GAIN_COLOUR = 0x29000000, 0x39000000, 0x144C0000
AFBD10, FETCH = 0x05600010, (0x05600058, 0x0560005C)
PAIR, BYPASS, IOMMU_STA = 0x05600320, 0x02010030, 0x02010108
TCON = (0x0588001C, 0x05880020, 0x05880024)
MIRROR, BLUE = 0x051C00A0, (0x05140D54, 0x051C00B8, 0x051C0364)
MEMAGENT_PTR = 0x8B499B14
# NR history DMA: enable bit 31 of each line-count word; addresses in 16-byte units
NR_EN = (0x05000178, 0x050001B8, 0x05000278, 0x050002B8)
NR_ADDR = {0x05000140: 0x04D35A00, 0x05000180: 0x04D02800, 0x05000240: 0x04D35A00, 0x05000280: 0x04D02800}
SHELL_OK = ("memory_agent en 4", "memory_agent dis 4", "memory_agent en 5", "memory_agent dis 5",
            "memory_agent en 6", "memory_agent dis 6")
SHELL = ["python3", "-u", "/usr/lib/h713-hdmi/mips-shell.py"]
FAULT_RE = re.compile(r"iommu.*(fault|error)|page fault|unhandled", re.I)
HOLD_A = HOLD_B = 15.0
# Test 2 (section 10.23.2): composition routing x AFBD format, on the 4:2:2 ring,
# in the T5 stage-B state.  Only these words change; AFBD's own mode bits (mux
# 0x68 bit 8, 0x10 bit 4) stay in capture mode -- set, they would point AFBD at
# its empty queue slots (address 0).
COMP30, COMP40, AFBD4C, AFBD14, AFBD6C, AFBD68 = 0x05000030, 0x05000040, 0x0560004C, 0x05600014, 0x0560006C, 0x05600068
ROUTING = {  # comp 0x030 bits (22, 11, 10), comp 0x040 bits (7, 3) -- the firmware router 0x8b1a43f0
    "capture": ({22: 1, 11: 0, 10: 0}, {7: 1, 3: 0}),
    "decoder": ({22: 0, 11: 1, 10: 1}, {7: 0, 3: 1}),
}
FORMAT = {"422": (0x02, 0x02D00500), "420": (0x00, 0x01680500)}  # AFBD 0x10[15:8], 0x4c
CELLS = [("capture", "422"), ("capture", "420"), ("decoder", "422"), ("decoder", "420"), ("capture", "422")]
HOLD_CELL = 15.0


def setbits(v, bits):
    for b, on in bits.items():
        v = (v | (1 << b)) if on else (v & ~(1 << b))
    return v
HOLD_B_MIN, HOLD_B_MAX = 15.0, 120.0  # --hold-b: stage B long enough to sweep (10.21)


def effective_hold_b(arg):
    return HOLD_B if arg is None else arg


def hold_b_seconds(text):
    v = float(text)
    if not HOLD_B_MIN <= v <= HOLD_B_MAX:
        raise ValueError(f"--hold-b must be {HOLD_B_MIN:g}..{HOLD_B_MAX:g} s")
    return v


def kseg(va):
    return va - 0x80000000 + 0x40000000


class DevMem:
    """Word access through /dev/mem; writes only to allowlisted values."""

    def __init__(self, writable):
        self.fd = os.open("/dev/mem", (os.O_RDWR if writable else os.O_RDONLY) | os.O_SYNC)
        self.writable = writable

    def _map(self, pa, prot):
        base = pa & ~0xFFF
        return mmap.mmap(self.fd, 4096, mmap.MAP_SHARED, prot, offset=base), (pa - base) // 4

    def read(self, pa):
        if 0x07091000 <= pa <= 0x07091FFF or 0x06940000 <= pa <= 0x0694FFFF or pa == 0x0709011C:
            raise ValueError(f"forbidden read {pa:#x}")
        m, i = self._map(pa, mmap.PROT_READ)
        v = memoryview(m).cast("I")
        x = v[i]
        v.release()
        m.close()
        return x

    def write(self, pa, val):
        m, i = self._map(pa, mmap.PROT_READ | mmap.PROT_WRITE)
        v = memoryview(m).cast("I")
        v[i] = val
        v.release()
        m.close()


class Board:
    def __init__(self, mem, shell, faults, kms_video, reserved, with_nr=False, matrix=False):
        self.mem, self._shell, self._faults = mem, shell, faults
        self.with_nr, self.matrix = with_nr, matrix
        self.cell_base = None
        self._kms_video, self._reserved = kms_video, reserved
        self.allowed = {SEL: {SEL_CONSOLE, SEL_VIDEO}}
        self.events = []

    def log(self, ev, **kw):
        kw.update(t=round(time.monotonic(), 3), ev=ev)
        self.events.append(kw)
        print(json.dumps(kw), flush=True)

    def write(self, pa, val):
        if val not in self.allowed.get(pa, ()):
            raise ValueError(f"write {pa:#x}={val:#x} not in the allowlist")
        self.mem.write(pa, val)
        back = self.mem.read(pa)
        self.log("write", reg=f"{pa:#010x}", val=f"{val:08x}", readback=f"{back:08x}")

    def shell(self, cmd):
        assert cmd in SHELL_OK and (self.with_nr or cmd.endswith(" 4")), cmd
        out = self._shell(cmd)
        self.log("shell", cmd=cmd, reply=out[-200:])

    def snap(self, label):
        r = self.mem.read
        s = {
            "sel": r(SEL), "gain": r(GAIN), "afbd10": r(AFBD10), "fetch": [r(a) for a in FETCH],
            "pair": r(PAIR), "bypass": r(BYPASS), "iommu_sta": r(IOMMU_STA), "tcon": [r(a) for a in TCON],
            "mirror": r(MIRROR), "blue": [r(a) for a in BLUE], "nr_en": [r(a) for a in NR_EN],
            "faults": self._faults(),
        }
        self.log("snap", label=label, **{k: (f"{v:08x}" if isinstance(v, int) and k != "faults" else
                                             [f"{x:08x}" for x in v] if isinstance(v, list) else v)
                                          for k, v in s.items()})
        return s

    def preconditions(self):
        r = self.mem.read
        obj = r(kseg(MEMAGENT_PTR))
        locked = (r(kseg(obj) + 0xB4) >> 8) & 0xFF
        checks = {
            "pool identity map in group 0": "0x000000004bf41000 0x000000004d940fff direct" in self._reserved(),
            "HDMI locked (MemoryAgent +0xb5 == 1)": locked == 1,
            "IOMMU bypass 0x58 (master 2 translates)": r(BYPASS) == 0x58,
            "selector on the console": r(SEL) == SEL_CONSOLE,
            "KMS video plane off": not self._kms_video(),
            "AFBD source 0 in capture config, off (0x10 == 03000200)": r(AFBD10) == 0x03000200,
            "TCON 720p": [r(a) for a in TCON[1:]] == [0x02F80550, 0x02D00500],
            "IOMMU interrupt status 0": r(IOMMU_STA) == 0,
            "no kernel fault lines": self._faults() == 0,
        }
        if self.with_nr:
            checks["NR history addresses in the pool, as stock"] = all(r(a) == v for a, v in NR_ADDR.items())
            checks["NR history DMA off"] = not any(r(a) >> 31 for a in NR_EN)
        for k, v in checks.items():
            self.log("check", what=k, ok=bool(v))
        return all(checks.values())

    def guard(self, base):
        r = self.mem.read
        bad = []
        if r(IOMMU_STA):
            bad.append(f"IOMMU status {r(IOMMU_STA):08x}")
        if self._faults() != base["faults"]:
            bad.append("new kernel fault line")
        if [r(a) for a in TCON[1:]] != base["tcon"][1:]:
            bad.append("TCON 720p words changed")
        if r(MIRROR) != base["mirror"]:
            bad.append("panel mirror word changed")
        return bad

    def hold(self, secs, base, label):
        end = time.monotonic() + secs
        seen = set()
        while time.monotonic() < end:
            bad = self.guard(base)
            if bad:
                self.log("abort", stage=label, why=bad)
                return False
            seen.add(tuple(self.mem.read(a) for a in FETCH))
            time.sleep(0.25)
        self.log("held", stage=label, secs=secs, fetch_values=len(seen))
        return True

    def cell_words(self, routing, fmt):
        """The four words for one cell, derived from the T5 baseline read at the start."""
        b = self.cell_base
        r30, r40 = ROUTING[routing]
        fb, rows = FORMAT[fmt]
        return {COMP30: setbits(b[COMP30], r30), COMP40: setbits(b[COMP40], r40),
                AFBD10: (b[AFBD10] & ~0xFF00) | fb << 8, AFBD4C: rows}

    def apply_cell(self, routing, fmt):
        for pa, val in self.cell_words(routing, fmt).items():
            if self.mem.read(pa) != val:
                self.write(pa, val)
        self.write(AFBD6C, 1)  # the two-plane publish latch, as the firmware programmer ends
        self.write(AFBD14, 1)

    def restore_cells(self):
        """Put the four cell words back to the T5 baseline (no-op if never changed)."""
        if self.cell_base is None:
            return
        changed = False
        for pa in (COMP30, COMP40, AFBD10, AFBD4C):
            if self.mem.read(pa) != self.cell_base[pa]:
                self.write(pa, self.cell_base[pa])
                changed = True
        if changed:
            self.write(AFBD6C, 1)
            self.write(AFBD14, 1)

    def revert(self, gain_idle):
        """Cell words back, gain back, console selected, then source 0 off. Safe to repeat."""
        self.allowed[GAIN] = {gain_idle, GAIN_COLOUR}
        try:
            self.restore_cells()
        except Exception as e:  # never let a failed restore skip the selector / source revert
            self.log("restore_cells_failed", why=str(e))
        try:
            if self.mem.read(GAIN) != gain_idle:
                self.write(GAIN, gain_idle)
        finally:
            try:
                if self.mem.read(SEL) != SEL_CONSOLE:
                    self.write(SEL, SEL_CONSOLE)
            finally:
                try:
                    self.shell("memory_agent dis 4")
                finally:
                    if self.with_nr:
                        try:
                            self.shell("memory_agent dis 6")
                        finally:
                            self.shell("memory_agent dis 5")

    def run(self):
        if not self.preconditions():
            self.log("refused", why="preconditions")
            return 2
        gain_idle = self.mem.read(GAIN)
        self.allowed[GAIN] = {gain_idle, GAIN_COLOUR}
        self.log("gain_idle", val=f"{gain_idle:08x}")
        base = self.snap("pre")
        ok = False
        try:
            if self.with_nr:
                self.shell("memory_agent en 5")
                self.shell("memory_agent en 6")
                time.sleep(0.5)
                s = self.snap("nr-on")
                if not all(v >> 31 for v in s["nr_en"]) or self.guard(base):
                    self.log("abort", stage="nr-on", why="NR history enables not set or a guard tripped")
                    return 3
            self.shell("memory_agent en 4")
            seen = set()
            for _ in range(12):
                seen.add(tuple(self.mem.read(a) for a in FETCH))
                time.sleep(0.25)
            s = self.snap("en4")
            if (s["afbd10"] & 3) != 3 or len(seen) < 2 or self.guard(base):
                self.log("abort", stage="en4", why="source 0 not fetching or a guard tripped",
                         fetch_values=len(seen))
                return 3
            self.write(SEL, SEL_VIDEO)
            self.snap("A-grey")
            if not self.hold(HOLD_A, base, "A-grey"):
                return 4
            self.snap("A-grey-end")
            self.write(GAIN, GAIN_COLOUR)
            self.snap("B-colour")
            if not self.hold(HOLD_B, base, "B-colour"):
                return 4
            self.snap("B-colour-end")
            if self.matrix:
                # the T5 baseline (capture routing, format 2) is what the cells are derived from
                self.cell_base = {pa: self.mem.read(pa) for pa in (COMP30, COMP40, AFBD10, AFBD4C)}
                self.log("cell_base", **{f"{pa:#010x}": f"{v:08x}" for pa, v in self.cell_base.items()})
                for pa in (COMP30, COMP40, AFBD10, AFBD4C):
                    self.allowed[pa] = {self.cell_words(r, f)[pa] for r, f in CELLS} | {self.cell_base[pa]}
                self.allowed[AFBD6C] = self.allowed[AFBD14] = {1}
                for i, (routing, fmt) in enumerate(CELLS):
                    self.apply_cell(routing, fmt)
                    label = f"cell{i}-{routing}-{fmt}"
                    self.snap(label)
                    if not self.hold(HOLD_CELL, base, label):
                        return 4
            ok = True
            return 0
        finally:
            self.revert(gain_idle)
            self.snap("reverted")
            self.log("done", ok=ok)


def real_board(writable, with_nr=False, matrix=False):
    mem = DevMem(writable)

    def shell(cmd):
        p = subprocess.run(SHELL + ["--cmd", cmd, "--wait", "2"], capture_output=True, text=True, timeout=20)
        return p.stdout + p.stderr

    def faults():
        out = subprocess.run(["dmesg"], capture_output=True, text=True).stdout
        return sum(1 for l in out.splitlines() if FAULT_RE.search(l) and "Default domain" not in l)

    def kms_video():
        return "video on" in open("/sys/kernel/debug/dri/0/h713_geometry").read()

    def reserved():
        return open("/sys/kernel/iommu_groups/0/reserved_regions").read()

    return Board(mem, shell, faults, kms_video, reserved, with_nr, matrix)


# ---- offline self-test -------------------------------------------------------

class FakeMem:
    def __init__(self):
        obj = 0x8B600000
        self.r = {SEL: SEL_CONSOLE, GAIN: 0x04000000, AFBD10: 0x03000200, FETCH[0]: 0x47, FETCH[1]: 0x3B,
                  PAIR: 0x4C3EF000, BYPASS: 0x58, IOMMU_STA: 0, TCON[0]: 0x00D00404, TCON[1]: 0x02F80550,
                  TCON[2]: 0x02D00500, MIRROR: 0x80000000, BLUE[0]: 0, BLUE[1]: 0x38, BLUE[2]: 0xF0000000,
                  kseg(MEMAGENT_PTR): obj, kseg(obj) + 0xB4: 0x8B000100,
                  NR_EN[0]: 0x60020168, NR_EN[1]: 0x600202D0, NR_EN[2]: 0x60020168, NR_EN[3]: 0x600202D0}
        self.r.update(NR_ADDR)
        self.r.update({COMP30: 0x00400000, COMP40: 0x02090280, AFBD4C: 0x02D00500, AFBD14: 0, AFBD6C: 0, AFBD68: 0x22})
        self.nr_works = True
        self.fault_time = None
        self.writes, self.tick, self.fetching, self.on_write = [], 0, True, None

    def read(self, pa):
        if 0x07091000 <= pa <= 0x07091FFF or 0x06940000 <= pa <= 0x0694FFFF or pa == 0x0709011C:
            raise ValueError(f"forbidden read {pa:#x}")
        if pa == IOMMU_STA and self.fault_time is not None and time.monotonic() >= self.fault_time:
            self.r[IOMMU_STA] = 4
        if pa in FETCH and self.r[AFBD10] & 3 and self.fetching:
            self.tick += 1
            return 0x40 + self.tick % 0x30
        return self.r[pa]

    def write(self, pa, val):
        self.writes.append((pa, val))
        self.r[pa] = val
        if self.on_write:
            self.on_write(pa, val, self)


def fake(mem=None, with_nr=False, matrix=False):
    mem = mem or FakeMem()
    cmds = []

    def shell(cmd):
        cmds.append(cmd)
        on, agent = cmd.split()[1] == "en", cmd[-1]
        if agent == "4":
            mem.r[AFBD10] = (mem.r[AFBD10] & ~3) | (3 if on else 0)
        elif mem.nr_works:
            for a in (NR_EN[:2] if agent == "5" else NR_EN[2:]):
                mem.r[a] = (mem.r[a] & 0x7FFFFFFF) | (on << 31)
        return "VS:/$ "

    def faults():
        return mem.r.get("faults", 0)

    b = Board(mem, shell, faults, lambda: False,
              lambda: "0x000000004bf41000 0x000000004d940fff direct\n", with_nr, matrix)
    return b, mem, cmds


def self_test():
    global HOLD_A, HOLD_B, HOLD_CELL
    HOLD_A = HOLD_B = 0.6
    HOLD_CELL = 0.3
    out = open(os.devnull, "w")
    real_stdout, sys.stdout = sys.stdout, out
    fails = []
    try:
        # 1. happy path: exact write order, restored at the end
        b, m, cmds = fake()
        rc = b.run()
        want = [(SEL, SEL_VIDEO), (GAIN, GAIN_COLOUR), (GAIN, 0x04000000), (SEL, SEL_CONSOLE)]
        if rc != 0 or m.writes != want or cmds != ["memory_agent en 4", "memory_agent dis 4"]:
            fails.append(f"happy path rc={rc} writes={m.writes} cmds={cmds}")
        # 2. a precondition fails -> no write, no shell command
        m = FakeMem(); m.r[SEL] = SEL_VIDEO
        b, m, cmds = fake(m)
        if b.run() != 2 or m.writes or cmds:
            fails.append("refused precondition still wrote or ran the shell")
        for k, v in ((BYPASS, 0x5C), (AFBD10, 0x03000010), (IOMMU_STA, 1), (TCON[1], 0x04380780)):
            m = FakeMem(); m.r[k] = v
            b, m, cmds = fake(m)
            if b.run() != 2 or m.writes or cmds:
                fails.append(f"precondition {k:#x}={v:#x} not refused")
        b, m, cmds = fake()
        b._reserved = lambda: ""
        if b.run() != 2 or m.writes or cmds:
            fails.append("missing identity map not refused")
        # 3. source 0 does not fetch -> abort before the selector, still dis 4
        m = FakeMem(); m.fetching = False
        b, m, cmds = fake(m)
        if b.run() != 3 or any(pa == SEL and v == SEL_VIDEO for pa, v in m.writes) or cmds[-1] != "memory_agent dis 4":
            fails.append(f"no-fetch abort wrong: {m.writes} {cmds}")
        # 4. IOMMU status bit during stage A -> abort, full revert
        m = FakeMem()
        m.on_write = lambda pa, v, mm: mm.r.__setitem__(IOMMU_STA, 4) if (pa, v) == (SEL, SEL_VIDEO) else None
        b, m, cmds = fake(m)
        if b.run() != 4 or m.r[SEL] != SEL_CONSOLE or m.r[GAIN] != 0x04000000 or cmds[-1] != "memory_agent dis 4":
            fails.append("IOMMU abort did not revert")
        if (GAIN, GAIN_COLOUR) in m.writes:
            fails.append("stage B ran after an abort")
        # 5. a kernel fault line appearing -> abort
        m = FakeMem()
        m.on_write = lambda pa, v, mm: mm.r.__setitem__("faults", 1) if (pa, v) == (GAIN, GAIN_COLOUR) else None
        b, m, cmds = fake(m)
        if b.run() != 4 or m.r[SEL] != SEL_CONSOLE or m.r[GAIN] != 0x04000000:
            fails.append("fault-line abort did not revert")
        # 6. an exception mid-run (shell dies) still reverts
        m = FakeMem()
        m.on_write = lambda pa, v, mm: (_ for _ in ()).throw(OSError("boom")) if (pa, v) == (GAIN, GAIN_COLOUR) else None
        b, m, cmds = fake(m)
        try:
            b.run()
            fails.append("exception swallowed")
        except OSError:
            pass
        if m.r[SEL] != SEL_CONSOLE or m.r[GAIN] != 0x04000000 or cmds[-1] != "memory_agent dis 4":
            fails.append(f"exception path did not revert: sel={m.r[SEL]:#x} gain={m.r[GAIN]:#x}")
        # 7. allowlist: anything else refused, forbidden reads refused
        b, m, cmds = fake()
        for pa, v in ((SEL, 0x19000000), (GAIN, 0), (0x05600010, 0x03000203)):
            try:
                b.write(pa, v)
                fails.append(f"allowlist let {pa:#x}={v:#x} through")
            except ValueError:
                pass
        for pa in (0x07091000, 0x07091FFC, 0x06940928, 0x0709011C):
            try:
                m.read(pa)
                fails.append(f"forbidden read {pa:#x} allowed")
            except ValueError:
                pass
        # 8. revert is idempotent on a clean board: no register writes
        b, m, cmds = fake()
        b.revert(0x04000000)
        if m.writes or cmds != ["memory_agent dis 4"]:
            fails.append("revert on a clean board wrote registers")
        # 9. T6 happy path: NR on before agent 4, off last; registers as T5
        b, m, cmds = fake(with_nr=True)
        rc = b.run()
        want_cmds = ["memory_agent en 5", "memory_agent en 6", "memory_agent en 4",
                     "memory_agent dis 4", "memory_agent dis 6", "memory_agent dis 5"]
        if rc != 0 or cmds != want_cmds or m.writes != want or any(m.r[a] >> 31 for a in NR_EN):
            fails.append(f"T6 happy path rc={rc} cmds={cmds}")
        # 10. T6: NR enables do not take -> abort before agent 4 and the selector, NR off again
        m = FakeMem(); m.nr_works = False
        b, m, cmds = fake(m, with_nr=True)
        if b.run() != 3 or "memory_agent en 4" in cmds or m.writes or cmds[-2:] != ["memory_agent dis 6", "memory_agent dis 5"]:
            fails.append(f"T6 NR-enable abort wrong: {cmds} {m.writes}")
        # 11. T6 preconditions: NR address moved, or NR already on -> refused, nothing run
        for k, v in ((0x05000180, 0x04000000), (NR_EN[2], 0xE0020168)):
            m = FakeMem(); m.r[k] = v
            b, m, cmds = fake(m, with_nr=True)
            if b.run() != 2 or m.writes or cmds:
                fails.append(f"T6 precondition {k:#x}={v:#x} not refused")
        # 12. T5 mode never sends the NR commands
        b, m, cmds = fake()
        try:
            b.shell("memory_agent en 5")
            fails.append("T5 mode allowed en 5")
        except AssertionError:
            pass
        # 13. --hold-b wiring and bounds
        if effective_hold_b(None) != HOLD_B or effective_hold_b(60.0) != 60.0:
            fails.append("--hold-b not applied")
        for v, ok in (("15", True), ("60", True), ("120", True), ("121", False), ("5", False), ("x", False)):
            try:
                hold_b_seconds(v)
                good = True
            except ValueError:
                good = False
            if good != ok:
                fails.append(f"--hold-b {v} accepted={good}")
        # 14. a long stage-B hold still guards: an IOMMU bit deep into the hold reverts everything
        saved = HOLD_B
        try:
            HOLD_B = 3.0
            m = FakeMem()  # an IOMMU bit 1.5 s into the 3 s stage B
            m.on_write = lambda pa, v, mm: setattr(mm, "fault_time", time.monotonic() + 1.5) \
                if (pa, v) == (GAIN, GAIN_COLOUR) else None
            b, m, cmds = fake(m, with_nr=True)
            rc = b.run()
            if rc != 4 or m.r[SEL] != SEL_CONSOLE or m.r[GAIN] != 0x04000000 or \
                    cmds[-3:] != ["memory_agent dis 4", "memory_agent dis 6", "memory_agent dis 5"]:
                fails.append(f"long-hold abort rc={rc} cmds={cmds[-3:]}")
            if (GAIN, GAIN_COLOUR) not in m.writes:
                fails.append("long-hold fault fired before stage B; test is not exercising the long hold")
            ev = [(e["ev"], e.get("stage")) for e in b.events]
            if ("abort", "B-colour") not in ev or ("held", "B-colour") in ev:
                fails.append("long hold was not cut short by the fault")
            # and a clean long hold runs its full length, then reverts
            m = FakeMem()
            b, m, cmds = fake(m)
            t0 = time.monotonic()
            rc = b.run()
            if rc != 0 or time.monotonic() - t0 < HOLD_A + HOLD_B or m.r[SEL] != SEL_CONSOLE:
                fails.append("clean long hold did not hold or did not revert")
        finally:
            HOLD_B = saved
        # 15. Test 2 matrix: each cell writes exactly its words, in order; everything returns to base
        b, m, cmds = fake(matrix=True)
        rc = b.run()
        base = {COMP30: 0x00400000, COMP40: 0x02090280, AFBD4C: 0x02D00500}
        cell_writes = [(pa, v) for pa, v in m.writes if pa in (COMP30, COMP40, AFBD10, AFBD4C)]
        want_cells = [
            (AFBD10, 0x03000003), (AFBD4C, 0x01680500),                                  # capture/420
            (COMP30, 0x00000C00), (COMP40, 0x02090208), (AFBD10, 0x03000203), (AFBD4C, 0x02D00500),  # decoder/422
            (AFBD10, 0x03000003), (AFBD4C, 0x01680500),                                  # decoder/420
            (COMP30, 0x00400000), (COMP40, 0x02090280), (AFBD10, 0x03000203), (AFBD4C, 0x02D00500),  # capture/422
        ]
        if rc != 0 or cell_writes != want_cells:
            fails.append(f"matrix writes rc={rc}: {[(hex(a), hex(v)) for a, v in cell_writes]}")
        if any(pa == AFBD68 for pa, _ in m.writes):
            fails.append("matrix wrote AFBD mux 0x68")
        if any(m.r[pa] != v for pa, v in base.items()) or m.r[SEL] != SEL_CONSOLE or m.r[AFBD10] & 3:
            fails.append("matrix did not end at the T5 baseline with source 0 off")
        if sum(1 for pa, v in m.writes if pa == AFBD14) != len(CELLS):
            fails.append("each cell must publish (0x14) exactly once")
        ev = [e.get("label") for e in b.events if e["ev"] == "snap"]
        if [l for l in ev if l and l.startswith("cell")] != [f"cell{i}-{r}-{f}" for i, (r, f) in enumerate(CELLS)]:
            fails.append(f"cell snapshots {ev}")
        # 16. an IOMMU fault in the decoder cell aborts, restores the cell words, then the usual revert
        m = FakeMem()
        m.on_write = lambda pa, v, mm: mm.r.__setitem__(IOMMU_STA, 4) if (pa, v) == (COMP30, 0x00000C00) else None
        b, m, cmds = fake(m, matrix=True)
        rc = b.run()
        if rc != 4 or any(m.r[pa] != v for pa, v in base.items()) or m.r[SEL] != SEL_CONSOLE \
                or cmds[-1] != "memory_agent dis 4" or (AFBD10, 0x03000003) in [(a, v) for a, v in m.writes][-3:]:
            fails.append(f"matrix abort did not restore: rc={rc} {[(hex(a), hex(m.r[a])) for a in base]}")
        # 17. the allowlist refuses the mux and arbitrary routing values; T5 mode never applies cells
        b, m, cmds = fake(matrix=True)
        b.run()
        for pa, v in ((AFBD68, 0x122), (COMP30, 0xFFFFFFFF), (AFBD10, 0x03000613)):
            try:
                b.write(pa, v)
                fails.append(f"allowlist let {pa:#x}={v:#x} through")
            except ValueError:
                pass
        b, m, cmds = fake()
        b.run()
        if any(pa in (COMP30, COMP40, AFBD4C) for pa, _ in m.writes):
            fails.append("T5 mode wrote cell words")
    finally:
        sys.stdout = real_stdout
    for f in fails:
        print("FAIL:", f)
    print("self-test", "FAILED" if fails else "passed (17 groups)")
    return 1 if fails else 0


def main():
    global HOLD_B
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", nargs="?", choices=("check", "run", "revert"))
    ap.add_argument("--confirm-t5", action="store_true")
    ap.add_argument("--with-nr", action="store_true", help="T6: NR history DMA (agents 5/6) on too")
    ap.add_argument("--matrix", action="store_true", help="Test 2: the routing x format cells after stage B")
    ap.add_argument("--hold-b", type=hold_b_seconds, default=None,
                    help=f"stage B hold in seconds ({HOLD_B_MIN:g}..{HOLD_B_MAX:g}; default {HOLD_B:g})")
    ap.add_argument("--gain-idle", default="04000000")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if a.mode == "check":
        return 0 if real_board(False, a.with_nr).preconditions() else 2
    if a.mode == "revert":
        real_board(True, a.with_nr).revert(int(a.gain_idle, 16))
        return 0
    if a.mode == "run":
        if not a.confirm_t5:
            raise SystemExit("run needs --confirm-t5")
        HOLD_B = effective_hold_b(a.hold_b)
        return real_board(True, a.with_nr, a.matrix).run()
    ap.error("mode or --self-test required")


if __name__ == "__main__":
    raise SystemExit(main())
