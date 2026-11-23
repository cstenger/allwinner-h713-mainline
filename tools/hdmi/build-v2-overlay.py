#!/usr/bin/env python3
"""Build the projector's (HY200_QZ713_V2) HDMI input rootfs overlay.

  tools/hdmi/build-v2-overlay.py --kernel-tree DIR --output DIR

Builds the five HDMI modules against the V2 slot kernel tree and assembles
the V2 release overlay (tools/release/build.py v2_overlay, the same code
`build.py --board v2` uses): session, signal owner, capture bridge, health
ack, speaker and their units, with the V2 calibration
(config/hy200-v2-calibration.json). Pass the result to tools/rootfs/build.sh
--release-overlay. For a release, use tools/release/build.py --board v2.

The V2 needs no startup script: U-Boot's `h713_disp boot-v2` (patch 0019)
launches the display firmware, selects source 3 and publishes
/chosen/h713,hdmi-boot-v1, which every HDMI unit requires. Nothing here
touches a board.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# The Android DSP patch the receiver session verifies (production-vendor.json
# pins the same bytes as hdmi/hdmi-audio-dsp.bin).
DSP = ROOT/'docs/hdmi-evidence/2026-10-07-android-audio/audio-dsp-patch.bin'
DSP_SHA256 = '8e31db199e0078d142f622436ff0b7249b333dbb6df8ec3fbabc0d8fea6ea0c5'
# The V2's HDMI-to-speaker delay and keystone state live in this file
# (docs/hdmi-evidence/2026-11-23-v2-avsync/ for the delay).
CALIBRATION = ROOT/'config/hy200-v2-calibration.json'


def release_builder():
    spec = importlib.util.spec_from_file_location('h713_release_build', ROOT/'tools/release/build.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--kernel-tree', type=Path, required=True, help='built V2 slot kernel tree')
    p.add_argument('--output', type=Path, required=True, help='new overlay directory')
    p.add_argument('--audio-delay',
                   help='override the calibrated HDMI-to-speaker delay in seconds (trials only)')
    a = p.parse_args()
    b = release_builder()
    cal = b.calibration(CALIBRATION, 'v2')
    if a.audio_delay is not None:
        b.need(0 <= float(a.audio_delay) <= 1, 'invalid audio delay')
        cal = dict(cal, hdmi_audio_delay_seconds=a.audio_delay)
    kernel = a.kernel_tree.resolve()
    output = a.output.resolve()
    b.need(not output.exists(), 'output must be new: '+str(output))
    b.need((kernel/'Module.symvers').is_file(), 'kernel tree is not built: '+str(kernel))
    dtb = kernel/'arch/arm64/boot/dts/allwinner/sun50i-h713-hy200-qz713-v2.dtb'
    b.need(dtb.is_file(), 'kernel tree has no V2 DTB')
    b.need(b'hdmi-mips-shutdown' in dtb.read_bytes(), 'V2 DTB lacks the HDMI resources (kernel 0218)')
    b.need(hashlib.sha256(DSP.read_bytes()).hexdigest() == DSP_SHA256, 'DSP patch hash mismatch')

    with tempfile.TemporaryDirectory(prefix='h713-v2-overlay-') as work:
        work = Path(work)
        env = dict(os.environ)
        env['KCFLAGS'] = '-ffile-prefix-map='+str(work)+'=.'
        built = b.modules(kernel, work, env)
        staging = work/'overlay'
        b.v2_overlay(staging, built, DSP, cal)
        (staging/'usr/share/h713-release/v2-hdmi-overlay.json').write_text(json.dumps(dict(
            board='hy200-qz713-v2', kernel_tree=kernel.name,
            hdmi_audio_delay_seconds=cal['hdmi_audio_delay_seconds'],
            omitted_units=list(b.V2_OMITTED_UNITS),
            modules={k: b.sha(v) for k, v in sorted(built.items())},
            dsp_sha256=DSP_SHA256), indent=2)+'\n')
        shutil.copytree(staging, output, symlinks=True)
    print(f'{output}: V2 HDMI overlay for {kernel.name}')


if __name__ == '__main__':
    main()
