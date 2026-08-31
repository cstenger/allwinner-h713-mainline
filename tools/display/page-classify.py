#!/usr/bin/env python3
"""Classify MMIO windows from page-sample.sh captures, and diff two stacks.

Runs on the host, not the board, so the board script needs nothing but sh and a
reader binary.

    page-classify.py CAPDIR                 classify one stack
    page-classify.py CAPDIR-A CAPDIR-B      classify both and diff them

Each CAPDIR holds the four files page-sample.sh writes: state1-a, state1-b,
state2-a, state2-b.

WHY CLASSIFY BEFORE DIFFING

The composition page mixes static configuration with free-running telemetry.
Diffing one stock sample against one Linux sample reports both as differences,
and the telemetry drowns the configuration -- the 08-29 block sweep's 49
differing registers were readable only because the swept windows happened to be
mostly static. This page is not.

Two samples per state separate them:

  free-running   changed within a state, so its value carries no information
                 across stacks and any cross-stack difference is meaningless
  state-driven   stable within each state but different between them: this is
                 what the state actually changes
  static         stable everywhere and identical in both states

A register that free-runs in EITHER state is free-running, full stop. AFBD's
buffer ring is the case that matters: still at idle, cycling during playback.
Treating it as state-driven because the idle pair happened to match would put
four addresses into the interesting set that belong in the noise.

WHAT THE CROSS-STACK DIFF REPORTS

Only registers that are trustworthy on BOTH stacks -- static or state-driven on
each -- and whose state-2 values differ. That is the set that can actually
explain why one stack shows video and the other does not. Registers free-running
on either side are listed separately and counted, never silently dropped: a
register that free-runs on stock and is frozen on ours is itself a finding, and
one that free-runs on both is exactly what the earlier "AFBD counters are
frozen" retraction got wrong by reading liveness into a single sample.
"""

import sys
from pathlib import Path

FILES = ("state1-a", "state1-b", "state2-a", "state2-b")

FREE_RUNNING = "free-running"
STATE_DRIVEN = "state-driven"
STATIC = "static"


def load(path):
    """Parse a reader capture into {address: value}, both as ints.

    The format is fixed by hidtvreg-read.c/mmio-read.c and is deliberately
    identical between them: lowercase 8-hex address, space, '0x', uppercase
    8-hex value. Anything else is rejected rather than skipped -- a silently
    ignored malformed line would shrink the compared set without saying so.
    """
    regs = {}
    for lineno, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2 or not parts[1].startswith("0x"):
            raise ValueError(f"{path}:{lineno}: unparseable line {raw!r}")
        try:
            addr = int(parts[0], 16)
            value = int(parts[1], 16)
        except ValueError:
            raise ValueError(f"{path}:{lineno}: bad hex in {raw!r}") from None
        if addr in regs:
            raise ValueError(f"{path}:{lineno}: duplicate address {addr:08x}")
        regs[addr] = value
    if not regs:
        raise ValueError(f"{path}: no registers")
    return regs


def load_capture(capdir):
    """Load all four samples, requiring identical address coverage."""
    capdir = Path(capdir)
    missing = [f for f in FILES if not (capdir / f).exists()]
    if missing:
        raise SystemExit(
            f"{capdir}: missing {', '.join(missing)} -- "
            "run page-sample.sh and copy all four files off the board"
        )
    samples = {f: load(capdir / f) for f in FILES}

    reference = set(samples[FILES[0]])
    for name in FILES[1:]:
        if set(samples[name]) != reference:
            raise SystemExit(
                f"{capdir}: {name} covers a different address set than "
                f"{FILES[0]} -- the samples were taken with different "
                "address/count arguments and cannot be compared"
            )
    return samples


def classify(samples):
    """Return {address: (kind, state1_value, state2_value)}.

    state1/state2 values are only meaningful for the stable kinds; for a
    free-running register the reported value is the first sample of that state,
    kept so the output shows something rather than a blank.
    """
    s1a, s1b = samples["state1-a"], samples["state1-b"]
    s2a, s2b = samples["state2-a"], samples["state2-b"]

    out = {}
    for addr in sorted(s1a):
        v1a, v1b, v2a, v2b = s1a[addr], s1b[addr], s2a[addr], s2b[addr]
        if v1a != v1b or v2a != v2b:
            kind = FREE_RUNNING
        elif v1a != v2a:
            kind = STATE_DRIVEN
        else:
            kind = STATIC
        out[addr] = (kind, v1a, v2a)
    return out


