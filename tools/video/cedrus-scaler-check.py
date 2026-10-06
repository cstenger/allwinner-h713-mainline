#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Validate active NV12 pixels through the H713 polyphase scaler.

Run on the board with ffmpeg, the v4l2_request VA driver, the repository's
v01-v05/h01-h07 vectors, the v01-v12 VP9 vectors va-regress.sh uses, and a compiled cedrus-compose-probe.c shared
library. The large VP9 clips are generated on the board under --root on first
use (libvpx-vp9, no alt-ref frames, so decode order is display order and a
late dump is a predicted frame).
The adapter dumps capture buffers headlessly; it cannot describe scaled VA
surfaces correctly for playback or hwdownload.
"""
import argparse, concurrent.futures, json, math, os, re, subprocess
from pathlib import Path
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root', type=Path, default=Path('/mnt/media-data/scaler-tests'))
parser.add_argument('--clips', default='/root/video-test')
parser.add_argument('--vp9-clips', default='/var/tmp', help='the v01-v12 VP9 .webm vectors')
parser.add_argument('--probe', type=Path, default=Path('/mnt/media-data/cedrus-compose-probe.so'))
parser.add_argument('--expected-md5', help='require this installed module digest')
parser.add_argument('--only', choices=('all', 'vp9'), default='all',
                    help='vp9: run only the VP9 cases')
parser.add_argument('--keep-dumps', action='store_true',
                    help='keep each NV12 dump (the media partition is small)')
args = parser.parse_args()
root = args.root
root.mkdir(parents=True, exist_ok=True)
probe = args.probe
if not probe.is_file():
    parser.error('compile cedrus-compose-probe.c first and pass its .so with --probe')
env = os.environ.copy()
for key in tuple(env):
    if key.startswith('CEDRUS_'):
        env.pop(key)
env.update(LIBVA_DRIVER_NAME='v4l2_request', LIBVA_DRIVERS_PATH='/usr/lib/aarch64-linux-gnu/dri')
module = subprocess.check_output(['modinfo', '-n', 'sunxi_cedrus'], text=True).strip()
module_md5 = subprocess.check_output(['md5sum', module], text=True).split()[0]
print('installed module', module_md5, flush=True)
if args.expected_md5 and module_md5 != args.expected_md5:
    raise RuntimeError('installed module differs from the expected build')
before = subprocess.check_output(['dmesg'], text=True)
guard = Path('/sys/module/sunxi_cedrus/parameters/dma_guard')
old_guard = guard.read_text()
guard.write_text('65536\n')
results = []

def psnr(a, b):
    if len(a) != len(b):
        raise RuntimeError(f'plane lengths {len(a)} != {len(b)}')
    mse = sum(((x - y) ** 2 for x, y in zip(a, b))) / len(a)
    return 99.0 if not mse else 10 * math.log10(255 ** 2 / mse)

def test(clip, w, h, mode='format', frames=30, dump_at=1, pitch=0):
    name = f'{Path(clip).stem}-{w}x{h}-{mode}-pitch{pitch}-frames{frames}-at{dump_at}'
    dump = root / (name + '.nv12')
    dump.unlink(missing_ok=True)
    e = env.copy()
    e.update(LD_PRELOAD=str(probe), CEDRUS_DUMP=str(dump), CEDRUS_DUMP_AT=str(dump_at))
    if mode == 'unscaled':
        e['CEDRUS_DUMP_ONLY'] = '1'
    else:
        e['CEDRUS_CAPTURE_SIZE' if mode == 'format' else 'CEDRUS_COMPOSE'] = f'{w}x{h}'
    if pitch:
        e['CEDRUS_STRIDE'] = str(pitch)
    p = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-hwaccel', 'vaapi', '-hwaccel_output_format', 'vaapi', '-i', clip, '-frames:v', str(frames), '-f', 'null', '-'], env=e, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
    (root / (name + '.log')).write_text(p.stderr)
    if p.returncode or re.search('Timeout|timed out|invalid completed|Error|failed', p.stderr, re.I):
        raise RuntimeError(name + ' decode failed: ' + p.stderr)
    matches = re.findall('compose-probe: (\\d+)x(\\d+) stride=(\\d+) bytes=(\\d+) format=NV12 active=(\\d+)x(\\d+)', p.stderr)
    if not matches or not dump.exists():
        raise RuntimeError(name + ' no metadata/dump: ' + p.stderr)
    cw, ch, stride, size, aw, ah = map(int, matches[-1])
    a = dump.read_bytes()
    if not args.keep_dumps:
        dump.unlink()
    geometry_ok = (aw >= w and ah >= h) if mode == 'unscaled' else (aw, ah) == (w, h)
    if not geometry_ok or len(a) != size or (pitch and stride != pitch):
        raise RuntimeError(name + f' geometry {(cw, ch, stride, size, aw, ah)} bytes {len(a)}')
    y = b''.join((a[row * stride:row * stride + w] for row in range(h)))
    uv = b''.join((a[stride * ch + row * stride:stride * ch + row * stride + w] for row in range(h // 2)))
    ref = subprocess.check_output(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', clip, '-vf', f'select=eq(n\\,{dump_at - 1}),scale={w}:{h}:flags=bicubic', '-frames:v', '1', '-pix_fmt', 'nv12', '-f', 'rawvideo', '-'], timeout=60)
    yy = ref[:w * h]
    cc = ref[w * h:]
    scores = [psnr(y, yy), psnr(uv[::2], cc[::2]), psnr(uv[1::2], cc[1::2])]
    result = dict(name=name, geometry=[cw, ch, stride, aw, ah], psnr=scores, frames=frames, module_md5=module_md5)
    results.append(result)
    print(name, 'Y/U/V', *(f'{v:.2f}' for v in scores), flush=True)
    # Off-bucket filter ratios differ from bicubic; corrupt planes score much lower.
    if mode == 'unscaled' and 'main10' not in clip and min(scores) != 99:
        raise RuntimeError(name + ' unscaled pixels are not bit-exact')
    if min(scores) < 27 or scores[0] < 32:
        raise RuntimeError(name + ' quality failed')
    return y + uv
def vp9_clip(name, size, frames, crf):
    # Regenerated when absent; the reference is a software decode of the same
    # file, so the encoder version does not matter.
    path = root / name
    if not path.exists():
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
                        '-i', f'testsrc2=size={size}:rate=30', '-frames:v', str(frames),
                        '-c:v', 'libvpx-vp9', '-b:v', '0', '-crf', str(crf),
                        '-deadline', 'realtime', '-cpu-used', '8', '-row-mt', '1',
                        '-auto-alt-ref', '0', '-lag-in-frames', '0', '-g', str(frames),
                        '-pix_fmt', 'yuv420p', '-f', 'ivf', '-y', str(path) + '.tmp'],
                       check=True, timeout=900)
        os.rename(str(path) + '.tmp', path)
    return str(path)

def vp9_cases():
    # VP9 runs on the H.265 engine's secondary output (kernel 0167).
    clip = args.vp9_clips + '/v04-720p-default.webm'
    # 640x180 is asymmetric: a symmetric ratio cannot catch swapped H/V fields.
    # 854x478 widens the pitch (864 -> 896) so the chroma base is 256-aligned.
    for w, h in ((640, 360), (640, 180), (854, 478)):
        if test(clip, w, h) != test(clip, w, h, mode='compose'):
            raise RuntimeError(f'VP9 APIs disagree at {w}x{h}')
    # The scaler writes even sizes: odd-sized 350x286 halves to 174x142.
    for name, w, h in (('v02-inter-1tile.webm', 352, 288), ('v03-720p-4tiles.webm', 1280, 720), ('v04-720p-default.webm', 1280, 720), ('v07-seg-cyclic.webm', 640, 360), ('v09-lossless.webm', 352, 288), ('v10-odd-350x286.webm', 350, 286), ('v11-1080p-mandel.webm', 1920, 1080)):
        test(args.vp9_clips + '/' + name, w // 2 & ~1, h // 2 & ~1)
        test(args.vp9_clips + '/' + name, w, h, mode='unscaled')
    # The plane routes' sizes: 1080p and scope to the 1280-wide panel, and 4K.
    # A late dump is a P-frame: references are the full-size reconstructions.
    fhd = vp9_clip('vp9-1920x1080-ip.ivf', '1920x1080', 60, 32)
    test(fhd, 1280, 720)
    test(fhd, 1280, 720, frames=60, dump_at=45)
    test(vp9_clip('vp9-1920x800-ip.ivf', '1920x800', 30, 32), 1280, 534, dump_at=20)
    test(vp9_clip('vp9-3840x2160-ip.ivf', '3840x2160', 10, 36), 1280, 720, frames=10, dump_at=8)
    # VP9 and H.264 share TOP1's geometry and coefficient banks.
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(test, fhd, 1280, 720, frames=60, dump_at=50), pool.submit(test, args.clips + '/v04-1280x720-high.h264', 854, 478, frames=90)]
        for job in jobs:
            job.result()

def h264_hevc_cases():
    clip = args.clips + '/v04-1280x720-high.h264'
    for w, h in ((1280, 720), (640, 360), (320, 180), (640, 180), (960, 540), (854, 480), (854, 478)):
        a = test(clip, w, h)
        b = test(clip, w, h, mode='compose')
        if a != b:
            raise RuntimeError(f'APIs disagree at {w}x{h}')
    test(args.clips + '/v05-1920x1080-high.h264', 1280, 720)
    test(args.clips + '/h02-1280x720-main.h265', 854, 478)
    test(args.clips + '/h01-640x480-main.h265', 258, 242)
    test(clip, 518, 362)
    main10_pixels = test(args.clips + '/h07-640x480-main10.h265', 258, 242)
    if main10_pixels != test(args.clips + '/h07-640x480-main10.h265', 258, 242, mode='compose'):
        raise RuntimeError('Main10 sizing APIs disagree')
    test(args.clips + '/h07-640x480-main10.h265', 258, 246)
    for name, w, h in (('v01-320x240-baseline.h264', 320, 240), ('v02-1280x720-baseline.h264', 1280, 720), ('v03-1280x720-main.h264', 1280, 720), ('v04-1280x720-high.h264', 1280, 720), ('v05-1920x1080-high.h264', 1920, 1080), ('h01-640x480-main.h265', 640, 480), ('h02-1280x720-main.h265', 1280, 720), ('h03-640x480-nowpp.h265', 640, 480), ('h04-640x480-scaling.h265', 640, 480), ('h05-640x480-scaling-custom.h265', 640, 480), ('h06-640x480-lossless.h265', 640, 480), ('h07-640x480-main10.h265', 640, 480)):
        test(args.clips + '/' + name, w // 2, h // 2)
        test(args.clips + '/' + name, w, h, mode='unscaled')
    for w, h, pitch in ((640, 360, 1024), (1280, 720, 1536)):
        if test(clip, w, h) != test(clip, w, h, pitch=pitch):
            raise RuntimeError('pitch changed active pixels')
    # Different codec contexts must restore the shared geometry and coefficient banks.
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(test, clip, 854, 478, frames=90), pool.submit(test, args.clips + '/h02-1280x720-main.h265', 640, 360, frames=90)]
        for job in jobs:
            job.result()
    # A later P-frame validates full-size reconstruction and reference addressing.
    generated = root / 'ip-reference.h264'
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=1280x720:rate=30', '-frames:v', '90', '-c:v', 'libx264', '-preset', 'fast', '-bf', '0', '-g', '90', '-pix_fmt', 'yuv420p', '-f', 'h264', '-y', str(generated)], check=True, timeout=60)
    test(str(generated), 854, 478, frames=90, dump_at=60)
    # Main10 also needs the full-size packed side planes for P-frame references.
    generated = root / 'ip-reference-main10.h265'
    subprocess.run([
        'ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
        '-i', 'testsrc2=size=640x480:rate=30', '-frames:v', '90',
        '-c:v', 'libx265', '-preset', 'fast', '-pix_fmt', 'yuv420p10le',
        '-x265-params', 'bframes=0:keyint=90:pools=1:frame-threads=1:log-level=error',
        '-f', 'hevc', '-y', str(generated),
    ], check=True, timeout=60)
    test(str(generated), 258, 242, frames=90, dump_at=60)

try:
    if args.only == 'all':
        h264_hevc_cases()
    vp9_cases()
    after = subprocess.check_output(['dmesg'], text=True)
    new = '\n'.join((line for line in after.splitlines() if line not in before.splitlines()))
    (root / 'dmesg-new.txt').write_text(new)
    if re.search('timed out|[Pp]age fault|DMA GUARD|Oops|BUG:', new):
        raise RuntimeError('kernel errors: ' + new)
    print('PASS', len(results), 'captures; no kernel faults', flush=True)
finally:
    guard.write_text(old_guard)
    (root / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
