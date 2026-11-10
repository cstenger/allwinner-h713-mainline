#!/usr/bin/env python3
"""Record a fresh SPL boot and send exactly one autoboot-interrupt space.

Waits across UART disconnect/reconnect. Never types a command or resets the
board. Run before the operator applies power; the board is left at =>.
"""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import select
import signal
import time
import termios
from console import open_port


class Catch:
    def __init__(self):self.buffer = b''; self.spl = False; self.sent = False
    def feed(self, data):
        self.buffer = (self.buffer + data)[-8192:]
        if self.buffer.count(b'U-Boot SPL ') > 1:raise RuntimeError('Repeated boot; no retry')
        if b'U-Boot SPL ' in self.buffer:self.spl = True
        if b'H713 RESET v1 stage=pre_workspace' in self.buffer:
            raise RuntimeError('Logo initialization already started; no retry')
        if self.spl and not self.sent and b'Hit any key to stop autoboot:' in self.buffer:
            self.sent = True
            return 'space'
        if self.sent and b'=> ' in self.buffer:return 'done'
        return None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args=parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    stopped=False
    def stop(*unused):
        nonlocal stopped
        stopped=True
    for sig in (signal.SIGTERM, signal.SIGINT):signal.signal(sig, stop)
    state=Catch();fd=None
    with (args.output/'serial.log').open('xb', buffering=0) as raw, (args.output/'events.log').open('x', buffering=1) as events:
        def note(value):events.write(datetime.now(timezone.utc).isoformat()+' '+value+'\n')
        try:
            while not stopped:
                if fd is None:
                    try:fd=open_port(args.port);note('OPEN '+args.port)
                    except (OSError, termios.error):time.sleep(.5);continue
                try:
                    if not select.select([fd],[],[],1)[0]:continue
                    data=os.read(fd,65536)
                    if not data:raise OSError('UART disconnected')
                except BlockingIOError:continue
                except OSError:
                    os.close(fd);fd=None;note('DISCONNECTED')
                    if state.spl:raise RuntimeError('Lost UART during boot; no retry')
                    continue
                raw.write(data)
                action=state.feed(data)
                if action=='space':
                    if os.write(fd,b' ')!=1:raise RuntimeError('Short UART interrupt write')
                    note('SENT ONE AUTOBOOT INTERRUPT SPACE')
                elif action=='done':
                    note('PROMPT CAPTURED; no command sent');print('U-Boot prompt captured',flush=True);return
            raise RuntimeError('Stopped before prompt; do not assume autoboot was interrupted')
        finally:
            if fd is not None:os.close(fd)


if __name__=='__main__':main()
