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

def require(ok,message):
    if not ok:raise RuntimeError(message)

def run(args):subprocess.run(args,check=True,timeout=20)
def param(name):return (MODULE/'parameters'/name).read_text().strip()
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('start','stop'));args=parser.parse_args()
    if args.action=='start':
        if MODULE.exists():
            require(OWNED.exists(),'signal module is not owned by this service')
            require(param('ready')=='Y' and param('failed')=='N','signal owner failed; cold cycle required');return
        require(not OWNED.exists(),'signal initialization already attempted; inspect retained state')
        require(not DDC.exists() and not Path('/sys/module/h713_scp_probe').exists(),'competing signal helper')
        require(Path('/sys/module/h713_hdmi_audio/parameters/graph_ready').read_text().strip()=='Y','capture backend not ready')
        run(['insmod',str(BUNDLE/'h713-ddc-pins.ko'),'run=1'])
        OWNED.parent.mkdir(mode=0o700,exist_ok=True);OWNED.write_text('DDC acquired by signal service\n');OWNED.chmod(0o600)
        run(['insmod',str(BUNDLE/'h713-hdmi-signal.ko'),'armed=1'])
        require(param('ready')=='Y' and param('failed')=='N','signal setup failed; holds retained, cold cycle required')
        print('EDID/HPD ready; receiver client and DDC pins retained',flush=True)
    else:
        if not MODULE.exists() and not DDC.exists():return
        require(OWNED.exists(),'signal resources not owned by this service; refusing removal')
        if MODULE.exists():
            require(PCM.read_text().strip()=='closed','capture is open; signal retained')
            require(param('failed')=='N','signal owner failed; holds retained, cold cycle required')
            (MODULE/'parameters/stop').write_text('1\n')
            require(param('restored')=='Y' and param('ready')=='N' and param('failed')=='N','signal restoration incomplete')
            run(['rmmod','h713_hdmi_signal'])
        require(not MODULE.exists(),'signal still owns SCP; DDC retained')
        if DDC.exists():run(['rmmod','h713_ddc_pins'])
        OWNED.unlink()
        print('EDID/HPD, SCP SRAM/vectors and DDC ownership restored',flush=True)

if __name__=='__main__':
    try:main()
    except Exception as error:sys.exit(str(error))
