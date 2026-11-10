#!/usr/bin/env python3
"""Offline source/ABI audit. No NVIDIA, DRM or target-board operations."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def require(ok,message):
    if not ok:raise ValueError(message)


def audit(source,output):
    require(not output.exists(),'output already exists')
    require('615.78.08' in (source/'version.mk').read_text(),'wrong source version')
    output.mkdir(mode=0o700,parents=True)
    files={
      'dispatch':'src/nvidia/generated/g_disp_objs_nvoc.c',
      'route-flags':'src/nvidia/inc/kernel/rmapi/control.h',
      'rpc-routing':'src/nvidia/src/kernel/rmapi/resource.c',
      'device-constructor':'src/nvidia/src/kernel/gpu/device.c',
      'display-constructors':'src/nvidia/src/kernel/gpu/disp/disp_objs.c',
      'root-client':'src/nvidia/src/kernel/rmapi/client.c',
      'hotplug-consumer':'src/nvidia/src/kernel/gpu/disp/disp_common_kern_ctrl_minimal.c',
      'gpu-open-close':'kernel-open/nvidia/nv.c',
      'system-api':'src/common/sdk/nvidia/inc/ctrl/ctrl0073/ctrl0073system.h',
      'os-api':'src/common/sdk/nvidia/inc/nvos.h',
      'device-api':'src/common/sdk/nvidia/inc/class/cl0080.h',
      'escape-api':'src/nvidia/arch/nvalloc/unix/include/nv_escape.h',
    }
    dest=output/'source-audit';dest.mkdir()
    refs={}
    for label,name in files.items():
        data=(source/name).read_bytes();(dest/(label+Path(name).suffix)).write_bytes(data)
        refs[label]=dict(path=name,sha256=hashlib.sha256(data).hexdigest(),url='https://github.com/NVIDIA/open-gpu-kernel-modules/blob/615.78.08/'+name)
    dispatch=(source/files['dispatch']).read_text()
    entries={int(code,16):int(flags,16) for flags,code in re.findall(
       r'/\*flags=\*/\s*(0x[0-9a-f]+)u,\s*/\*accessRight=\*/[^\n]*\n\s*/\*methodId=\*/\s*(0x[0-9a-f]+)u',dispatch)}
    expected={0x730107:0x82004a,0x730108:0x848,0x730109:0x44,0x73010a:0x48}
    require(all(entries.get(cmd)==flags for cmd,flags in expected.items()),'dispatch metadata changed')
    flags=(source/files['route-flags']).read_text()
    require(re.search(r'#define RMCTRL_FLAGS_ROUTE_TO_PHYSICAL\s+0x0*40\b',flags),'route flag changed')
    require(all(value&0x40 for value in expected.values()),'expected firmware routing missing')
    routing=(source/files['rpc-routing']).read_text()
    require('IS_FW_CLIENT(pGpu)' in routing and 'RMCTRL_FLAGS_ROUTE_TO_PHYSICAL' in routing and
            'NV_RM_RPC_CONTROL(pGpu' in routing,'firmware dispatch path changed')
    constructor=(source/files['device-constructor']).read_text()
    require('NV_RM_RPC_ALLOC_SHARE_DEVICE' in constructor,'device firmware allocation changed')
    consumer=(source/files['hotplug-consumer']).read_text()
    require('pDispCommon->hotPlugMaskToBeReported = 0;' in consumer and
            'pDispCommon->hotUnplugMaskToBeReported = 0;' in consumer,'event-consuming path changed')
    system=(source/files['system-api']).read_text()
    require('Return the last full detection state' in system and 'reported only ONCE' in system,'documented semantics changed')
    # Published tree declares these exports but does not contain their physical implementations.
    absent=[]
    for name in ['dispcmnCtrlCmdSystemGetConnectState_IMPL','dispcmnCtrlCmdSystemGetHotplugConfig_IMPL',
                 'dispcmnCtrlCmdSystemGetHotplugState_IMPL']:
        definitions=[]
        for f in (source/'src/nvidia/src').rglob('*.c'):
            if re.search(r'\b'+name+r'\s*\([^;{}]*\)\s*\{',f.read_text()):definitions.append(str(f.relative_to(source)))
        require(not definitions,'physical implementation now available; redo audit')
        absent.append(name)
    helper=output/'abi-recorder'
    cmd=['cc','-std=c11','-Wall','-Wextra','-Werror','-O2','-I'+str(source/'src/common/sdk/nvidia/inc'),
         '-I'+str(source/'src/common/inc'),str(Path(__file__).with_name('abi.c')),'-o',str(helper)]
    built=subprocess.run(cmd,capture_output=True,text=True)
    (output/'abi-build.txt').write_text(' '.join(cmd)+'\n'+built.stdout+built.stderr)
    require(built.returncode==0,'ABI compile failed: '+built.stderr)
    values=json.loads(subprocess.run([str(helper.resolve())],check=True,capture_output=True,text=True).stdout)
    expected_abi={'NVOS21_PARAMETERS':32,'NVOS21_PARAMETERS.pAllocParms':16,'NVOS21_PARAMETERS.status':28,
      'NVOS54_PARAMETERS':32,'NVOS54_PARAMETERS.params':16,'NVOS54_PARAMETERS.status':28,
      'NVOS00_PARAMETERS':16,'NV0080_ALLOC_PARAMETERS':56,
      'NV0073_CTRL_SYSTEM_GET_SUPPORTED_PARAMS':12,'NV0073_CTRL_SYSTEM_GET_CONNECT_STATE_PARAMS':16,
      'NV0073_CTRL_SYSTEM_GET_SET_HOTPLUG_CONFIG_PARAMS':24,'NV0073_CTRL_SYSTEM_GET_HOTPLUG_STATE_PARAMS':12,
      'cached_flags':0x31,'root_class':0x41,'device_class':0x80,
      'supported':0x730107,'connect':0x730108,'config':0x730109,'state':0x73010a}
    require(values==expected_abi,'ABI differs: '+str(values))
    (output/'abi.json').write_text(json.dumps(values,indent=2)+'\n')
    archive=source.parent/'nvidia-615.78.08.tar.gz'
    result=dict(schema='nvidia-cache-reader-source-audit',version='615.78.08',
       source_archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
       offline_source_and_abi_checks='PASS',live_rm_qualified=False,hardware_executed=False,
       transport_linked=False,all_candidate_queries_route_to_physical=True,
       dispatch_flags={hex(k):hex(v) for k,v in expected.items()},
       physical_implementations_not_in_published_tree=absent,
       device_allocation_uses_firmware_rpc=True,hotplug_unplug_read_consumes_events=True,
       blocker='Cannot establish no-reprobe/no-state-change behavior across GSP setup, queries and teardown from available source; live transport absent',
       references=refs)
    (output/'SOURCE-AUDIT.json').write_text(json.dumps(result,indent=2)+'\n')
    for name in ['reader.py','test.py','audit.py','abi.c','README.md','example-replies.json']:
        src=Path(__file__).with_name(name)
        if src.exists():shutil.copyfile(src,output/name)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=audit(a.source.resolve(),a.output.resolve())
    print(json.dumps({k:v for k,v in r.items() if k!='references'},indent=2))
