#!/usr/bin/env python3
"""Build the projector's (HY200_QZ713_V2) HDMI input rootfs overlay.

  tools/hdmi/build-v2-overlay.py --kernel-tree DIR --output DIR

Builds the five HDMI modules against the V2 slot kernel tree and assembles
the same HDMI runtime the bench release ships (tools/release/build.py
hdmi_payload): session, signal owner, capture bridge, health ack, speaker
and their units. Pass the result to tools/rootfs/build.sh --release-overlay.

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
# The bench board's measured HDMI-to-speaker delay (2026-11-18). The V2 has
# the same panel pipeline; replace it once the V2 is measured.
DEFAULT_AUDIO_DELAY = '0.115'
# Not needed on the V2: it boots the vendor's display_cfg.xml (b3e6e8f6...),
# whose elog_init_setting is mode 1 (async) level 1. The firmware's elog_init
# stores that level at 0x4b48bd9c, which reads 1 live. The 2 MiB flush stall
# the unit prevents needs buf mode (2) at level 5, the bench's own 2026-09-04
# debugging edit (f97eec07). `elog -l 2` would raise the V2's level.
# (2026-11-22, firmware 16c74a28 disassembly + live read on slot B.)
V2_OMITTED_UNITS = ('h713-mips-elog-level.service',)


def release_builder():
    spec = importlib.util.spec_from_file_location('h713_release_build', ROOT/'tools/release/build.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--kernel-tree', type=Path, required=True, help='built V2 slot kernel tree')
    p.add_argument('--output', type=Path, required=True, help='new overlay directory')
    p.add_argument('--audio-delay', default=DEFAULT_AUDIO_DELAY,
                   help=f'HDMI-to-speaker delay in seconds (default {DEFAULT_AUDIO_DELAY})')
    a = p.parse_args()
    b = release_builder()
    kernel = a.kernel_tree.resolve()
    output = a.output.resolve()
    b.need(not output.exists(), 'output must be new: '+str(output))
    b.need((kernel/'Module.symvers').is_file(), 'kernel tree is not built: '+str(kernel))
    dtb = kernel/'arch/arm64/boot/dts/allwinner/sun50i-h713-hy200-qz713-v2.dtb'
    b.need(dtb.is_file(), 'kernel tree has no V2 DTB')
    b.need(b'hdmi-mips-shutdown' in dtb.read_bytes(), 'V2 DTB lacks the HDMI resources (kernel 0218)')
    b.need(hashlib.sha256(DSP.read_bytes()).hexdigest() == DSP_SHA256, 'DSP patch hash mismatch')
    float(a.audio_delay)

    with tempfile.TemporaryDirectory(prefix='h713-v2-overlay-') as work:
        work = Path(work)
        env = dict(os.environ)
        env['KCFLAGS'] = '-ffile-prefix-map='+str(work)+'=.'
        built = b.modules(kernel, work, env)
        staging = work/'overlay'
        staging.mkdir()
        b.hdmi_payload(staging, built, DSP, a.audio_delay)
        for unit in V2_OMITTED_UNITS:
            for path in (staging/'etc/systemd/system'/unit,
                         staging/'etc/systemd/system/multi-user.target.wants'/unit,
                         staging/'usr/lib/h713-hdmi'/unit):
                path.unlink()
        release = staging/'usr/share/h713-release'
        release.mkdir(parents=True)
        (release/'v2-hdmi-overlay.json').write_text(json.dumps(dict(
            board='hy200-qz713-v2', kernel_tree=kernel.name,
            hdmi_audio_delay_seconds=a.audio_delay,
            omitted_units=list(V2_OMITTED_UNITS),
            modules={k: b.sha(v) for k, v in sorted(built.items())},
            dsp_sha256=DSP_SHA256), indent=2)+'\n')
        (staging/'.h713-release-overlay').write_text('h713-production-overlay-v1\n')
        shutil.copytree(staging, output, symlinks=True)
    print(f'{output}: V2 HDMI overlay for {kernel.name}')


if __name__ == '__main__':
    main()
