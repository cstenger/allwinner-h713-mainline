#!/usr/bin/env python3
"""NVIDIA 615.78.08 cached RM snapshot. Default offline; live requires explicit flag."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import time
from protocol import Snapshot,VERSION,need

ROOT=Path(__file__).resolve().parent

def sha(data):return hashlib.sha256(data).hexdigest()

def sealed():
    names=set()
    for line in (ROOT/'SHA256SUMS').read_text().splitlines():
        digest,name=line.split('  ',1);p=Path(name)
        need(not p.is_absolute() and '..' not in p.parts and name not in names,'invalid ledger path')
        need(not (ROOT/p).is_symlink() and sha((ROOT/p).read_bytes())==digest,'checksum mismatch: '+name)
        names.add(name)
    need({'reader.py','protocol.py','transport.py','abi.json','LIVE-GATE.json'}<=names,'incomplete package')
    gate=json.loads((ROOT/'LIVE-GATE.json').read_text())
    need(gate['prepared_for_one_explicit_snapshot'] is True and gate['board_preservation_required'] is False,'snapshot gate policy')
    need(gate['qualification_basis']=='version-matched supported API contract plus open host lifecycle audit','qualification basis changed')
    from transport import verify_abi
    verify_abi(json.loads((ROOT/'abi.json').read_text()))
    return gate


def baseline(root=Path('/')):
    def read(name,limit=4096):
        with (root/name).open('rb') as f:data=f.read(limit+1)
        need(len(data)<=limit,'oversized attribute: '+name)
        return data
    version=read('sys/module/nvidia/version').decode().strip()
    need(version==VERSION,'wrong NVIDIA version')
    boot=read('proc/sys/kernel/random/boot_id').decode().strip()
    # Pin the intended BDF through sysfs, not a guessed /dev/nvidia minor.
    device=root/'sys/bus/pci/devices/0000:0c:00.0'
    need((device/'vendor').read_text().strip()=='0x10de','wrong PCI vendor')
    need((device/'driver/module/version').read_text().strip()==VERSION,'PCI driver version changed')
    card=root/'sys/class/drm/card1'
    need((card/'device').resolve()==device.resolve(),'DRM card PCI mapping changed')
    connectors={}
    for p in sorted((root/'sys/class/drm').glob('card1-*')):
        if not (p/'status').exists():continue
        state=(p/'status').read_text().strip();enabled=(p/'enabled').read_text().strip()
        with (p/'edid').open('rb') as f:edid=f.read(4097)
        need(len(edid)<=4096 and state in ('connected','disconnected','unknown') and enabled in ('enabled','disabled'),'invalid cached DRM state')
        need((p/'device').resolve()==card.resolve(),'connector DRM card mapping changed')
        connectors[p.name]=dict(status=state,enabled=enabled,edid_bytes=len(edid),edid_sha256=sha(edid))
    need('card1-HDMI-A-1' in connectors,'HDMI connector missing')
    need(any(v['status']=='connected' and v['enabled']=='enabled' for k,v in connectors.items() if '-DP-' in k),
         'require an active host desktop display; no GPU attach/initialization fallback')
    return dict(version=version,boot_id=boot,pci='0000:0c:00.0',connectors=connectors)


def save(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def execute(output):
    gate=sealed();before=baseline()
    need(before['boot_id']==gate['host_boot_id'],'host boot changed; reprepare identity')
    os.umask(0o077);output.mkdir(mode=0o700,parents=True,exist_ok=False)
    save(output/'before.json',before)
    save(output/'INTENT.json',dict(snapshot_requests=1,board_access=False,cache_flags='0x31',
         control_node_only=True,firmware_contract=True,no_retries=True,no_reset=True,host_boot_id=before['boot_id']))
    from transport import open_control
    with (output/'events.jsonl').open('x') as log:
        def record(event):
            event['monotonic']=time.monotonic();log.write(json.dumps(event)+'\n');log.flush();os.fsync(log.fileno())
        # Signals raise rather than returning, preventing Python's EINTR retry.
        def deadline(signum,frame):raise TimeoutError('snapshot deadline; no reset or retry')
        previous=signal.signal(signal.SIGALRM,deadline)
        signal.alarm(30)
        session=None
        try:
            session=Snapshot(open_control(),record=record)
            result=session.run()
            signal.alarm(0)
            after=baseline();save(output/'after.json',after)
            need(after['boot_id']==before['boot_id'],'host boot changed during snapshot')
            result['drm_before']=before;result['drm_after']=after
            result['drm_cache_unchanged']=before==after
            result['hardware_executed']=True
            result['meaning']='RM/DRM caches and static connector metadata; no electrical HPD or fresh DDC measurement'
            save(output/'RESULT.json',result)
            return result
        except BaseException as exc:
            signal.alarm(0)
            save(output/'FAILURE.json',dict(error=str(exc),snapshot_complete=False,
                  cleanup_error=session.cleanup_error if session else None,
                  no_reset=True,no_retry=True,do_not_automatically_repeat=True))
            raise
        finally:
            signal.alarm(0);signal.signal(signal.SIGALRM,previous)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute-approved',action='store_true');p.add_argument('--output',type=Path)
    a=p.parse_args()
    if not a.execute_approved:
        print(json.dumps(dict(mode='OFFLINE PLAN ONLY',hardware_executed=False,board_access=False,
              control_node='/dev/nvidiactl',open_gpu_nodes=False,cached_flags='0x31',
              firmware_contract='supported cached/query semantics; no firmware-free guarantee'),indent=2));return
    need(a.output is not None,'new private output directory required')
    print(json.dumps(execute(a.output),indent=2))

if __name__=='__main__':main()
