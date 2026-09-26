#!/usr/bin/env python3
"""Validate VIncap completion-event ordering against the three-pair ring."""

import argparse
import collections
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    args = parser.parse_args()
    records = [json.loads(line) for line in args.trace.read_text().splitlines()]
    samples = [record for record in records if record.get("type") == "sample"]
    if not samples or "pair_windows" not in samples[0]:
        raise SystemExit("trace has no pair-bracketed samples")

    keys = ("irq", "vde", "vs", "mode_change")
    delta = {key: samples[-1]["after"][key] - samples[0]["before"][key]
             for key in keys}
    lead_states = collections.Counter()
    ordered_steps = collections.Counter()
    for sample in samples:
        snapshots = ([sample["before"]] +
                     [value for window in sample["pair_windows"]
                      for value in (window["before"], window["after"])] +
                     [sample["after"]])
        for snapshot in snapshots:
            lead_states[snapshot["vde"] - snapshot["vs"]] += 1
        for before, after in zip(snapshots, snapshots[1:]):
            step = (after["vde"] - before["vde"],
                    after["vs"] - before["vs"])
            if step != (0, 0):
                ordered_steps[step] += 1

    last = [None] * 3
    epoch_pairs = collections.defaultdict(set)
    definite_changes = ambiguous_changes = 0
    vde_lead_windows = vde_lead_changes = 0
    for sample in samples:
        for window in sample["pair_windows"]:
            pair = window["pair"]
            hashes = (sample["crc32"][pair], sample["crc32"][pair + 3])
            before, after = window["before"], window["after"]
            stable = before == after
            if stable and before["vde"] == before["vs"] + 1:
                vde_lead_windows += 1
            if last[pair] is not None and hashes != last[pair][0]:
                _old_hashes, old_epoch, old_stable = last[pair]
                if stable and old_stable and old_epoch == before["vde"]:
                    epoch_pairs[before["vde"]].add(pair)
                    definite_changes += 1
                    if before["vde"] == before["vs"] + 1:
                        vde_lead_changes += 1
                else:
                    ambiguous_changes += 1
            last[pair] = (hashes, before["vde"], stable)

    pair_sets = collections.Counter(tuple(sorted(value))
                                    for value in epoch_pairs.values())
    epochs = sorted((epoch, next(iter(pairs)))
                    for epoch, pairs in epoch_pairs.items()
                    if len(pairs) == 1)
    contiguous = 0
    sequence_errors = []
    for previous, current in zip(epochs, epochs[1:]):
        if current[0] != previous[0] + 1:
            continue
        contiguous += 1
        if current[1] != (previous[1] + 1) % 3:
            sequence_errors.append([previous, current])

    passed = (delta["irq"] == delta["vde"] + delta["vs"] and
              delta["vde"] == delta["vs"] and delta["vde"] > 0 and
              delta["mode_change"] == 0 and
              set(lead_states).issubset({0, 1}) and
              vde_lead_windows > 0 and vde_lead_changes == 0 and
              all(len(pair_set) == 1 for pair_set in pair_sets) and
              contiguous == delta["vde"] and not sequence_errors)
    result = {
        "pass": passed,
        "samples": len(samples),
        "duration_seconds": samples[-1]["end_ns"] / 1e9,
        "counter_delta": delta,
        "vde_minus_vs_observations": dict(sorted(lead_states.items())),
        "ordered_event_steps": {f"vde+{v[0]},vs+{v[1]}": count
                                for v, count in sorted(ordered_steps.items())},
        "definite_ring_changes": definite_changes,
        "ambiguous_boundary_changes": ambiguous_changes,
        "write_epochs": len(epoch_pairs),
        "epoch_pair_sets": {str(key): value for key, value in pair_sets.items()},
        "contiguous_epoch_transitions": contiguous,
        "pair_sequence_errors": sequence_errors,
        "vde_before_vs_stable_windows": vde_lead_windows,
        "ring_changes_between_vde_and_vs": vde_lead_changes,
        "conclusion": ("cap-vde is the earliest observed safe pair-completion "
                       "boundary; cap-vs follows before the next pair write")
                      if passed else "completion condition not proved",
    }
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
