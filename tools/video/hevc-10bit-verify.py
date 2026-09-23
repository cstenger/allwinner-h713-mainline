#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Prove the VE's Main10 output is bit-exact 10 bit. RUNS ON THE TARGET.

This is a different question from hevc-10bit-test.sh, which scores the 8-bit
plane a client sees today and expects ~57 dB. Here the 2-bit side plane is read
back as well and the full 10-bit sample is reconstructed, so the only acceptable
answer is EXACT: every sample of every plane equal to a software 10-bit decode.

A PSNR threshold would be the wrong gate. The 8-bit plane alone already scores
59 dB against a 10-bit reference, so any threshold loose enough to be safe would
pass a run in which the 2-bit plane was never read.

PICK A HEIGHT THAT IS 8 MOD 16. The 2-bit chroma rows start after coded_h luma
rows -- the SPS height, a multiple of 8 -- not after the capture canvas height,
which is a multiple of 16. Those agree at 480 and 720 and disagree at 482, and
reading chroma at the canvas height gives bit-exact luma with 81.6% of chroma
correct and maxerr 3, which reads as rounding rather than a layout error. The
default vector list includes 642x482 for exactly this reason.

    usage: ./hevc-10bit-verify.py [--probe FULL_DUMP.so] [W]x[H]:CLIP ...
