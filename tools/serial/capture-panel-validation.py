#!/usr/bin/env python3
"""Passively record a 115200-baud UART into a new directory, reconnecting on loss.

Never sends serial data. Ensure no other process is reading the same UART.
SIGINT/SIGTERM stop recording and close the descriptor and output files.
"""
import argparse
from datetime import datetime, timezone
import errno
import os
from pathlib import Path
import select
import signal
import sys
import termios
import threading


def record(port, output, stop):
    output.mkdir(parents=True, exist_ok=False)
    fd = None
    last_open_error = None
    with (output / 'serial.log').open('xb', buffering=0) as raw, \
            (output / 'serial-timestamped.log').open('x', buffering=1) as stamped:
        def note(message):
            stamped.write(datetime.now(timezone.utc).isoformat() + ' ' + message + '\n')

        note('CAPTURE START; passive recorder; timestamps are host UTC')
        try:
            while not stop.is_set():
                if fd is None:
                    try:
                        fd = os.open(port, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
                        attrs = termios.tcgetattr(fd)
                        attrs[0] = attrs[1] = attrs[3] = 0
                        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
                        attrs[4] = attrs[5] = termios.B115200
                        attrs[6][termios.VMIN] = 1
                        attrs[6][termios.VTIME] = 0
                        termios.tcsetattr(fd, termios.TCSANOW, attrs)
                    except (OSError, termios.error) as error:
                        if fd is not None:
                            os.close(fd)
                            fd = None
                        message = str(error)
                        if message != last_open_error:
                            note('OPEN FAILED ' + message)
                            last_open_error = message
                        stop.wait(.5)
                        continue
                    last_open_error = None
                    note(f'OPEN {port} 115200')
                    print(f'Serial capture ready on {port}', flush=True)
                try:
                    readable, _, _ = select.select([fd], [], [], 1)
                    if not readable:
                        continue
                    data = os.read(fd, 65536)
                    if not data:
                        raise OSError(errno.EIO, 'serial disconnected')
                except BlockingIOError:
                    continue
                except OSError as error:
                    note('DISCONNECTED ' + str(error))
                    os.close(fd)
                    fd = None
                    stop.wait(.5)
                    continue
                # Output failures must propagate; they are not UART disconnects.
                if raw.write(data) != len(data):
                    raise OSError(errno.EIO, 'short write to raw UART log')
                note(repr(data))
        finally:
            try:
                note('CAPTURE STOP')
            finally:
                if fd is not None:
                    os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True, help='UART device, e.g. /dev/ttyUSB0')
    parser.add_argument('--output', required=True, type=Path, help='new capture directory')
    args = parser.parse_args()
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    try:
        record(args.port, args.output, stop)
    except (OSError, termios.error) as error:
        print(f'Serial recording failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
