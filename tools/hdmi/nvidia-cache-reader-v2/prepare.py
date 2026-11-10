#!/usr/bin/env python3
"""Prepare the version-pinned NVIDIA reader offline. No live GPU/board calls."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE=Path(__file__).resolve().parent

def sha(data):return hashlib.sha256(data).hexdigest()
def need(ok,message):
    if not ok:raise ValueError(message)

def entries(source):
    return {int(code,16):int(flags,16) for flags,code in re.findall(
      r'/\*flags=\*/\s*(0x[0-9a-f]+)u,\s*/\*accessRight=\*/[^\n]*\n\s*/\*methodId=\*/\s*(0x[0-9a-f]+)u',source)}

def prepare(source,output):
    need(not output.exists(),'output already exists')
    need('615.78.08' in (source/'version.mk').read_text(),'source version mismatch')
    output.mkdir(mode=0o700,parents=True)
    paths=['kernel-open/nvidia/nv.c','src/nvidia/arch/nvalloc/unix/src/escape.c',
      'src/nvidia/src/kernel/gpu/device.c','src/nvidia/src/kernel/gpu/disp/disp_objs.c',
      'src/nvidia/src/kernel/rmapi/resource.c','src/nvidia/src/kernel/rmapi/alloc_free.c',
      'src/nvidia/src/kernel/rmapi/entry_points.c','src/nvidia/src/kernel/rmapi/client.c',
      'src/nvidia/src/kernel/rmapi/client_resource.c','src/nvidia/src/kernel/gpu_mgr/gpu_mgr.c',
      'src/nvidia/generated/g_disp_objs_nvoc.c','src/nvidia/generated/g_client_resource_nvoc.c',
      'src/nvidia/inc/kernel/rmapi/control.h','src/common/sdk/nvidia/inc/nvos.h',
      'src/common/sdk/nvidia/inc/ctrl/ctrl0073/ctrl0073system.h',
      'src/common/sdk/nvidia/inc/ctrl/ctrl0073/ctrl0073specific.h',
      'src/common/sdk/nvidia/inc/ctrl/ctrl0000/ctrl0000gpu.h']
    audit=output/'source-audit';audit.mkdir();references={}
    for index,name in enumerate(paths):
        dest=f'{index:02d}-'+Path(name).name;data=(source/name).read_bytes();(audit/dest).write_bytes(data)
        references[name]=dict(file=dest,sha256=sha(data),url='https://github.com/NVIDIA/open-gpu-kernel-modules/blob/615.78.08/'+name)
    host=(source/paths[0]).read_text();escape=(source/paths[1]).read_text()
    display=(source/'src/nvidia/generated/g_disp_objs_nvoc.c').read_text()
    root=(source/'src/nvidia/generated/g_client_resource_nvoc.c').read_text()
    de=entries(display);ro=entries(root)
    expected={0x730107:0x82004a,0x730108:0x848,0x73010a:0x48,0x730250:0x48}
    need(all(de.get(k)==v for k,v in expected.items()),'display dispatch metadata changed')
    need(all(v&8 and not v&4 for v in expected.values()),'candidate query requires privilege')
    need(de[0x730109]&4,'GET_HOTPLUG_CONFIG privilege changed; redo exclusion audit')
    need(all(ro[k]&0x40==0 for k in [0x201,0x205,0x21b]),'GPU metadata unexpectedly routes to firmware')
    need('if (nv_is_control_device(inode))' in host and 'nvidia_ctl_open(inode, file)' in host,'control open path changed')
    ctl=host.split('static int\nnvidia_ctl_open(',1)[1].split('/*\n** nvidia_ctl_close',1)[0]
    need('nv_open_device' not in ctl and 'rm_init_adapter' not in ctl,'control node initializes GPU')
    fd=escape.split('static NV_STATUS RmGetDeviceFd(',1)[1].split('// Only return errors',1)[0]
    need('default:\n            return NV_OK;' in fd and 'NV0073_' not in fd,'queries now require GPU device FD')
    lifecycle=(source/'src/nvidia/src/kernel/gpu/device.c').read_text()
    need('gpumgrGetGpu(gpuInst)' in lifecycle and 'NV_RM_RPC_ALLOC_SHARE_DEVICE' in lifecycle,'device lifetime path changed')
    free=(source/'src/nvidia/src/kernel/rmapi/entry_points.c').read_text()
    need('pArgs->hRoot, pArgs->hObjectOld, RMAPI_FREE_FLAGS_NONE' in free,'free ownership path changed')
    system=(source/'src/common/sdk/nvidia/inc/ctrl/ctrl0073/ctrl0073system.h').read_text()
    need('Return the last full detection state' in system and 'reported only ONCE' in system,'cache/event API contract changed')
    cmd=['cc','-std=c11','-Wall','-Wextra','-Werror','-O2',
       '-I'+str(source/'src/common/sdk/nvidia/inc'),'-I'+str(source/'src/common/inc'),
       '-I'+str(source/'src/nvidia/arch/nvalloc/unix/include'),str(HERE/'abi.c'),'-o',str(output/'abi-recorder')]
    compile_result=subprocess.run(cmd,capture_output=True,text=True)
    (output/'abi-build.txt').write_text(' '.join(cmd)+'\n'+compile_result.stdout+compile_result.stderr)
    need(compile_result.returncode==0,'ABI compilation failed: '+compile_result.stderr)
    abi=json.loads(subprocess.run([str((output/'abi-recorder').resolve())],check=True,capture_output=True,text=True).stdout)
    (output/'abi.json').write_text(json.dumps(abi,indent=2)+'\n')
    for name in ['reader.py','protocol.py','transport.py','test.py','abi.c','prepare.py','README.md']:
        if (HERE/name).exists():shutil.copyfile(HERE/name,output/name)
    sys.path.insert(0,str(output));from transport import verify_abi
    verify_abi(abi)
    proof=dict(schema='nvidia-cache-reader-v2-source-audit',version='615.78.08',
       source_archive_sha256=sha((source.parent/'nvidia-615.78.08.tar.gz').read_bytes()),
       display_dispatch={hex(k):hex(v) for k,v in expected.items()},root_metadata_dispatch={hex(k):hex(ro[k]) for k in [0x201,0x205,0x21b]},
       control_node_bypasses_adapter_open=True,query_controls_do_not_require_gpu_fd=True,
       physical_implementations_available=False,firmware_execution_eliminated=False,
       qualification_basis='version-matched supported API contract plus open host lifecycle audit',
       strict_original_bad_state_preservation_qualification=False,
       changed_context='operator reports board powered off; original bad state and live SCP session ended',
       owned_resources_only=True,no_display_engine_classes=True,no_event_subscription=True,
       no_EDID_request=True,no_attach_detach=True,no_GPU_node_open=True,
       cached_connection_flags='0x31',no_fallback=True,references=references)
    (output/'SOURCE-AUDIT.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof

if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--source',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    x=a.parse_args();result=prepare(x.source.resolve(),x.output.resolve())
    print(json.dumps({k:v for k,v in result.items() if k!='references'},indent=2))