"""
import argparse
import math
import os
import subprocess
import sys
from pathlib import Path

VECTORS = '/root/video-test'
DEFAULT = [
    f'640x480:{VECTORS}/h07-640x480-main10.h265',
    f'1280x720:{VECTORS}/h08-1280x720-main10.h265',
    f'642x482:{VECTORS}/h09-642x482-main10.h265',
]

parser = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('vectors', nargs='*', default=DEFAULT,
                    help='WxH:path entries; default is the three-vector set')
parser.add_argument('--probe', type=Path, default=Path('/root/probe-full.so'),
                    help='LD_PRELOAD dumper built with CEDRUS_DUMP_FULL support')
parser.add_argument('--frames', type=int, default=5)
args = parser.parse_args()

if not args.probe.is_file():
    parser.error(f'{args.probe} not found; build cedrus-compose-probe.c with '
                 'CEDRUS_DUMP_FULL and pass it with --probe')

DUMP = Path('/var/tmp/hevc10-capture.bin')
REF = Path('/var/tmp/hevc10-reference.yuv')


def decode(clip):
    """Decode on the VE and dump the whole allocated capture buffer."""
    env = {k: v for k, v in os.environ.items() if not k.startswith('CEDRUS_')}
    env.update(LIBVA_DRIVER_NAME='v4l2_request',
               LIBVA_DRIVERS_PATH='/usr/lib/aarch64-linux-gnu/dri',
               LD_PRELOAD=str(args.probe), CEDRUS_DUMP=str(DUMP),
               CEDRUS_DUMP_AT='1', CEDRUS_DUMP_ONLY='1', CEDRUS_DUMP_FULL='1')
    DUMP.unlink(missing_ok=True)
    p = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error',
                        '-hwaccel', 'vaapi', '-hwaccel_output_format', 'vaapi',
                        '-i', clip, '-frames:v', str(args.frames), '-f', 'null', '-'],
                       env=env, capture_output=True, text=True, timeout=120)
    if p.returncode or not DUMP.exists():
        raise RuntimeError(f'{clip}: hardware decode failed: {p.stderr[-600:]}')
    if 've+' not in p.stderr and 'compose-probe: saved' not in p.stderr:
        raise RuntimeError(f'{clip}: no capture was dumped: {p.stderr[-600:]}')
    return DUMP.read_bytes()


def reference(clip, w, h):
    subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', clip,
                    '-frames:v', '1', '-pix_fmt', 'yuv420p10le', '-f', 'rawvideo',
                    str(REF)], check=True)
    r = REF.read_bytes()
    want = w * h * 3  # three planes of 16-bit samples, 4:2:0
    if len(r) < want:
        raise RuntimeError(f'{clip}: reference is {len(r)} bytes, expected {want}')

    def plane(off, n):
        return [r[off + 2 * i] | (r[off + 2 * i + 1] << 8) for i in range(n)]

    return (plane(0, w * h), plane(w * h * 2, w * h // 4),
            plane(w * h * 2 + w * h // 2, w * h // 4))


def unpack(eight, two, pitch_8, pitch_2, row0, rows, cols):
    """Rebuild 10-bit samples from the 8-bit plane and the packed 2-bit plane."""
    out = []
    for y in range(rows):
        base = (row0 + y) * pitch_2
        row8 = y * pitch_8
        for x in range(cols):
            packed = two[base + (x >> 2)]
            out.append((eight[row8 + x] << 2) | ((packed >> (2 * (x & 3))) & 3))
    return out


def score(name, got, want):
    exact = sum(1 for a, b in zip(got, want) if a == b)
    mse = sum((a - b) ** 2 for a, b in zip(got, want)) / len(got)
    psnr = 99.0 if not mse else 10 * math.log10(1023 * 1023 / mse)
    maxerr = max(abs(a - b) for a, b in zip(got, want))
    ok = exact == len(got)
    print('    %-2s %7d/%7d exact (%6.2f%%)  PSNR %6.2f dB  maxerr %d  %s'
          % (name, exact, len(got), 100 * exact / len(got), psnr, maxerr,
             'OK' if ok else 'FAIL'))
    return ok


failures = 0
for spec in args.vectors:
    geom, _, clip = spec.partition(':')
    w, h = (int(v) for v in geom.split('x'))
    if not Path(clip).is_file():
        print(f'{clip}: missing, skipped')
        continue

    # Capture canvas: the pitch is 32-aligned, the height 16-aligned, and the
    # coded picture is 8-aligned. The width alignment is 32 rather than 16
    # because the hardware rounds the chroma stride field up to 16 in chroma
    # units -- a 16-aligned pitch that is not also 32-aligned makes the engine
    # read reference chroma at a wider stride than it wrote, which corrupted
    # every inter frame. See docs/reference/hevc-unaligned-chroma-2026-09-23.md.
    # The 2-bit chroma rows follow coded_h luma rows, NOT canvas_h -- docstring.
    canvas_w, canvas_h = (w + 31) // 32 * 32, (h + 15) // 16 * 16
    coded_h = (h + 7) // 8 * 8
    pitch_2 = ((canvas_w + 3) // 4 + 31) // 32 * 32

    data = decode(clip)
    nv12 = canvas_w * canvas_h * 3 // 2
    if len(data) <= nv12:
        raise RuntimeError(f'{clip}: buffer is {len(data)} bytes with no 2-bit '
                           f'plane past {nv12}; is the stream really Main10?')
    luma8, chroma8, two = data[:canvas_w * canvas_h], data[canvas_w * canvas_h:nv12], data[nv12:]

    print('%s  %dx%d canvas %dx%d coded_h %d  buffer %d (nv12 %d + 2bit %d, pitch %d)'
          % (Path(clip).name, w, h, canvas_w, canvas_h, coded_h,
             len(data), nv12, len(data) - nv12, pitch_2))

    ref_y, ref_u, ref_v = reference(clip, w, h)
    hw_y = unpack(luma8, two, canvas_w, pitch_2, 0, h, w)
    hw_c = unpack(chroma8, two, canvas_w, pitch_2, coded_h, h // 2, w)

    ok = score('Y', hw_y, ref_y)
    ok &= score('U', hw_c[0::2], ref_u)
    ok &= score('V', hw_c[1::2], ref_v)
    failures += not ok

print('\n%s' % ('all vectors bit-exact' if not failures
                else f'{failures} vector(s) NOT bit-exact'))
sys.exit(1 if failures else 0)
