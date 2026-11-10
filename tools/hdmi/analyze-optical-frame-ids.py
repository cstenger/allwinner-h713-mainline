#!/usr/bin/env python3
"""Decode mirrored H713 motion-pattern IDs from two displays in one video."""

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

WIDTH = 1280
HEIGHT = 720
BANDS = (0, HEIGHT * 3 // 10, HEIGHT * 6 // 10, HEIGHT * 9 // 10)
CELL = WIDTH // 10
SOURCE_RATE = 60
ACTIVE_EDGE_MARGIN = 24
MAX_DELAY_FRAMES = 12
BAND_SEARCH_RADIUS = 36


def parse_quad(value):
    try:
        points = [[float(axis) for axis in point.split(",")]
                  for point in value.split(";")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("quad must contain numeric x,y points") from exc
    if len(points) != 4 or any(len(point) != 2 for point in points):
        raise argparse.ArgumentTypeError(
            "quad must be TLx,TLy;TRx,TRy;BRx,BRy;BLx,BLy")
    return np.array(points, dtype=np.float32)


def transform_for(quad):
    destination = np.array([[0, 0], [WIDTH - 1, 0],
                            [WIDTH - 1, HEIGHT - 1], [0, HEIGHT - 1]],
                           dtype=np.float32)
    return cv2.getPerspectiveTransform(quad, destination)


def sample_band(gray, top):
    foreground_rows = slice(top + 8, top + 40)
    # Compare every cell with the eight-row gap immediately below it.  The
    # displays and projection surface are not uniformly illuminated, so one
    # background sample at the left edge gives bad thresholds for cells across
    # the image.  The generated pattern deliberately leaves this gap before
    # the moving stripe begins at top + 48.
    background_rows = slice(top + 40, top + 48)

    def local_score(left, right):
        foreground = float(np.mean(gray[foreground_rows, left:right]))
        background = float(np.mean(gray[background_rows, left:right]))
        return foreground - background

    contrast = local_score(8, 40)
    samples = []
    for bit in range(8):
        left = CELL + CELL * bit
        sample = local_score(left + 8, left + CELL - 8)
        samples.append(sample)
    return {
        "contrast": contrast,
        "samples": samples,
    }


def sample_display(frame, transform):
    warped = cv2.warpPerspective(frame, transform, (WIDTH, HEIGHT))
    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    # Phone stabilization and wide-angle lens distortion can move the warped
    # bands by tens of rows even when the filmed displays stay fixed.  Track
    # each known left marker independently instead of treating the initial
    # quadrilateral as a perfect per-frame registration.
    marker_profile = np.mean(gray[:, 8:40], axis=1)
    tops = []
    for expected in BANDS:
        first = max(0, expected - BAND_SEARCH_RADIUS)
        last = min(HEIGHT - 48, expected + BAND_SEARCH_RADIUS)
        scores = [float(np.mean(marker_profile[top + 8:top + 40]))
                  for top in range(first, last + 1)]
        tops.append(first + int(np.argmax(scores)))
    return [sample_band(gray, top) for top in tops]


def two_means(values):
    """Return stable low/high centers for one cell's temporal samples."""
    low, high = np.percentile(values, (10, 90))
    for _ in range(20):
        threshold = (low + high) / 2
        lower = values[values <= threshold]
        upper = values[values > threshold]
        if not len(lower) or not len(upper):
            break
        new_low = float(np.mean(lower))
        new_high = float(np.mean(upper))
        if abs(new_low - low) + abs(new_high - high) < 0.001:
            low, high = new_low, new_high
            break
        low, high = new_low, new_high
    return low, high


def fit_levels(samples, display):
    levels = []
    for band in range(len(BANDS)):
        active = [frame[display][band]["samples"] for frame in samples]
        if not active:
            levels.append(None)
            continue
        columns = np.asarray(active, dtype=np.float32)
        band_levels = []
        for bit in range(8):
            low, high = two_means(columns[:, bit])
            band_levels.append((low, high))
        levels.append(band_levels)
    return levels


def activity_window(samples, min_contrast):
    active = []
    for frame in samples:
        source = sum(band["contrast"] >= min_contrast
                     for band in frame["source"])
        projector = sum(band["contrast"] >= min_contrast
                        for band in frame["projector"])
        if source >= 2 and projector >= 2:
            active.append(frame["camera_frame"])
    if not active:
        raise SystemExit("no simultaneous pattern activity found")
    runs = []
    start = previous = active[0]
    for index in active[1:]:
        if index - previous > 12:
            runs.append((start, previous))
            start = index
        previous = index
    runs.append((start, previous))
    return max(runs, key=lambda run: run[1] - run[0])


def emission_matrix(samples, display, band, levels):
    bit_values = ((np.arange(256, dtype=np.uint16)[:, None] >>
                   np.arange(8, dtype=np.uint16)) & 1).astype(np.float32)
    emissions = []
    for frame in samples:
        scores = np.asarray(frame[display][band]["samples"], dtype=np.float32)
        low = np.asarray([pair[0] for pair in levels], dtype=np.float32)
        high = np.asarray([pair[1] for pair in levels], dtype=np.float32)
        normalized = np.clip((scores - low) / np.maximum(high - low, 1),
                             -0.5, 1.5)
        emissions.append(np.sum((bit_values - normalized) ** 2, axis=1))
    return np.asarray(emissions)


def infer_from_emissions(emissions):
    """Decode the cyclic counter with 0/1 steps and penalized two-step gaps."""
    costs = emissions[0].copy()
    backtrack = np.empty((len(emissions), 256), dtype=np.uint8)
    states = np.arange(256)
    for index in range(1, len(emissions)):
        candidates = np.stack((costs,
                               np.roll(costs, 1),
                               np.roll(costs, 2) + 2.0))
        choice = np.argmin(candidates, axis=0)
        costs = candidates[choice, states] + emissions[index]
        backtrack[index] = choice
    state = int(np.argmin(costs))
    sequence = [state]
    for index in range(len(emissions) - 1, 0, -1):
        state = (state - int(backtrack[index, state])) % 256
        sequence.append(state)
    sequence.reverse()
    residual = float(np.mean([
        emissions[index, state] for index, state in enumerate(sequence)]))
    return sequence, residual


def infer_display(samples, display, levels_by_band):
    emissions = [emission_matrix(samples, display, band, levels)
                 for band, levels in enumerate(levels_by_band)]
    joint = np.zeros_like(emissions[0])
    for matrix in emissions:
        # A rolling camera and top-to-bottom display scanout can put a band one
        # counter step on either side of the display's common frame identity.
        joint += np.minimum.reduce((matrix, np.roll(matrix, 1, axis=1),
                                    np.roll(matrix, -1, axis=1)))
    common, residual = infer_from_emissions(joint)
    sequences = []
    band_residuals = []
    for matrix in emissions:
        sequence = []
        error = 0.0
        for index, state in enumerate(common):
            candidates = ((state - 1) % 256, state, (state + 1) % 256)
            selected = min(candidates, key=lambda value: matrix[index, value])
            sequence.append(selected)
            error += float(matrix[index, selected])
        sequences.append(sequence)
        band_residuals.append(round(error / len(samples), 4))
    return common, sequences, round(residual / len(BANDS), 4), band_residuals


def infer_delay(source_sequences, projector_emissions, max_delay):
    count = len(source_sequences[0])
    by_band = []
    for band, matrix in enumerate(projector_emissions):
        costs = np.empty((count, max_delay + 1), dtype=np.float32)
        for index, source in enumerate(source_sequences[band]):
            states = (source - np.arange(max_delay + 1)) % 256
            costs[index] = matrix[index, states]
        by_band.append(costs)

    # The median prevents one dim or partially occluded band from controlling
    # the result while preserving three independent optical cross-checks.
    emissions = np.median(np.stack(by_band), axis=0)
    path_cost = emissions[0].copy()
    backtrack = np.empty((count, max_delay + 1), dtype=np.uint8)
    delay_states = np.arange(max_delay + 1)
    transition = np.abs(delay_states[:, None] - delay_states[None, :]) * 2.0
    for index in range(1, count):
        candidates = path_cost[:, None] + transition
        previous = np.argmin(candidates, axis=0)
        path_cost = candidates[previous, delay_states] + emissions[index]
        backtrack[index] = previous
    delay = int(np.argmin(path_cost))
    sequence = [delay]
    for index in range(count - 1, 0, -1):
        delay = int(backtrack[index, delay])
        sequence.append(delay)
    sequence.reverse()

    band_sequences = []
    for costs in by_band:
        band_sequences.append([
            int(np.argmin(costs[index, max(0, delay - 1):
                                     min(max_delay, delay + 1) + 1]) +
                max(0, delay - 1))
            for index, delay in enumerate(sequence)
        ])
    residual = float(np.mean([
        emissions[index, delay] for index, delay in enumerate(sequence)]))
    return sequence, band_sequences, round(residual, 4)


def percentile(values, percent):
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def summarize(delays):
    minimum = min(delays)
    median = statistics.median(delays)
    p95 = percentile(delays, 95)
    p99 = percentile(delays, 99)
    maximum = max(delays)
    return {
        "samples": len(delays),
        "histogram": {str(value): count
                      for value, count in sorted(Counter(delays).items())},
        "min_frames": minimum,
        "median_frames": median,
        "p95_frames": round(p95, 2),
        "p99_frames": round(p99, 2),
        "max_frames": maximum,
        "min_milliseconds": round(minimum * 1000 / SOURCE_RATE, 2),
        "median_milliseconds": round(median * 1000 / SOURCE_RATE, 2),
        "p95_milliseconds": round(p95 * 1000 / SOURCE_RATE, 2),
        "p99_milliseconds": round(p99 * 1000 / SOURCE_RATE, 2),
        "max_milliseconds": round(maximum * 1000 / SOURCE_RATE, 2),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video", type=Path)
    ap.add_argument("--source-quad", required=True, type=parse_quad,
                    help="source TL;TR;BR;BL as x,y points")
    ap.add_argument("--projector-quad", required=True, type=parse_quad,
                    help="projector TL;TR;BR;BL as x,y points")
    ap.add_argument("--min-contrast", type=float, default=20)
    ap.add_argument("--details", type=Path)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    capture = cv2.VideoCapture(str(args.video))
    if not capture.isOpened():
        raise SystemExit(f"could not open {args.video}")
    camera_rate = capture.get(cv2.CAP_PROP_FPS)
    source_transform = transform_for(args.source_quad)
    projector_transform = transform_for(args.projector_quad)
    samples = []
    frame_index = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        samples.append({
            "camera_frame": frame_index,
            "source": sample_display(frame, source_transform),
            "projector": sample_display(frame, projector_transform),
        })
        frame_index += 1
    capture.release()

    # The four repeated markers locate the longest interval in which both
    # displays contain the pattern.  Allow individual bands to be dim because
    # the projection surface has a strong brightness gradient.
    active_start, active_end = activity_window(samples, args.min_contrast)
    if active_end - active_start + 1 <= ACTIVE_EDGE_MARGIN * 2:
        raise SystemExit("simultaneous pattern activity interval was too short")
    active_start += ACTIVE_EDGE_MARGIN
    active_end -= ACTIVE_EDGE_MARGIN
    active_samples = samples[active_start:active_end + 1]
    source_levels = fit_levels(active_samples, "source")
    projector_levels = fit_levels(active_samples, "projector")
    rows = []
    by_band = [[] for _ in BANDS]
    _, source_sequences, source_joint_residual, source_residuals = \
        infer_display(active_samples, "source", source_levels)
    projector_emissions = [
        emission_matrix(active_samples, "projector", band, levels)
        for band, levels in enumerate(projector_levels)
    ]
    delays, band_delays, delay_fit_residual = infer_delay(
        source_sequences, projector_emissions, MAX_DELAY_FRAMES)

    for offset, frame in enumerate(active_samples):
        source_ids = [sequence[offset] for sequence in source_sequences]
        projector_ids = [
            (source - band_delays[band][offset]) % 256
            for band, source in enumerate(source_ids)
        ]
        frame_band_delays = [sequence[offset] for sequence in band_delays]
        for band, delay in enumerate(frame_band_delays):
            by_band[band].append(delay)
        frame_index = frame["camera_frame"]
        rows.append({
            "camera_frame": frame_index,
            "camera_time_seconds": round(frame_index / camera_rate, 6),
            "source_ids": source_ids,
            "projector_ids": projector_ids,
            "delay_frames": frame_band_delays,
            "consensus_delay_frames": delays[offset],
        })

    all_delays = delays
    if not all_delays:
        raise SystemExit("no confident paired frame IDs were decoded")
    result = {
        "video": str(args.video),
        "encoded_playback_rate_fps": round(camera_rate, 6),
        "decoded_camera_frames": len(rows),
        "active_camera_frame_first": active_start,
        "active_camera_frame_last": active_end,
        "source_pattern_rate_fps": SOURCE_RATE,
        "source_joint_fit_residual": source_joint_residual,
        "delay_fit_residual": delay_fit_residual,
        "source_fit_residual_by_band": source_residuals,
        "max_delay_frames_considered": MAX_DELAY_FRAMES,
        "same_normalized_band_consensus": summarize(all_delays),
        "by_band": {str(index): summarize(delays)
                    for index, delays in enumerate(by_band) if delays},
        "nominal_milliseconds_per_source_frame": round(1000 / SOURCE_RATE, 6),
        "caveat": ("the source display is the optical reference; values "
                   "include relative display scanout/response and are not "
                   "corrected for rolling-camera readout"),
    }
    text = json.dumps(result, indent=2) + "\n"
    if args.details:
        args.details.write_text(json.dumps(rows, indent=2) + "\n")
    if args.output:
        args.output.write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
