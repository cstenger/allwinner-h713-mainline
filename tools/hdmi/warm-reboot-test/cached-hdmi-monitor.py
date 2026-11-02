#!/usr/bin/env python3
"""Observe cached DRM attributes only; no DRM devices, ioctls or detect writes."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import signal
import sys
import threading
import time

CONNECTOR=Path('/sys/class/drm/card1-HDMI-A-1')
CARD=Path('/sys/class/drm/card1')
PCI=Path('/sys/bus/pci/devices/0000:0c:00.0')


def limited(path,limit):
    with path.open('rb') as f:data=f.read(limit+1)
    if len(data)>limit:raise RuntimeError('oversized cached attribute: '+str(path))
    return data


def sample():
    if CARD.joinpath('device').resolve()!=PCI.resolve():raise RuntimeError('DRM PCI mapping changed')
    if CONNECTOR.joinpath('device').resolve()!=CARD.resolve():raise RuntimeError('connector mapping changed')
    if limited(PCI/'vendor',32).strip()!=b'0x10de':raise RuntimeError('unexpected PCI vendor')
    status=limited(CONNECTOR/'status',64).decode().strip()
    enabled=limited(CONNECTOR/'enabled',64).decode().strip()
    edid=limited(CONNECTOR/'edid',4096)
    if status not in ('connected','disconnected','unknown') or enabled not in ('enabled','disabled'):
        raise RuntimeError('invalid cached state')
    return {'status':status,'enabled':enabled,'edid_bytes':len(edid),
            'edid_sha256':hashlib.sha256(edid).hexdigest(),'edid_hex':edid.hex()}


def main():
    output=Path(sys.argv[1]);output.mkdir(exist_ok=False)
    stop=threading.Event()
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,lambda *_:stop.set())
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    previous=None;last_log=0;count=0
    with (output/'events.jsonl').open('x',buffering=1) as log:
        def publish(phase,value):
            event={'host_utc':datetime.now(timezone.utc).isoformat(),'host_monotonic_ns':time.monotonic_ns(),
                'host_boot_id':boot,'phase':phase,'samples':count,'connector':str(CONNECTOR),
                'mode':'cached sysfs reads only; no probe/ioctl','snapshot':value}
            log.write(json.dumps(event,sort_keys=True)+'\n')
            temporary=output/'latest.json.tmp';temporary.write_text(json.dumps(event,sort_keys=True,indent=2)+'\n')
            temporary.replace(output/'latest.json')
        while not stop.is_set():
            count+=1
            try:value={'ok':True,**sample()}
            except (OSError,RuntimeError,UnicodeError) as error:value={'ok':False,'error':str(error)}
            now=time.monotonic_ns()
            if value!=previous or now-last_log>=5_000_000_000:
                publish('initial' if previous is None else ('change' if value!=previous else 'heartbeat'),value)
                if previous is None:print('Cached HDMI monitor ready' if value['ok'] else 'Cached HDMI monitor initial read failed',flush=True)
                previous=value;last_log=now
            stop.wait(.25)
        publish('stop',previous)


if __name__=='__main__':main()
