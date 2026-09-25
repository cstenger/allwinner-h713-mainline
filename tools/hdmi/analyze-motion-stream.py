#!/usr/bin/env python3
"""Check repeated frame IDs and moving stripe in a 640x480 NV16 stream."""

import argparse
import json
from pathlib import Path

import numpy as np

WIDTH = 640
HEIGHT = 480
FRAME = 2 * WIDTH * HEIGHT
# COSMIC draws its top panel over the source video, obscuring the first band.
BANDS = (168, 312, 456)
STRIPE_ROWS = (96, 240, 384)


def analyze(path):
    if path.stat().st_size % FRAME:
        raise ValueError("stream ends in a partial NV16 frame")
    stream = np.memmap(path, dtype=np.uint8, mode="r").reshape(-1, 2, HEIGHT, WIDTH)
    records = []
    for index, frame in enumerate(stream):
        y = frame[0]
        band_ids = []
        sync = []
        for row in BANDS:
            sync.append(bool(y[row - 4:row + 4, 16:32].mean() > 128))
            value = 0
            for bit in range(8):
                left = 64 + bit * 64
                if y[row - 4:row + 4, left + 20:left + 36].mean() > 128:
                    value |= 1 << bit
            band_ids.append(value)
        stripe_positions = []
        for row in STRIPE_ROWS:
            bright = np.flatnonzero(y[row] > 128)
            stripe_positions.append(int(bright[0]) if len(bright) else None)
        present = all(sync)
        coherent = present and len(set(band_ids)) == 1
        expected = band_ids[0] * 7 % WIDTH if coherent else None
        stripe_ok = coherent and all(
            position is not None and abs(position - expected) <= 2
            for position in stripe_positions)
        records.append({"frame": index, "pattern_present": present,
                        "band_ids": band_ids, "bands_agree": coherent,
                        "stripe_positions": stripe_positions,
                        "stripe_ok": stripe_ok})
    patterned = [r for r in records if r["pattern_present"]]
    agreed = [r for r in patterned if r["bands_agree"]]
    ids = [r["band_ids"][0] for r in agreed]
    steps = [(b - a) % 256 for a, b in zip(ids, ids[1:])]
    anomalies = [{"capture_frame": agreed[index + 1]["frame"],
                  "previous_id": ids[index], "id": ids[index + 1],
                  "step": step}
                 for index, step in enumerate(steps) if step != 1]
    return {"file": str(path), "frames": len(records),
            "patterned_frames": len(patterned),
            "band_mismatches": sum(not r["bands_agree"] for r in patterned),
            "stripe_mismatches": sum(not r["stripe_ok"] for r in patterned),
            "sequential_steps": sum(step == 1 for step in steps),
            "duplicate_steps": sum(step == 0 for step in steps),
            "skipped_steps": sum(step > 1 for step in steps),
            "first_pattern_frame": patterned[0]["frame"] if patterned else None,
            "last_pattern_frame": patterned[-1]["frame"] if patterned else None,
            "first_ids": ids[:12], "last_ids": ids[-12:],
            "step_anomalies": anomalies[:20],
            "errors": [r for r in patterned if not r["bands_agree"] or
                       not r["stripe_ok"]][:20]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stream", type=Path)
    args = ap.parse_args()
    print(json.dumps(analyze(args.stream), indent=2))


if __name__ == "__main__":
    main()
