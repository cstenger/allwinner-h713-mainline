#!/usr/bin/env python3
"""Find the ALSA HDMI PCM whose valid ELD has the requested monitor name."""

import argparse
import json
import re
from pathlib import Path


def fields(path):
    result = {}
    for line in path.read_text().splitlines():
        parts = line.split(None, 1)
        if parts:
            result[parts[0]] = parts[1].strip() if len(parts) == 2 else ""
    return result


def find_pcm(monitor):
    matches = []
    for eld in sorted(Path("/proc/asound").glob("card*/eld#*")):
        data = fields(eld)
        if (data.get("monitor_present") != "1" or data.get("eld_valid") != "1" or
                data.get("monitor_name") != monitor):
            continue
        card_match = re.fullmatch(r"card(\d+)", eld.parent.name)
        eld_match = re.fullmatch(r"eld#\d+\.(\d+)", eld.name)
        if not card_match or not eld_match:
            continue
        card = int(card_match.group(1))
        # HDA exposes four ELD entries (MST device IDs 0..3) per pin/PCM.
        # Select the corresponding PCM from the card's ordered HDMI devices.
        group = int(eld_match.group(1)) // 4
        devices = sorted(
            int(match.group(1))
            for path in eld.parent.glob("pcm*p")
            if (match := re.fullmatch(r"pcm(\d+)p", path.name))
        )
        if group >= len(devices):
            continue
        device = devices[group]
        matches.append({"card": card, "device": device,
                        "pcm": f"hw:{card},{device}", "eld": str(eld),
                        "monitor_name": monitor,
                        "connection_type": data.get("connection_type"),
                        "sad_count": int(data.get("sad_count", "0"))})
    if len(matches) != 1:
        raise RuntimeError(f"expected one valid ELD named {monitor!r}, found {len(matches)}")
    return matches[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--monitor", default="H713 HDMI IN")
    args = parser.parse_args()
    try:
        print(json.dumps(find_pcm(args.monitor), sort_keys=True))
    except RuntimeError as error:
        raise SystemExit(str(error))


if __name__ == "__main__":
    main()
