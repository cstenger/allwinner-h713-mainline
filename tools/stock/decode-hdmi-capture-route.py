#!/usr/bin/env python3
"""Host-only stock HAL route selection; no board access.

Runs create_audio_patch for HDMI source 1, PCM format 0, speaker/A2DP sinks.
Intercepts Sound_Connect to record route selection and terminal unmute/effect
setup to avoid pretending configuration-file/hardware stubs form a full HAL.
"""
import argparse,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'re'))
from awemu import Lib,RET
from unicorn.arm_const import UC_ARM_REG_PC
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('hal',type=Path);args=ap.parse_args()
b=args.hal.read_bytes();digest=hashlib.sha256(b).hexdigest()
results=[]
for sink,name in [(1,'speaker'),(3,'A2DP')]:
 lib=Lib(args.hal);device=lib.alloc(0x2000)
 lib.wr(device+0x7a0,sink);lib.wr(device+0x7a4,1);lib.wr(device+0x7dc,0)
 calls=[]
 lib.intercept('_Z13Sound_Connectm',lambda l,a:calls.append(a[0]) or 0)
 lib.intercept('_Z18Check_Sound_UnmuteP18sunxi_audio_device',lambda l,a:0)
 rc=lib.call('_Z18create_audio_patchP18sunxi_audio_deviceii',device,1,sink,max_insns=100000)
 assert rc==0 and lib.uc.reg_read(UC_ARM_REG_PC)==RET,(name,rc)
 assert calls==[0x89 if sink==1 else 0x8f],(name,calls)
 results.append({'source':1,'sink':sink,'sink_name':name,'hdmi_format':0,'Sound_Connect_routes':calls,'rc':rc})
print(json.dumps({'hal_sha256':digest,'method':'Offline HAL branch execution, Sound_Connect and terminal unmute intercepted; not live DSP word readback','results':results},indent=2))
