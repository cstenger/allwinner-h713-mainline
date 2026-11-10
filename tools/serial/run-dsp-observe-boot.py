#!/usr/bin/env python3
"""Execute a prepared cold-only RAM boot, stopping at the first failed step."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time
from console import open_port, write_slow, drain


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--prepared', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args=parser.parse_args()
    manifest=json.loads((args.prepared/'manifest.json').read_text())
    data=(args.prepared/'commands.json').read_bytes()
    if hashlib.sha256(data).hexdigest()!=manifest['commands_sha256']:raise RuntimeError('Boot commands changed')
    commands=json.loads(data)
    args.output.mkdir(parents=True,exist_ok=False)
    fd=open_port(args.port)
    try:
        with (args.output/'serial.log').open('xb',buffering=0) as raw:
            write_slow(fd,b'\n');initial=drain(fd,1,echo=False);raw.write(initial)
            if not re.search(rb'=>\s*$',initial):raise RuntimeError('Not at U-Boot prompt')
            for i,command in enumerate(commands):
                if i==len(commands)-1:
                    if command!='bootm 0x50000000 - 0x4f000000':raise RuntimeError('Unexpected final boot command')
                    line=command
                else:line=f'if {command}; then echo DSP_STEP_{i}_OK; else echo DSP_STEP_{i}_FAIL; fi'
                if len(line)>900:raise RuntimeError('Console command too long')
                write_slow(fd,(line+'\n').encode());time.sleep(.2)
                output=drain(fd,5 if i==len(commands)-1 else 1,echo=False);raw.write(output)
                if i<len(commands)-1 and not re.search(rb'(?m)^DSP_STEP_'+str(i).encode()+rb'_OK\r?$',output):
                    raise RuntimeError(f'Boot step {i} failed or response missing; no further command')
    finally:os.close(fd)
    print('RAM boot sequence sent; Linux health/boot ID still require verification.')


if __name__=='__main__':main()