def counts(classified):
    tally = {FREE_RUNNING: 0, STATE_DRIVEN: 0, STATIC: 0}
    for kind, _, _ in classified.values():
        tally[kind] += 1
    return tally


def report_one(label, classified):
    tally = counts(classified)
    total = len(classified)
    print(f"== {label}: {total} registers")
    for kind in (STATIC, STATE_DRIVEN, FREE_RUNNING):
        print(f"   {kind:<14} {tally[kind]:>5}")

    driven = [(a, v1, v2) for a, (k, v1, v2) in classified.items()
              if k == STATE_DRIVEN]
    if driven:
        print(f"\n   state-driven registers ({len(driven)}):")
        for addr, v1, v2 in driven:
            print(f"     {addr:08x}  0x{v1:08X} -> 0x{v2:08X}")
    else:
        print("\n   no state-driven registers -- the state change moved "
              "nothing in any captured window")

    free = [a for a, (k, _, _) in classified.items() if k == FREE_RUNNING]
    if free:
        print(f"\n   free-running ({len(free)}): "
              + " ".join(f"{a:08x}" for a in free))
    print()


def report_diff(class_a, label_a, class_b, label_b):
    common = sorted(set(class_a) & set(class_b))
    only_a = set(class_a) - set(class_b)
    only_b = set(class_b) - set(class_a)
    if only_a or only_b:
        print(f"!! address sets differ: {len(only_a)} only in {label_a}, "
              f"{len(only_b)} only in {label_b}; comparing the "
              f"{len(common)} in common\n")

    comparable = []
    unstable = []
    for addr in common:
        kind_a, _, v2a = class_a[addr]
        kind_b, _, v2b = class_b[addr]
        if kind_a == FREE_RUNNING or kind_b == FREE_RUNNING:
            unstable.append((addr, kind_a, kind_b))
            continue
        if v2a != v2b:
            comparable.append((addr, v2a, kind_a, v2b, kind_b))

    print(f"== cross-stack diff, state 2 ({label_a} vs {label_b})")
    print(f"   {len(common)} common, {len(unstable)} excluded as free-running "
          f"on at least one stack, {len(comparable)} differing\n")

    if comparable:
        print(f"   {'address':<10} {label_a:<22} {label_b}")
        for addr, va, ka, vb, kb in comparable:
            print(f"   {addr:08x}   0x{va:08X} ({ka:<12}) 0x{vb:08X} ({kb})")
    else:
        print("   no trustworthy register differs between the two stacks.")
        print("   If one stack shows video and the other does not, the")
        print("   difference is not in any window captured here.")

    # Never silently dropped: a register free-running on one stack and frozen
    # on the other is a finding in its own right, and reading liveness out of a
    # single sample is exactly the error the "AFBD counters are frozen" claim
    # had to retract.
    asymmetric = [(a, ka, kb) for a, ka, kb in unstable if ka != kb]
    if asymmetric:
        print(f"\n   free-running on one stack only ({len(asymmetric)}) -- "
              "worth a look, not noise:")
        for addr, ka, kb in asymmetric:
            print(f"     {addr:08x}  {label_a}: {ka:<12} {label_b}: {kb}")


def main(argv):
    # A corrupt or truncated capture is an expected failure -- a board run can
    # be cut short by the hard lock this page is being used to study. Report it
    # as a message with the offending file and line, not a traceback.
    try:
        if len(argv) == 2:
            capdir = argv[1]
            report_one(capdir, classify(load_capture(capdir)))
            return 0
        if len(argv) == 3:
            a, b = argv[1], argv[2]
            class_a = classify(load_capture(a))
            class_b = classify(load_capture(b))
            report_one(a, class_a)
            report_one(b, class_b)
            report_diff(class_a, a, class_b, b)
            return 0
    except ValueError as exc:
        print(f"page-classify: {exc}", file=sys.stderr)
        return 1
    print(__doc__.strip().splitlines()[0], file=sys.stderr)
    print("usage: page-classify.py CAPDIR [CAPDIR-B]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
