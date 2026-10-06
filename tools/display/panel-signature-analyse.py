#!/usr/bin/env python3
"""Find a downstream frame signature in panel-signature.sh's samples. HOST.

    panel-signature-analyse.py DIR

Each DIR/NN-variant.json holds several reads of every comp/route/panel word
while one card was on the panel. A word is a SIGNATURE CANDIDATE when:
  * it holds one value through every sample of each card (a CRC of a static
    picture does; a frame counter or a live statistic does not),
  * the repeated 'upright' cards agree (it is reproducible), and
  * it differs between cards.
It is POSITION-sensitive when upright differs from its software mirrors and
from the 1-px shift -- only such a word can verify a hardware mirror.
Words that separate the solid colours but not upright from its mirror are
content statistics (histogram, average level), reported separately.
"""
import glob
import json
import os
import sys


def main():
    d = sys.argv[1]
    runs = []
    for p in sorted(glob.glob(os.path.join(d, "[0-9][0-9]-*.json"))):
        v = os.path.basename(p)[3:-5]
        runs.append((v, json.load(open(p))))
    if not runs:
        sys.exit(f"no samples in {d}")
    words = sorted(runs[0][1])
    stable_all, live, cand, content, position = 0, 0, [], [], []
    for w in words:
        per = []
        steady = True
        for v, data in runs:
            s = data[w]
            if len(set(s)) != 1:
                steady = False
            per.append((v, s[0], len(set(s))))
        if not steady:
            live += 1
            continue
        vals = {}
        for v, val, _n in per:
            vals.setdefault(v, set()).add(val)
        if len({val for _v, val, _n in per}) == 1:
            stable_all += 1
            continue
        if len(vals.get("upright", {0})) != 1:
            continue                     # not reproducible
        cand.append(w)
        up = next(iter(vals["upright"]))
        pos = all(v in vals and next(iter(vals[v])) != up for v in ("x", "y", "xy", "shift"))
        (position if pos else content).append((w, {v: next(iter(s)) for v, s in vals.items()}))
    print(f"{len(words)} words x {len(runs)} cards ({', '.join(v for v, _ in runs)})")
    print(f"  constant everywhere: {stable_all}; changing within a card (live): {live}; "
          f"steady, reproducible and card-dependent: {len(cand)}")
    order = list(dict.fromkeys(v for v, _ in runs))
    for title, rows in (("POSITION-SENSITIVE (upright != x, y, xy, shift)", position),
                        ("content only (card-dependent, but blind to a mirror or shift)", content)):
        print(f"\n{title}: {len(rows)}")
        if rows:
            print("  word        " + " ".join(f"{v:>9}" for v in order))
            for w, vals in rows:
                print(f"  {w:11} " + " ".join(f"{vals[v]:9X}" for v in order))
    return 0 if position else 1


if __name__ == "__main__":
    sys.exit(main())
