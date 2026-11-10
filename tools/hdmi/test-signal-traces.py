#!/usr/bin/env python3
"""Replay recorded firmware port-object captures through the signal state
machine (modules/hdmi-v4l2/h713-signal.h via test-signal-state --trace).

HDMI panel-source design 10.26. Each capture is a few snapshots of HDMI
port 1 (state, active size) seconds apart, read by read-mips-port-cache.py
while a host enabled and disabled its output. A snapshot is held until the
next one and sampled every 20 ms; the ring is taken to move whenever the
port is at state 5 (measured 10-24, 10.25.5). Expected, from the data
itself: one lock per live stretch (LOCKED 1280x720 with SOURCE_CHANGE, or
UNSUPPORTED 640x480 with 480p not offered), 200-220 ms after the first
live sample, and NO_SIGNAL after the stretch ends (via HOLD for LOCKED).

    test-signal-traces.py BINARY

The 09-24 raw captures used the first reader, which swapped width and
height; only the corrected file from that day is replayed.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRACES = [
    'docs/hdmi-evidence/2026-09-24-hdmi1-signal/h713-hdmi-trial-20260924T225853Z/port-cache-corrected.json',
    'docs/hdmi-evidence/2026-09-25-source3-restart/first-miss/port-cache.json',
    'docs/hdmi-evidence/2026-09-25-source3-restart/second-connected/port-cache.json',
    'docs/hdmi-evidence/2026-10-08-linux-direct-capture/signal-evidence/port-cache.json',
    'docs/hdmi-evidence/2026-10-08-linux-stock-graph/signal-evidence/port-cache.json',
]
PERIOD = 20
LOCK, HOLD, GRACE = 200, 100, 1500


def snapshots(path):
    data = json.loads((ROOT / path).read_text())
    samples = data['samples'] if isinstance(data, dict) else data
    for s in samples:
        snap = s.get('snapshot') or (json.loads(s['output']) if s.get('output') else {})
        port = (snap.get('ports') or [{}])[0]
        yield (round(s['seconds'] * 1000), port.get('state', 0) or 0,
               port.get('hactive', 0) or 0, port.get('vactive', 0) or 0)


def grid(snaps, t):
    """The first sample time at or after t, on the 20 ms grid from the first snapshot."""
    t0 = snaps[0][0]
    return t0 + -(-(t - t0) // PERIOD) * PERIOD


def expand(snaps):
    """20 ms samples (dt valid state w h moving) on one fixed grid; each
    sample shows the latest snapshot taken at or before it."""
    lines, t, i, end = [], snaps[0][0], 0, snaps[-1][0] + 3000
    while t + PERIOD <= end:
        t += PERIOD
        while i + 1 < len(snaps) and snaps[i + 1][0] <= t:
            i += 1
        _, state, w, h = snaps[i]
        lines.append(f'{PERIOD} 1 {state} {w} {h} {int(state == 5)}')
    return lines


def expected(snaps):
    """[(name, mode, ev, earliest, latest)] from the snapshot data."""
    out, live_since, mode = [], None, None
    for start, state, w, h in snaps:
        live = state == 5 and w and h
        seen = grid(snaps, start)  # the first sample that shows this snapshot
        if live and live_since is None:
            live_since, mode = seen, (w, h)
            locked = mode == (1280, 720)
            out.append(('acquiring', (0, 0), 1, live_since, live_since))
            out.append(('locked' if locked else 'unsupported', mode, 3 if locked else 1,
                        live_since + LOCK, live_since + LOCK))
        elif not live and live_since is not None:
            if mode == (1280, 720):
                out.append(('holding', mode, 1, seen + HOLD - PERIOD, seen + HOLD - PERIOD))
                out.append(('none', (0, 0), 1, seen + HOLD - PERIOD + GRACE,
                            seen + HOLD - PERIOD + GRACE))
            else:
                out.append(('none', (0, 0), 1, seen + HOLD - PERIOD, seen + HOLD - PERIOD))
            live_since = None
    return out


def main():
    binary = sys.argv[1]
    fails = 0
    for path in TRACES:
        snaps = list(snapshots(path))
        got = subprocess.run([binary, '--trace'], input='\n'.join(expand(snaps)) + '\n',
                             capture_output=True, text=True, check=True).stdout.split('\n')
        got = [g.split() for g in got if g]
        want = expected(snaps)
        ok = len(got) == len(want)
        for g, (name, mode, ev, lo, hi) in zip(got, want):
            # the binary's clock starts at the first snapshot
            t, state, size, gev = int(g[0]) + snaps[0][0], g[1], g[2], int(g[3])
            ok &= (state == name and size == f'{mode[0]}x{mode[1]}' and gev == ev
                   and lo <= t <= hi)
        print(f"{'ok  ' if ok else 'FAIL'} {Path(path).parent.name}/{Path(path).name}: "
              f"{len(snaps)} snapshots -> " + ', '.join(f'{g[1]} {g[2]}@{int(g[0]) + snaps[0][0]}' for g in got))
        if not ok:
            print('     expected', want)
            fails += 1
    print('trace replay', 'FAILED' if fails else 'passed')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
