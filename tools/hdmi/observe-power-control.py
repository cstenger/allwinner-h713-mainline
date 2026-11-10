#!/usr/bin/env python3
"""Target-side cold-boot qualification of the read-only V4L2 power control.

Never stream, change firmware, or request HPD. The single S_CTRL negative test
must be rejected by the framework's already-verified READ_ONLY flag.
"""
import argparse
import errno
import fcntl
import json
import os
from pathlib import Path
import select
import struct
import time

POWER = 0xA00964
QUERY, GET, SET, SUB, DEQUEUE = 0xC0445624, 0xC008561B, 0xC008561C, 0x4020565A, 0x80885659


def emit(kind, **data):
    print(json.dumps(dict(kind=kind, monotonic=time.monotonic(), **data)), flush=True)


def sample(fd):
    q = bytearray(struct.pack('=II32siiiiIII', POWER, 0, b'', 0, 0, 0, 0, 0, 0, 0))
    fcntl.ioctl(fd, QUERY, q, True)
    fields = struct.unpack('=II32siiiiIII', q)
    if fields[1] != 8 or fields[3:5] != (0, 1) or not fields[7] & 4:
        raise RuntimeError('power control type/range/read-only contract failed')
    c = bytearray(struct.pack('=Ii', POWER, 0))
    fcntl.ioctl(fd, GET, c, True)
    return dict(value=struct.unpack('=Ii', c)[1], flags=fields[7],
                available=not bool(fields[7] & 17), name=fields[2].rstrip(b'\0').decode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=float, default=600)
    args = parser.parse_args()
    if not 0 <= args.seconds <= 1800:
        raise ValueError('duration outside 0..1800 seconds')
    deadline = time.monotonic() + 45
    while not Path('/dev/h713-hdmi-in').exists():
        if time.monotonic() >= deadline:
            raise RuntimeError('video node did not appear')
        time.sleep(.1)
    version = Path('/sys/module/h713_hdmi_v4l2/version').read_text().strip()
    if version != 'reject-trace-power-v2':
        raise RuntimeError('wrong loaded module: ' + version)
    fd = os.open('/dev/h713-hdmi-in', os.O_RDONLY | os.O_NONBLOCK)
    try:
        emit('identity', boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(), version=version,
             build_note=Path('/sys/module/h713_hdmi_v4l2/notes/.note.gnu.build-id').read_bytes().hex())
        fcntl.ioctl(fd, SUB, struct.pack('=8I', 3, POWER, 1, 0, 0, 0, 0, 0))
        fcntl.ioctl(fd, SUB, struct.pack('=8I', 5, 0, 0, 0, 0, 0, 0, 0))
        initial = sample(fd)
        emit('initial', **initial)
        try:
            fcntl.ioctl(fd, SET, struct.pack('=Ii', POWER, 1 - initial['value']))
        except OSError as error:
            if error.errno != errno.EACCES:
                raise
            emit('write_rejected', errno=error.errno)
        else:
            raise RuntimeError('read-only write unexpectedly accepted')
        end, heartbeat, previous = time.monotonic() + args.seconds, 0, None
        while time.monotonic() < end:
            select.select([], [], [fd], min(1, max(0, end - time.monotonic())))
            for _ in range(32):
                event = bytearray(136)
                try:
                    fcntl.ioctl(fd, DEQUEUE, event, True)
                except OSError as error:
                    if error.errno in (errno.EAGAIN, errno.ENOENT):
                        break
                    raise
                kind = struct.unpack_from('=I', event)[0]
                emit('event', type=kind, id=struct.unpack_from('=I', event, 96)[0],
                     changes=struct.unpack_from('=I', event, 8)[0],
                     value=struct.unpack_from('=i', event, 16)[0] if kind == 3 else None,
                     flags=struct.unpack_from('=I', event, 24)[0] if kind == 3 else None,
                     sequence=struct.unpack_from('=I', event, 76)[0])
            current, now = sample(fd), time.monotonic()
            if current != previous or now - heartbeat >= 5:
                emit('sample', **current)
                previous, heartbeat = current, now
        emit('complete', **sample(fd))
    finally:
        os.close(fd)


if __name__ == '__main__':
    main()
