#!/usr/bin/env python3
"""Package the opt-in speaker consumer independently of the pinned HDMI backend."""
import argparse
import hashlib
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
SOURCES = {
    'h713-hdmi-speaker.service': 'tools/hdmi/h713-hdmi-speaker.service',
    'enable-mixer.sh': 'tools/hdmi/enable-speaker-mixer.sh',
    'install-speaker.sh': 'tools/hdmi/install-speaker.sh',
    'alsa-ctl.c': 'tools/audio/alsa-ctl.c',
    'hdmi-speaker.c': 'tools/hdmi/hdmi-speaker.c',
    'pipewire-speaker.py': 'tools/hdmi/pipewire-speaker.py',
}


def build(output):
    output.mkdir(parents=True, exist_ok=True)
    for name, source in SOURCES.items():
        shutil.copyfile(ROOT / source, output / name)
    (output / 'SHA256SUMS').write_text(''.join(
        hashlib.sha256((output / name).read_bytes()).hexdigest() + '  ' + name + '\n'
        for name in sorted(SOURCES)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    build(parser.parse_args().output)
