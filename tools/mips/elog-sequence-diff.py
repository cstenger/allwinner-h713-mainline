#!/usr/bin/env python3
"""Compare the firmware's HDMI-source sequence in two elog dumps.

Stage 1 of docs/hdmi-panel-source-design-2026-10-23.md asks one question of
our firmware log: which step of stock Android's HDMI picture sequence does
our boot never reach?  The reference is the 10-07 stock capture
(docs/hdmi-evidence/2026-10-07-android-audio/locked-elog/elog.bin).

    elog-sequence-diff.py REFERENCE OURS [OURS2 ...]
    elog-sequence-diff.py --self-test

Several dumps of one side are merged (later wins where the earlier had a
cache hole), exactly as elog-parse.py --merge does.  The output is

  1. the milestone table: the first tick of each step of section 1.7 on
     both sides, or MISSING;
  2. the first reference milestone that OURS lacks;
  3. the reference-only record shapes (numbers folded to '#'), which shows
     what a missing milestone was surrounded by.

Absence is weak evidence: a record can sit in the MIPS data cache past the
read, or be overwritten when the ring wraps.  So a milestone counts as
missing only when it is absent from every merged dump of that side, and the
report says how many records and which tick span it searched.
"""
import argparse
import importlib.util
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("elog_parse", HERE / "elog-parse.py")
elog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(elog)

TAGS = re.compile(r"^(hal|app|mem_agn|bs|win_mgr|wce_\w*|hdmirx|hdmi_driver|frl|crtc)$")

# Section 1.7, in stock order.  (name, tag regex, message regex)
MILESTONES = [
    ("SetSource(3)",            r"^hal$",         r"hal_source_id: 3\b"),
    ("AppTopSetSource",         r"^app$",         r"^AppTopSetSource$"),
    ("receiver BlueScreen on",  r"^hdmirx$",      r"Send BlueScreen, bON=1"),
    ("port state 4 -> 5",       r"^hdmirx$",      r"SwitchState from 4 to 5"),
    ("AVI infoframe",           r"^hdmirx$",      r"AVI Info Frame"),
    ("signal valid",            r"^hdmirx$",      r"Set Valid Signal"),
    ("CallbackOfSignalChange",  r"^app$",         r"^CallbackOfSignalChange$"),
    ("UpdateWce",               r"^win_mgr$",     r"^UpdateWce : ENTER"),
    ("capture window",          r"^wce_cap$",     r"^CalcWindow : ENTER"),
    ("capture WriteReg",        r"^wce_cap$",     r"^WriteReg : ENTER"),
    ("NR WriteReg",             r"^wce_nr$",      r"^WriteReg : ENTER"),
    ("update_onoff",            r"^mem_agn$",     r"^update_onoff$"),
    ("receiver unmuted",        r"^hdmirx$",      r"set AV mute:0 0"),
    ("NotifySignalChange",      r"^app$",         r"^NotifySignalChange$"),
    ("ARM Wce_SetWindow",       r"^hal$",         r"THal_Vp_Wce_SetWindow\(\) ENTER"),
    ("ARM DisableBlackScreen",  r"^hal$",         r"THal_Vp_DisableBlackScreen\(\) ENTER"),
]
# Not milestones: on stock's HDMI selection CAppTop never re-entered its
# EnterWaiting*/EnterSignalSteady states (they ran once, for the startup
# source).  They are still printed as context in the shapes list.


def load(paths):
    blobs = [Path(p).read_bytes() for p in paths]
    blob = elog.merge(blobs) if len(blobs) > 1 else blobs[0]
    recs = sorted(elog.records(blob), key=lambda r: (r[3], r[0]))
    return [r for r in recs if TAGS.match(r[2])]


def source3_window(recs):
    """Records from the last source-3 selection on; all of them if none."""
    start = 0
    for i, r in enumerate(recs):
        if r[2] == "hal" and re.search(r"hal_source_id: 3\b", r[5]):
            start = i
    # Include the THal_Vp_SetSource() ENTER line just before it.
    return recs[max(0, start - 1):]


def first_ticks(recs):
    """Ordered match: each milestone is searched after the previous one
    found, so a pre-lock record (update_onoff with no signal) cannot stand
    in for the post-lock one.  A missing milestone does not move the cursor."""
    found, cursor = {}, 0
    for name, tag, msg in MILESTONES:
        t, m = re.compile(tag), re.compile(msg)
        for i in range(cursor, len(recs)):
            if t.search(recs[i][2]) and m.search(recs[i][5]):
                found[name] = recs[i][3]
                cursor = i + 1
                break
    return found


def shape(r):
    return f"{r[2]}: " + re.sub(r"0x[0-9a-fA-F]+|-?\d+", "#", r[5]).strip()


def compare(ref_paths, our_paths, out=sys.stdout):
    ref = source3_window(load(ref_paths))
    ours = source3_window(load(our_paths))
    fr, fo = first_ticks(ref), first_ticks(ours)

    def span(recs):
        ts = [r[3] for r in recs if r[3] >= 0]
        return f"{len(recs)} records, ticks {min(ts, default=-1)}..{max(ts, default=-1)}"

    print(f"reference: {span(ref)}", file=out)
    print(f"ours:      {span(ours)}", file=out)
    print(f"\n{'milestone':26s} {'reference':>10s} {'ours':>10s}", file=out)
    first_missing = None
    for name, _, _ in MILESTONES:
        a, b = fr.get(name), fo.get(name)
        print(f"{name:26s} {('-' if a is None else a):>10} {('MISSING' if b is None else b):>10}", file=out)
        if a is not None and b is None and first_missing is None:
            first_missing = name
    print(f"\nfirst reference milestone missing from ours: {first_missing or 'none'}", file=out)

    ours_shapes = Counter(shape(r) for r in ours)
    ref_only = Counter(shape(r) for r in ref if shape(r) not in ours_shapes)
    print(f"\nreference-only record shapes ({len(ref_only)}):", file=out)
    for s, n in ref_only.most_common(40):
        print(f"  {n:4d}  {s[:150]}", file=out)
    return first_missing, fr, fo


def self_test():
    ev = HERE.parent.parent / "docs/hdmi-evidence/2026-10-07-android-audio"
    locked, idle = ev / "locked-elog/elog.bin", ev / "idle-elog/elog.bin"
    sink = open("/dev/null", "w")
    failures = []
    missing, fr, fo = compare([locked], [locked], sink)
    if missing is not None:
        failures.append(f"stock against itself reports {missing} missing")
    if len(fr) != len(MILESTONES):
        failures.append("stock lacks milestones: " +
                        ", ".join(n for n, _, _ in MILESTONES if n not in fr))
    missing, fr, fo = compare([locked], [idle], sink)
    for name in ("SetSource(3)", "AppTopSetSource", "capture WriteReg"):
        if name in fo:
            failures.append(f"idle (before HDMI was selected) unexpectedly has {name}")
    if missing is None:
        failures.append("stock against idle reports nothing missing")
    for f in failures:
        print("FAIL:", f)
    print("self-test", "FAILED" if failures else "passed",
          f"({len(MILESTONES)} milestones; idle first missing: {missing})")
    return 1 if failures else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("reference", nargs="?")
    ap.add_argument("ours", nargs="*")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if not a.reference or not a.ours:
        ap.error("need REFERENCE and at least one OURS dump")
    compare([a.reference], a.ours)
    return 0


if __name__ == "__main__":
    sys.exit(main())
