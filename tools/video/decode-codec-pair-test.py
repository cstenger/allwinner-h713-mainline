#!/usr/bin/env python3
"""Concurrent cedrus codec-pair test (well0nez 0298 scenario). Runs on the target.

Decodes pinned vectors through stock GStreamer v4l2sl decoders, hashing NV12
output from a pipe, and scores each stream against the manifest's software
reference. Phases: single-stream controls, a same-codec concurrency control,
the VP9+H.265 pairs under test, then single-stream recovery checks.
"""
import hashlib
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

# usage: decode-codec-pair-test.py OUT_DIR [ROUNDS] [VECTOR_DIR]
# VECTOR_DIR holds the pinned vectors and their manifest.json (file,
# input_sha256, raw_sha256, raw_bytes, frames), as staged for the 2026-11-14
# kernel follow-ups.
VEC = Path(sys.argv[3]) if len(sys.argv) > 3 else Path('/root/kernel-followups-20261114/vectors')
OUT = Path(sys.argv[1])
ROUNDS = int(sys.argv[2]) if len(sys.argv) > 2 else 2
MANIFEST = {row['file']: row for row in json.loads((VEC / 'manifest.json').read_text())}


def pipeline(name):
    p = VEC / name
    args = ['gst-launch-1.0', '-q', 'filesrc', 'location=' + str(p), '!']
    if p.suffix == '.webm':
        args += ['matroskademux', '!', 'vp9parse', '!', 'v4l2slvp9dec', '!']
    else:
        if p.suffix == '.mp4':
            args += ['qtdemux', '!']
        args += ['h265parse', '!', 'v4l2slh265dec', '!']
    return args + ['video/x-raw,format=NV12', '!', 'fdsink', 'fd=1']


def ve_irq():
    for line in Path('/proc/interrupts').read_text().splitlines():
        if 'video-codec' in line:
            return sum(int(n) for n in line.split()[1:5])
    raise RuntimeError('no VE interrupt line')


def decode(name, result):
    row = MANIFEST[name]
    h = hashlib.sha256()
    size = 0
    start = time.monotonic()
    proc = subprocess.Popen(pipeline(name), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    while chunk := proc.stdout.read(1 << 20):
        h.update(chunk)
        size += len(chunk)
    err = proc.stderr.read().decode(errors='replace')[-400:]
    rc = proc.wait(timeout=180)
    got = h.hexdigest() if size else None
    result.update(file=name, rc=rc, bytes=size, expected_bytes=row['raw_bytes'],
                  exact=(size == row['raw_bytes'] and got == row['raw_sha256']),
                  seconds=round(time.monotonic() - start, 2), stderr_tail=err.strip())


def kernel_lines(since):
    out = subprocess.run(['journalctl', '-k', '-o', 'cat', '--no-pager', '--since', since],
                         capture_output=True, text=True).stdout
    keys = ('cedrus', 'Failed to setup', 'timed out', 'Page fault', 'iommu')
    return [l for l in out.splitlines() if any(k in l for k in keys)]


def run(label, names, results):
    since = time.strftime('%Y-%m-%d %H:%M:%S')
    time.sleep(1.1)
    irq0 = ve_irq()
    rows = [{} for _ in names]
    threads = [threading.Thread(target=decode, args=(n, r)) for n, r in zip(names, rows)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    record = dict(phase=label, streams=rows, ve_irq=ve_irq() - irq0,
                  expected_frames=sum(MANIFEST[n]['frames'] for n in names),
                  kernel=kernel_lines(since)[-12:])
    record['all_exact'] = all(r['exact'] for r in rows)
    results.append(record)
    (OUT / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    summary = ' '.join('%s=%s' % (r['file'], 'EXACT' if r['exact'] else 'WRONG(%d/%d B rc%d)' % (r['bytes'], r['expected_bytes'], r['rc'])) for r in rows)
    print(json.dumps({'phase': label, 've_irq': record['ve_irq'], 'kernel_lines': len(record['kernel'])}), summary, flush=True)
    return record


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    for name, row in MANIFEST.items():
        h = hashlib.sha256((VEC / name).read_bytes()).hexdigest()
        assert h == row['input_sha256'], name
    print(json.dumps({'boot': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                      'cedrus_ko': hashlib.sha256(Path(subprocess.check_output(['modinfo', '-n', 'sunxi_cedrus'], text=True).strip()).read_bytes()).hexdigest()}), flush=True)
    results = []
    run('control-vp9', ['native-vp9.webm'], results)
    run('control-hevc', ['native-hevc.mp4'], results)
    run('control-hevc+hevc', ['native-hevc.mp4', 'h01-640x480-main.h265'], results)
    for r in range(ROUNDS):
        run('pair-vp9+hevc-%d' % r, ['native-vp9.webm', 'native-hevc.mp4'], results)
        run('pair-vp9short+hevc-%d' % r, ['vp9-short-gop.webm', 'h01-640x480-main.h265'], results)
    run('recovery-hevc', ['native-hevc.mp4'], results)
    run('recovery-vp9', ['native-vp9.webm'], results)
    print('DONE', json.dumps({p['phase']: p['all_exact'] for p in results}), flush=True)


if __name__ == '__main__':
    main()
