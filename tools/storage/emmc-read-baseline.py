#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""DDR3 bench: direct, read-only eMMC reads with optional 4K decode/GPU load.

Run on the board. Raw data is opened O_RDONLY|O_DIRECT; temporary workload
logs live in tmpfs. No timing fault injection or block-device writes. The
controller is kept runtime-active for safe read-only MMIO sampling; its PM
policy and GPU profiling setting are restored in finally. Each round hashes
exactly 2 GiB of the unmounted vendor system partition mmcblk0p9.
"""
import argparse
import ctypes
import hashlib
import json
import mmap
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import threading
import time

DEVICE = '/dev/mmcblk0p9'
CID = '15010038475446345208604bbe691991'
CONTROLLER = Path('/sys/devices/platform/soc/4022000.mmc')
SIZE = 2 * 1024**3
CHUNK = 4 * 1024**2


def emit(**data):
    print(json.dumps(data), flush=True)


def irqs():
    result = {'ve': 0, 'gpu': 0}
    for line in Path('/proc/interrupts').read_text().splitlines():
        for key, pattern in [('ve', 'video-codec'), ('gpu', 'panfrost')]:
            if pattern in line:
                values = line.split(':', 1)[1].split()
                result[key] += sum(int(v) for v in values if v.isdecimal())
    return result


def pipeline(clip):
    return ['gst-launch-1.0', '-q', 'filesrc', 'location='+str(clip), '!',
            'qtdemux', '!', 'h264parse', '!', 'v4l2slh264dec', '!',
            'video/x-raw,format=NV12', '!', 'fakesink', 'sync=true']


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', choices=['idle', 'mixed'], required=True)
    p.add_argument('--rounds', type=int, default=3)
    p.add_argument('--expected-sha256', default='336a55d66d0dbdad6c2f05c75bdf8b6945a4d91133190755d3419329a5ac1c2d',
                   help='digest of the pinned unmounted 2 GiB vendor partition')
    p.add_argument('--clip', type=Path, default=Path('/tmp/emmc-load-2160.mp4'))
    a = p.parse_args()
    def interrupted(signum, frame): raise SystemExit(128+signum)
    for signum in (signal.SIGTERM, signal.SIGHUP): signal.signal(signum, interrupted)
    assert 1 <= a.rounds <= 10
    assert Path('/proc/device-tree/model').read_bytes() == b'HY200 QZ713DF_A1 (Allwinner H713)\0'
    assert Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == CID
    assert (Path('/sys/class/mmc_host/mmc0/device').resolve() == CONTROLLER)
    assert (CONTROLLER/'of_node/compatible').read_bytes().split(b'\0')[0] == b'allwinner,sun50i-h713-emmc'
    assert Path('/sys/class/block/mmcblk0p9/start').read_text().strip() == '599040'
    assert int(Path('/sys/class/block/mmcblk0p9/size').read_text())*512 == SIZE
    assert all(DEVICE not in line for line in Path('/proc/mounts').read_text().splitlines())
    assert 'mmc HS400' in Path('/sys/kernel/debug/mmc0/ios').read_text()
    assert subprocess.check_output(['systemctl', 'is-system-running'], text=True).strip() == 'running'
    if a.mode == 'mixed':
        assert a.clip.is_file() and str(a.clip).startswith('/tmp/')
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    pm = CONTROLLER/'power/control'
    profiling = Path('/sys/bus/platform/devices/1800000.gpu/profiling')
    old_pm, old_profile = pm.read_text(), profiling.read_text()
    load = None
    gpu = None
    stop = threading.Event()
    samples = []
    errors = []
    last_progress = [time.monotonic()]
    # Read-only device mappings, aligned single-word accesses only.
    memfd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
    sampler = None
    log = tempfile.TemporaryFile(dir='/tmp')
    start_uptime = float(Path('/proc/uptime').read_text().split()[0])
    try:
        pm.write_text('on\n')
        assert (CONTROLLER/'power/runtime_status').read_text().strip() == 'active'
        profiling.write_text('1\n')
        # Map read-only through libc so ctypes can issue aligned word loads;
        # never use mmap slicing/memcpy over Device memory.
        libc = ctypes.CDLL(None, use_errno=True)
        libc.mmap.restype = ctypes.c_void_p
        libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_long]
        address = libc.mmap(None, 4096, mmap.PROT_READ, mmap.MAP_SHARED, memfd, 0x04022000)
        assert address != ctypes.c_void_p(-1).value
        def word(offset): return ctypes.c_uint32.from_address(address+offset).value
        def observe():
            last_report = time.monotonic()
            while not stop.is_set():
                try:
                    samples.append((word(0x3c), word(0x100)))
                    now = time.monotonic()
                    if now-last_report >= 10:
                        emit(phase='progress', mode=a.mode, samples=len(samples),
                             status=hex(samples[-1][0]), threshold=hex(samples[-1][1]),
                             seconds_since_read=now-last_progress[0])
                        last_report=now
                    if now-last_progress[0] > 15:
                        errors.append('direct read made no progress for 15 seconds')
                        for child in (load, gpu):
                            if child is not None and child.poll() is None: child.terminate()
                        emit(phase='stalled', errors=errors, status=hex(samples[-1][0]),
                             threshold=hex(samples[-1][1]))
                        stop.set()
                        break
                    stop.wait(0.001)
                except BaseException as e:
                    errors.append(str(e)); break
        sampler = threading.Thread(target=observe)
        sampler.start()
        if a.mode == 'mixed':
            env = dict(os.environ)
            gpu = subprocess.Popen(['python3', '-u', '/tmp/emmc-gpu-load.py', '--seconds', '600'], stdout=log, stderr=log)
            load = subprocess.Popen(pipeline(a.clip), env=env, stdout=log, stderr=log)
            time.sleep(3)
            assert load.poll() is None, 'decode load exited before reads'
            assert gpu.poll() is None, 'GPU load exited before reads'
        emit(phase='start', mode=a.mode, boot_id=boot, cid=CID,
             device=DEVICE, bytes_per_round=SIZE, pm_before=old_pm.strip(),
             ios=Path('/sys/kernel/debug/mmc0/ios').read_text())
        expected = a.expected_sha256
        for round_no in range(a.rounds):
            if load is not None and load.poll() is not None:
                assert load.returncode == 0, 'decode/GPU load failed'
                load = subprocess.Popen(pipeline(a.clip), env=env, stdout=log, stderr=log)
            irq0 = irqs(); first = len(samples)
            fd = os.open(DEVICE, os.O_RDONLY | os.O_DIRECT | os.O_CLOEXEC)
            digest = hashlib.sha256()
            temperatures = []
            started = time.monotonic()
            try:
                with mmap.mmap(-1, CHUNK) as buf:
                    remaining = SIZE
                    while remaining:
                        n = os.readv(fd, [buf])
                        assert n == CHUNK, f'short direct read: {n}'
                        last_progress[0] = time.monotonic()
                        digest.update(buf)
                        remaining -= n
                        if remaining % (64*1024**2) == 0:
                            temperatures.append(int(Path('/sys/class/thermal/thermal_zone0/temp').read_text()))
                            assert temperatures[-1] < 80000, 'temperature limit'
                        if gpu is not None: assert gpu.poll() is None, 'GPU load failed'
                        if load is not None and load.poll() is not None:
                            assert load.returncode == 0, 'decode/GPU load failed'
                            load = subprocess.Popen(pipeline(a.clip), env=env, stdout=log, stderr=log)
            finally:
                os.close(fd)
            elapsed = time.monotonic()-started
            assert not errors, errors
            observed = samples[first:]
            irq1 = irqs(); delta = {k:irq1[k]-irq0[k] for k in irq0}
            if a.mode == 'mixed': assert delta['ve'] > 0 and delta['gpu'] > 0, delta
            value = digest.hexdigest()
            assert value == expected, 'read digest changed'
            emit(phase='round', mode=a.mode, round=round_no+1, seconds=elapsed,
                 mib_per_second=SIZE/1024**2/elapsed, sha256=value, irq_delta=delta,
                 samples=len(observed), fifo_full=sum(bool(s&8) for s,t in observed),
                 thresholds={hex(t):sum(v==t for s,v in observed) for t in set(t for s,t in observed)},
                 max_temp_millic=max(temperatures))
        assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == boot
    finally:
        if gpu is not None and gpu.poll() is None:
            gpu.terminate()
            try: gpu.wait(timeout=8)
            except subprocess.TimeoutExpired: gpu.kill(); gpu.wait()
        if load is not None and load.poll() is None:
            load.terminate()
            try: load.wait(timeout=8)
            except subprocess.TimeoutExpired: load.kill(); load.wait()
        stop.set()
        if sampler is not None: sampler.join(timeout=5)
        if 'address' in locals() and address != ctypes.c_void_p(-1).value:
            libc.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
            libc.munmap(address, 4096)
        os.close(memfd)
        profiling.write_text(old_profile)
        pm.write_text(old_pm)
        log.seek(0)
        emit(phase='cleanup', pm_restored=pm.read_text().strip(),
             workload_log=log.read().decode(errors='replace'))
        log.close()
    kernel = subprocess.check_output(['dmesg'], text=True)
    new_lines = [line for line in kernel.splitlines()
                 if (m := re.match(r'\[\s*(\d+\.\d+)\]', line)) and float(m[1]) >= start_uptime]
    bad = [line for line in new_lines if re.search(r'mmc.*(?:error|timeout|CRC)|IOMMU.*fault|BUG:|WARNING:|Oops', line, re.I)]
    emit(phase='final', mode=a.mode, kernel_errors=bad, sha256=expected)
    assert not bad, bad


if __name__ == '__main__':
    main()
