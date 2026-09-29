#!/usr/bin/env python3
"""Join V4L2/GStreamer timestamps to AFBD physical presentations."""

import argparse
import csv
import json
import statistics
from pathlib import Path

KMS_BOOTSTRAP_PRESENTATIONS = 1
KMS_BOOTSTRAP_REPEAT_INDEX = 1
WINDOW_FRAMES = 60
MAX_CLOCK_OFFSET_NS = 1_000_000


def percentile(values, percent):
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def distribution_ns(values):
    if not values:
        raise RuntimeError("cannot summarize an empty latency distribution")
    return {
        "min_us": round(min(values) / 1000, 2),
        "mean_us": round(statistics.fmean(values) / 1000, 2),
        "median_us": round(statistics.median(values) / 1000, 2),
        "p95_us": round(percentile(values, 95) / 1000, 2),
        "p99_us": round(percentile(values, 99) / 1000, 2),
        "max_us": round(max(values) / 1000, 2),
    }


def read_pipeline(path):
    metadata = {}
    rows = []
    lines = path.read_text().splitlines()
    data_lines = []
    for line in lines:
        if line.startswith("# "):
            name, value = line[2:].split("=", 1)
            metadata[name] = int(value)
        elif line:
            data_lines.append(line)
    for row in csv.DictReader(data_lines):
        rows.append({name: int(value) for name, value in row.items()})
    required = {"pipeline_base_time_ns", "gst_clock_minus_monotonic_ns"}
    if required - metadata.keys():
        raise RuntimeError("pipeline trace omitted its monotonic clock metadata")
    if abs(metadata["gst_clock_minus_monotonic_ns"]) > MAX_CLOCK_OFFSET_NS:
        raise RuntimeError("GStreamer clock is not aligned with CLOCK_MONOTONIC")
    if not rows:
        raise RuntimeError("pipeline trace contained no frames")
    for index, row in enumerate(rows):
        if row["index"] != index:
            raise RuntimeError("pipeline trace indices are not contiguous")
    return metadata, rows


def read_scanout(path):
    rows = []
    with path.open(newline="") as source:
        reader = csv.DictReader(source, delimiter=" ", skipinitialspace=True)
        for row in reader:
            rows.append({name: int(value, 0) for name, value in row.items()})
    if not rows:
        raise RuntimeError("physical scanout trace contained no presentations")
    prior_vblank = None
    for index, row in enumerate(rows):
        if row["index"] != index:
            raise RuntimeError("physical scanout trace indices are not contiguous")
        if row["present_ns"] < row["submit_ns"]:
            raise RuntimeError("physical presentation predates its submission")
        if row["latency_ns"] != row["present_ns"] - row["submit_ns"]:
            raise RuntimeError("physical scanout trace latency is inconsistent")
        if prior_vblank is not None and row["vblank"] <= prior_vblank:
            raise RuntimeError("physical vblank sequence did not advance")
        prior_vblank = row["vblank"]
    return rows


def changed_presentations(rows):
    changed = []
    repeat_indices = []
    prior = None
    for index, row in enumerate(rows):
        identity = (row["y"], row["c"])
        if identity == prior:
            repeat_indices.append(index)
            continue
        changed.append(row)
        prior = identity
    return changed, repeat_indices


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pipeline_trace", type=Path)
    ap.add_argument("scanout_trace", type=Path)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    metadata, pipeline = read_pipeline(args.pipeline_trace)
    scanout = read_scanout(args.scanout_trace)
    changed, repeat_indices = changed_presentations(scanout)
    expected_repeats = [KMS_BOOTSTRAP_REPEAT_INDEX]
    if repeat_indices != expected_repeats:
        raise RuntimeError("physical trace repeat positions were "
                           f"{repeat_indices}, expected the single KMS "
                           f"bootstrap at index {KMS_BOOTSTRAP_REPEAT_INDEX}")
    if len(changed) != len(pipeline):
        raise RuntimeError(f"cannot join {len(pipeline)} pipeline frames to "
                           f"{len(changed)} changed physical presentations")

    stages = {
        "capture_to_source_pad": [],
        "source_pad_to_sink_pad": [],
        "sink_pad_to_submit": [],
        "capture_to_submit": [],
        "submit_to_physical_vsync": [],
        "capture_to_physical_vsync": [],
    }
    prior_sequence = None
    prior_present = None
    for source, display in zip(pipeline, changed):
        capture = source["capture_completion_ns"]
        source_pad = source["source_arrival_ns"]
        sink_pad = source["sink_arrival_ns"]
        submit = display["submit_ns"]
        present = display["present_ns"]
        sequence = source["v4l2_sequence"]
        if not capture or not (capture <= source_pad <= sink_pad <= submit <= present):
            raise RuntimeError("joined frame timestamps are not monotonic")
        if prior_sequence is not None and sequence <= prior_sequence:
            raise RuntimeError("V4L2 sequence did not advance monotonically")
        if prior_present is not None and present <= prior_present:
            raise RuntimeError("physical presentation time did not advance")
        prior_sequence = sequence
        prior_present = present
        stages["capture_to_source_pad"].append(source_pad - capture)
        stages["source_pad_to_sink_pad"].append(sink_pad - source_pad)
        stages["sink_pad_to_submit"].append(submit - sink_pad)
        stages["capture_to_submit"].append(submit - capture)
        stages["submit_to_physical_vsync"].append(present - submit)
        stages["capture_to_physical_vsync"].append(present - capture)

    end_to_end = stages["capture_to_physical_vsync"]
    window = min(WINDOW_FRAMES, len(end_to_end) // 2)
    first_median = statistics.median(end_to_end[:window])
    last_median = statistics.median(end_to_end[-window:])
    result = {
        "pipeline_frames": len(pipeline),
        "physical_presentations": len(scanout),
        "kms_bootstrap_repeats": len(repeat_indices),
        "changed_physical_presentations": len(changed),
        "gst_clock_minus_monotonic_ns":
        metadata["gst_clock_minus_monotonic_ns"],
        "v4l2_sequence_first": pipeline[0]["v4l2_sequence"],
        "v4l2_sequence_last": pipeline[-1]["v4l2_sequence"],
        "stages": {name: distribution_ns(values)
                   for name, values in stages.items()},
        "queue_growth_window_frames": window,
        "first_window_median_us": round(first_median / 1000, 2),
        "last_window_median_us": round(last_median / 1000, 2),
        "last_minus_first_median_us":
        round((last_median - first_median) / 1000, 2),
    }
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(text)
    print(text, end="")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        raise SystemExit(str(exc))
