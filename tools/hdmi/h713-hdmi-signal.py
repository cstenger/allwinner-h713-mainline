#!/usr/bin/env python3
"""Own DDC pins and the persistent, reversible SCP EDID/HPD module."""
import argparse
import subprocess
from pathlib import Path
import sys
BUNDLE=Path('/usr/lib/h713-hdmi')
MODULE=Path('/sys/module/h713_hdmi_signal')
DDC=Path('/sys/module/h713_ddc_pins')
PCM=Path('/proc/asound/H713HDMI/pcm0c/sub0/status')
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
def launch(bundle):
    try:run(['insmod',str(bundle/'h713-hdmi-signal.ko'),'armed=1'])
    except subprocess.CalledProcessError:
        # Present means init returned 0 with failed=Y (holds kept) or never
        # finished: keep everything. Absent means the module verified its
        # SRAM restore and released all it took before SCP release, so DDC
        # is the only hold left; drop it so the backend can still park.
        require(not MODULE.exists(),'signal init failed with the module loaded; holds retained, cold cycle required')
        try:run(['rmmod','h713_ddc_pins'])
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
            require(PCM.read_text().strip()=='closed','capture is open; signal retained')
            require(param('failed')=='N','signal owner failed; holds retained, cold cycle required')
            # The module marks a failed stop terminal and keeps every hold; keep DDC too.
            try:(MODULE/'parameters/stop').write_text('1\n')
            except OSError as error:raise RuntimeError(f'signal stop refused ({error.strerror}); holds retained, cold cycle required') from error
            require(param('restored')=='Y' and param('ready')=='N' and param('failed')=='N','signal restoration incomplete')
            run(['rmmod','h713_hdmi_signal'])
        require(not MODULE.exists(),'signal still owns SCP; DDC retained')
        if DDC.exists():run(['rmmod','h713_ddc_pins'])
        OWNED.unlink();ATTEMPTED.unlink(missing_ok=True)
        print('EDID/HPD, SCP SRAM/vectors and DDC ownership restored',flush=True)

if __name__=='__main__':
    try:main()
    except Exception as error:sys.exit(str(error))
