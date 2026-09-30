#!/usr/bin/env python3
"""Check a decoder's output for an AV1 stream whose frame size changes
without a new sequence (spatial resize / reference scaling). RUNS ON THE HOST.

A V4L2 decoder keeps the sequence's maximum size as its buffer size and
writes each smaller frame into the top-left corner, so the capture is
fixed-size NV12 frames (WxH of the sequence), taken straight from the
decoder:

  target$ gst-launch-1.0 -q filesrc location=clip.ivf ! ivfparse ! av1parse ! \
          v4l2slav1dec ! filesink location=capture.nv12

(not through videoconvert: GStreamer 1.26 advertises the render size on the
caps and videoconvert then writes blank frames). The reference is libdav1d's
native output, each frame at its own size. Every frame's own region must
match exactly.

  usage: av1-resize-check.py clip.ivf capture.nv12 SEQ_W SEQ_H
"""
import json, subprocess, sys, tempfile, os

clip, cap, W, H = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
probe = json.loads(subprocess.check_output(
    ['ffprobe', '-v', 'error', '-c:v', 'libdav1d', '-select_streams', 'v:0',
     '-show_frames', '-show_entries', 'frame=width,height', '-of', 'json', clip]))
sizes = [(f['width'], f['height']) for f in probe['frames']]
with tempfile.TemporaryDirectory() as d:
    ref = os.path.join(d, 'ref.yuv')
    subprocess.check_call(['dav1d', '-q', '-i', clip, '-o', ref, '--muxer', 'yuv'])
    ref = open(ref, 'rb').read()
cap = open(cap, 'rb').read()
fs = W * H * 3 // 2
print(f'{len(sizes)} frames, sizes {sorted(set(sizes))}; capture holds {len(cap) / fs:g}')
pos = bad = 0
for i, (w, h) in enumerate(sizes):
    cw, ch = (w + 1) // 2, (h + 1) // 2
    f = cap[i * fs:(i + 1) * fs]
    if len(f) < fs:
        print(f'frame {i}: missing from the capture'); bad += 1; continue
    ok = True
    want = ref[pos:pos + w * h]; pos += w * h
    ok &= b''.join(f[r * W:r * W + w] for r in range(h)) == want
    for c in range(2):		# Cb then Cr, interleaved in the capture
        want = ref[pos:pos + cw * ch]; pos += cw * ch
        ok &= b''.join(f[W * H + r * W + c:W * H + r * W + 2 * cw:2] for r in range(ch)) == want
    print(f'frame {i}: {w}x{h} {"exact" if ok else "MISMATCH"}')
    bad += not ok
print('PASS' if not bad and pos == len(ref) else 'FAIL')
sys.exit(bool(bad))
