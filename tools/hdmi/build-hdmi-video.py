#!/usr/bin/env python3
"""Collect the event-driven HDMI-in bundle (HDMI panel-source design 10.26):
the route B bridge module, the udev rule, the two units, the runtime
staging script and the installer, plus SHA256SUMS. The module must already be built
(build/route-b/module/h713-hdmi-v4l2.ko against the production kernel)."""
import argparse
import hashlib
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
SOURCES = {
    'h713-hdmi-v4l2.ko': 'build/route-b/module/h713-hdmi-v4l2.ko',
    '71-h713-hdmi-in.rules': 'tools/hdmi/71-h713-hdmi-in.rules',
    'h713-hdmi-ring.service': 'tools/hdmi/h713-hdmi-ring.service',
    'h713-hdmi-video.service': 'tools/hdmi/h713-hdmi-video.service',
    'stage-hdmi-video.sh': 'tools/hdmi/stage-hdmi-video.sh',
    'install-hdmi-video.sh': 'tools/hdmi/install-hdmi-video.sh',
}


def build(output):
    output.mkdir(parents=True, exist_ok=True)
    for name, source in SOURCES.items():
        shutil.copyfile(ROOT / source, output / name)
    for script in ('stage-hdmi-video.sh', 'install-hdmi-video.sh'):
        (output / script).chmod(0o755)
    (output / 'SHA256SUMS').write_text(''.join(
        hashlib.sha256((output / name).read_bytes()).hexdigest() + '  ' + name + '\n'
        for name in sorted(SOURCES)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    build(parser.parse_args().output)
