#!/usr/bin/env python3
"""Own DDC pins and the persistent, reversible SCP EDID/HPD module."""
import argparse
import errno
import os
import signal
import subprocess
import time
from pathlib import Path
import sys
BUNDLE=Path('/usr/lib/h713-hdmi')
MODULE=Path('/sys/module/h713_hdmi_signal')
DDC=Path('/sys/module/h713_ddc_pins')
CARD=Path('/proc/asound/H713HDMI')
SND=Path('/dev/snd')
PROC=Path('/proc')
# Bench-only, runtime-only: keeps capture consumers alive at shutdown so a
# busy PCM still makes the stop fail (H2 failure injection).
NO_RECLAIM=Path('/run/h713-hdmi-signal/no-reclaim')
OWNED=Path('/run/h713-hdmi-signal/owned')
# Per-boot latch: written before any hold, removed only by a complete stop.
ATTEMPTED=Path('/run/h713-hdmi-signal/attempted')
PROBE=Path('/sys/module/h713_scp_probe')
GRAPH=Path('/sys/module/h713_hdmi_audio/parameters/graph_ready')

def require(ok,message):
    if not ok:raise RuntimeError(message)

def run(args):subprocess.run(args,check=True,timeout=20)
def param(name):return (MODULE/'parameters'/name).read_text().strip()
def mark(path,text):path.parent.mkdir(mode=0o700,exist_ok=True);path.write_text(text);path.chmod(0o600)
def release_ddc():
    # The helper restores and verifies the pin mux in a fallible release
    # and stays pinned until it succeeds. Helpers from before that change
    # have no release parameter and restore in their module exit.
    release=DDC/'parameters/release'
    if release.exists():
        try:release.write_text('1\n')
        except OSError as error:raise RuntimeError(f'DDC pin restore failed ({error.strerror}); DDC retained, cold cycle required') from error
    run(['rmmod','h713_ddc_pins'])
def capture_device():
    # The single capture substream; None when the audio card is absent.
    if not CARD.exists():return None
    return SND/f'pcmC{CARD.resolve().name.removeprefix("card")}D0c'
def open_capture(dev):return os.open(dev,os.O_RDONLY|os.O_NONBLOCK|os.O_CLOEXEC)
def close_capture(fd):os.close(fd)
def holders(dev):
    pids=[]
    for fds in PROC.glob('[0-9]*/fd'):
        try:
            if any(os.readlink(fd)==str(dev) for fd in fds.iterdir()):pids.append(int(fds.parent.name))
        except OSError:pass # exited or not ours to read
    return sorted(set(pids)-{os.getpid()})
def kill(pid,sig):
    try:os.kill(pid,sig)
    except ProcessLookupError:pass
def shutting_down():
    state=subprocess.run(['systemctl','is-system-running'],capture_output=True,text=True,timeout=5).stdout.strip()
    return state=='stopping'
def reclaim(dev):
    # User-session consumers (PipeWire for WirePlumber's default source,
    # pw-record, ...) outlive this unit at shutdown: the backend is ordered
    # after user@1000 on purpose. systemd would kill them moments later;
    # do it now, and only during shutdown. A running system keeps refusing.
    if dev is None or NO_RECLAIM.exists() or not shutting_down():return
    pids=holders(dev)
    if not pids:return
    print(f'shutdown: closing HDMI capture consumers {pids}',flush=True)
    for sig,grace in ((signal.SIGTERM,5),(signal.SIGKILL,2)):
        for pid in pids:kill(pid,sig)
        deadline=time.monotonic()+grace
        while (pids:=holders(dev)) and time.monotonic()<deadline:time.sleep(0.1)
        if not pids:return
def hold_capture(dev):
    # Owning the only substream for the whole restoration closes the gap
    # between "nobody is capturing" and the stop: any other open now fails
    # (or, if blocking, waits until the source is already gone).
    if dev is None:return None
    try:return open_capture(dev)
    except OSError as error:
        if error.errno==errno.EBUSY:raise RuntimeError('capture is open; signal retained') from None
        if error.errno==errno.EAGAIN:return None # graph not ready: nobody can open it
        raise RuntimeError(f'capture device check failed ({error.strerror}); signal retained') from error
def launch(bundle):
    try:run(['insmod',str(bundle/'h713-hdmi-signal.ko'),'armed=1'])
    except subprocess.CalledProcessError:
        # Present means init returned 0 with failed=Y (holds kept) or never
        # finished: keep everything. Absent means the module verified its
        # SRAM restore and released all it took before SCP release, so DDC
        # is the only hold left; drop it so the backend can still park.
        require(not MODULE.exists(),'signal init failed with the module loaded; holds retained, cold cycle required')
        try:release_ddc()
        except Exception as error:raise RuntimeError('signal init refused before SCP release, and DDC release failed; DDC retained, cold cycle required') from error
        OWNED.unlink()
        raise RuntimeError('signal init refused before SCP release; nothing retained, retry needs a cold cycle') from None
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('start','stop'))
    parser.add_argument('--bundle',type=Path,default=BUNDLE,help='module directory (bench runs stage a candidate here)');args=parser.parse_args()
    if args.action=='start':
        if MODULE.exists():
            require(OWNED.exists(),'signal module is not owned by this service')
            require(param('ready')=='Y' and param('failed')=='N','signal owner failed; cold cycle required');return
        require(not ATTEMPTED.exists() and not OWNED.exists(),'signal initialization already attempted on this boot; cold cycle required')
        require(not DDC.exists() and not PROBE.exists(),'competing signal helper')
        require(GRAPH.read_text().strip()=='Y','capture backend not ready')
        mark(ATTEMPTED,'signal initialization attempted on this boot\n')
        run(['insmod',str(args.bundle/'h713-ddc-pins.ko'),'run=1'])
        mark(OWNED,'DDC acquired by signal service\n')
        launch(args.bundle)
        require(param('ready')=='Y' and param('failed')=='N','signal setup failed; holds retained, cold cycle required')
        print('EDID/HPD ready; receiver client and DDC pins retained',flush=True)
    else:
        if not MODULE.exists() and not DDC.exists():return
        require(OWNED.exists(),'signal resources not owned by this service; refusing removal')
        if MODULE.exists():
            require(param('failed')=='N','signal owner failed; holds retained, cold cycle required')
            dev=capture_device()
            reclaim(dev)
            held=hold_capture(dev)
            try:
                # The module marks a failed stop terminal and keeps every hold; keep DDC too.
                try:(MODULE/'parameters/stop').write_text('1\n')
                except OSError as error:raise RuntimeError(f'signal stop refused ({error.strerror}); holds retained, cold cycle required') from error
                require(param('restored')=='Y' and param('ready')=='N' and param('failed')=='N','signal restoration incomplete')
            finally:
                if held is not None:close_capture(held)
            run(['rmmod','h713_hdmi_signal'])
        require(not MODULE.exists(),'signal still owns SCP; DDC retained')
        if DDC.exists():release_ddc()
        OWNED.unlink();ATTEMPTED.unlink(missing_ok=True)
        print('EDID/HPD, SCP SRAM/vectors and DDC ownership restored',flush=True)

if __name__=='__main__':
    try:main()
    except Exception as error:sys.exit(str(error))
