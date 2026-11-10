#!/usr/bin/env python3
"""Boot-bound live capture driver. Default: offline package verification/plan.

--execute-approved selects a separately authorized temporary companion load
and one capture request. It NEVER releases preservation, unloads, retries,
reseats, enables output, pulses HPD or resets anything. No UART is used.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import selectors
import shlex
import subprocess
import time

REMOTE = r'''
from pathlib import Path
import base64,hashlib,json,mmap,os,subprocess,sys,time
def require(ok,message):
 if not ok:raise RuntimeError(message)
def emit(phase,**values):print(json.dumps(dict(phase=phase,**values)),flush=True)
config=json.loads(sys.stdin.readline());m=config['manifest'];identity=m['identity']
params=Path('/sys/module/h713_scp_sampler_v2/parameters')
def text(path):return Path(path).read_text().strip('\0\n')
def basic():
 require(text('/proc/device-tree/model')=='HY200 QZ713DF_A1 (Allwinner H713)','wrong board')
 require(text('/proc/sys/kernel/random/boot_id')==identity['boot_id'],'boot changed')
 require(hashlib.sha256(Path('/sys/kernel/notes').read_bytes()).hexdigest()==identity['kernel_notes_sha256'],'kernel build changed')
 require(hashlib.sha256(Path('/usr/lib/h713-hdmi/h713-hdmi-signal.ko').read_bytes()).hexdigest()==identity['owner_sha256'],'owner file changed')
 require(hashlib.sha256(Path('/sys/module/h713_hdmi_signal/notes/.note.gnu.build-id').read_bytes()).hexdigest()==identity['owner_note_sha256'],'loaded owner build changed')
 require(text('/sys/devices/platform/h713-hdmi-ring/signal')=='none','bad signal state no longer present')
def snapshot():
 fd=os.open('/dev/mem',os.O_RDONLY|os.O_SYNC|os.O_CLOEXEC)
 try:
  with mmap.mmap(fd,0x5000,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ,offset=0x00100000) as view:return view[:]
 finally:os.close(fd)
def ack(command):
 request=json.loads(sys.stdin.readline())
 require(request==dict(command=command,nonce=m['nonce']),'missing host acknowledgement')
basic();require(not params.exists(),'a sampler already exists; no reuse or retry')
for path,item in config['file_pins'].items():
 import stat
 p=Path(path);s=p.stat();data=p.read_bytes()
 require(hashlib.sha256(data).hexdigest()==item['sha256'] and len(data)==item['bytes'],'file drift: '+path)
 require(stat.S_IMODE(s.st_mode)==item['mode'] and s.st_uid==item['uid'] and s.st_gid==item['gid'],'metadata drift: '+path)
for module,name,value in [('h713_hdmi_receiver','clock_count','4'),('h713_hdmi_receiver','edid_ready','Y'),
 ('h713_hdmi_receiver','init_error','0'),('h713_hdmi_receiver','firmware_pin','Y'),
 ('h713_hdmi_signal','ready','Y'),('h713_hdmi_signal','failed','N'),('h713_hdmi_signal','restored','N')]:
 require(text('/sys/module/'+module+'/parameters/'+name)==value,'receiver/owner precondition changed')
before=snapshot();require(hashlib.sha256(before).hexdigest()==m['baseline_sram_sha256'],'SCP SRAM generation changed')
emit('preflight',boot_id=identity['boot_id'],pins=len(config['file_pins']),before_sram=base64.b64encode(before).decode())
ack('load');basic()
module_bytes=base64.b64decode(config['module_base64'],validate=True)
require(hashlib.sha256(module_bytes).hexdigest()==config['module_sha256'],'companion transfer checksum')
fd=os.memfd_create('h713-scp-sampler-v2',os.MFD_CLOEXEC)
try:
 with os.fdopen(os.dup(fd),'wb') as f:f.write(module_bytes)
 os.lseek(fd,0,os.SEEK_SET)
 p=subprocess.run(['insmod','/proc/self/fd/'+str(fd)],pass_fds=(fd,),capture_output=True,text=True,timeout=15)
 require(p.returncode==0,'inert companion load failed: '+p.stderr)
finally:os.close(fd)
require(params.exists() and text(params/'status')=='0','companion not inert/idle')
emit('loaded-inert',boot_id=identity['boot_id'])
ack('capture');basic()
# From this point DO NOT query the owner's parameters: the worker holds its
# parameter lock. Only this companion's own status/result and SRAM are read.
(params/'capture').write_text(hex(m['nonce'])+'\n')
emit('capture-requested',nonce=m['nonce']);end=time.monotonic()+30;last=None
while time.monotonic()<end:
 state=int(text(params/'status'))
 if state!=last:emit('progress',status=state);last=state
 if state in [8,9,10]:break
 time.sleep(.1)
else:state=int(text(params/'status'))
result=text(params/'result') if state==8 else None
after=snapshot()
emit('finished',status=state,reason=int(text(params/'reason')),result=result,
 bootstrap_sr=int(text(params/'bootstrap_sr')),original_r13=int(text(params/'original_r13')),
 after_sram=base64.b64encode(after).decode(),owner_stop_held=state not in [0,9,11],
 no_release_performed=True,boot_id=text('/proc/sys/kernel/random/boot_id'))
'''


def require(ok,message):
    if not ok:raise ValueError(message)


def digest(data):return hashlib.sha256(data).hexdigest()


def load_packet(path):
    names=set()
    for line in (path/'SHA256SUMS').read_text().splitlines():
        sha,name=line.split('  ',1);p=Path(name)
        require(not p.is_absolute() and '..' not in p.parts and name not in names,'unsafe checksum member')
        require(not (path/p).is_symlink() and digest((path/p).read_bytes())==sha,'package checksum: '+name)
        names.add(name)
    require({'manifest.json','h713-scp-sampler-v2.ko','baseline-sram.bin','live-preflight.json',
             'LIVE-CAPTURE-GATE.json','fragment-a.bin','fragment-b.bin'}<=names,'incomplete package')
    m=json.loads((path/'manifest.json').read_text());gate=json.loads((path/'LIVE-CAPTURE-GATE.json').read_text())
    require(m['schema']=='h713-scp-sampler-v2' and gate['prepared_for_explicit_capture'] is True,'package not prepared for capture')
    require(gate['hardware_executed'] is False and gate['automatic_release'] is False,'unexpected lifecycle policy')
    require(digest((path/'baseline-sram.bin').read_bytes())==m['baseline_sram_sha256'],'baseline checksum')
    data=(path/'h713-scp-sampler-v2.ko').read_bytes()
    require(data[:6]==b'\x7fELF\x02\x01' and int.from_bytes(data[18:20],'little')==183,'not an AArch64 companion ELF')
    preflight=json.loads((path/'live-preflight.json').read_text())
    require(len(preflight['file_pins'])==56,'missing file pins')
    return m,preflight


def verify_finished(packet,m,event):
    import struct
    require(event['boot_id']==m['identity']['boot_id'],'boot changed during capture')
    require(event['status']==8 and event['reason']==0 and event['no_release_performed'],'capture did not reach held success')
    require(event['owner_stop_held'] is True,'preservation lock not held')
    frame=[int(n) for n in event['result'].split()]
    require(len(frame)==18 and frame[:3]==[m['nonce'],8,0],'bad result frame')
    require(frame[3]&0x17e==0 and frame[3]&1,'unsafe SCP SR')
    require(event['bootstrap_sr']&0x17e==0 and event['bootstrap_sr']&1,'unsafe bootstrap SR')
    after=base64.b64decode(event['after_sram'],validate=True);before=(packet/'baseline-sram.bin').read_bytes()
    require(len(after)==len(before)==0x5000,'bad SRAM capture size')
    def word(off):return struct.unpack_from('<I',after,off)[0]
    require(word(0x4404)==m['original_instruction'],'entry not unhooked')
    require(word(0x4414)==0 and word(0x4418)==0x15000000,'restore-entry preservation guard absent')
    require(word(0x4f0c)==word(0x4f18)==word(0x4f10)==word(0x4f1c)==0,'owner/trap/stop state changed')
    require(word(0x4f80)==0 and word(0x4f84)==word(0x4f8c)==word(0x4f9c)==m['nonce'],'nonce/one-shot state mismatch')
    require(word(0x4f98)==14 and word(0x4f94)==0,'incomplete/failed SCP sample')
    require(word(0x4f90)==word(0x4ff0)==m['post_challenge'],'post-return echo mismatch')
    require(word(0x4ff4)==event['original_r13'],'bootstrap register restore cell mismatch')
    require(frame[4:]==[word(0x4fa0+4*i) for i in range(14)],'kernel result differs from SRAM')
    allowed=set(range(0x4f80,0x5000))|set(range(0x4414,0x441c))
    for f in m['fragments']:
        code=(packet/f['file']).read_bytes();off=f['offset']
        require(after[off:off+len(code)]==code,'resident code mismatch')
        allowed.update(range(off,off+len(code)))
    require(all(i in allowed for i,(x,y) in enumerate(zip(before,after)) if x!=y),'unapproved SRAM change')
    return dict(status='PASS capture held; bad-state preservation not released',boot_id=event['boot_id'],
                sr=frame[3],registers={hex(a):f'0x{v:08x}' for a,v in zip(m['read_registers'],frame[4:])},
                owner_stop_held=True,restore_guard_resident=True,scratch_resident=True,automatic_release=False,
                resets=False,HPD_writes=False,after_sha256=digest(after))


def durable(path,data):
    with path.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def host_bad_state():
    p=Path('/sys/class/drm/card1-HDMI-A-1')
    require((p/'status').read_text().strip()=='disconnected' and not (p/'edid').read_bytes(),'host bad state no longer present')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--packet',type=Path,required=True)
    p.add_argument('--execute-approved',action='store_true')
    p.add_argument('--output',type=Path)
    a=p.parse_args();m,preflight=load_packet(a.packet)
    if not a.execute_approved:
        print(json.dumps(dict(mode='OFFLINE PLAN ONLY',boot_id=m['identity']['boot_id'],nonce=m['nonce'],
                             hardware_opened=False,companion_loaded=False,automatic_release=False,
                             capture_outcome='owner stop remains held; guard and scratch resident'),indent=2));return
    require(a.output,'new private output directory required');host_bad_state()
    os.umask(0o077);a.output.mkdir(mode=0o700,parents=True,exist_ok=False)
    module=(a.packet/'h713-scp-sampler-v2.ko').read_bytes()
    config=dict(manifest=m,file_pins=preflight['file_pins'],module_sha256=digest(module),module_base64=base64.b64encode(module).decode())
    command='python3 -u -B -c '+shlex.quote(REMOTE)
    process=subprocess.Popen(['ssh','-F','/dev/null','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8',
                              'root@192.168.4.1',command],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                             stderr=(a.output/'ssh-stderr.txt').open('xb'))
    selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ)
    process.stdin.write((json.dumps(config)+'\n').encode());process.stdin.flush()
    pending=b'';finished=False;deadline=time.monotonic()+75
    try:
        with (a.output/'events.jsonl').open('xb',buffering=0) as log:
            while not finished:
                require(time.monotonic()<deadline,'host deadline; no retry/release; inspect retained state')
                if not selector.select(.2):
                    require(process.poll() is None,'remote ended before capture result');continue
                data=os.read(process.stdout.fileno(),65536);require(data,'observation connection closed; no retry/release')
                pending+=data
                while b'\n' in pending:
                    line,pending=pending.split(b'\n',1);event=json.loads(line);log.write(line+b'\n');os.fsync(log.fileno())
                    if event['phase']=='preflight':
                        before=base64.b64decode(event['before_sram'],validate=True)
                        require(digest(before)==m['baseline_sram_sha256'],'fresh backup generation mismatch')
                        durable(a.output/'before-sram.bin',before);host_bad_state()
                        process.stdin.write((json.dumps(dict(command='load',nonce=m['nonce']))+'\n').encode());process.stdin.flush()
                    elif event['phase']=='loaded-inert':
                        durable(a.output/'CAPTURE-INTENT.json',json.dumps(dict(boot_id=m['identity']['boot_id'],nonce=m['nonce'],
                            companion_sha256=digest(module),at_most_one_capture=True,automatic_release=False),indent=2).encode())
                        host_bad_state()
                        process.stdin.write((json.dumps(dict(command='capture',nonce=m['nonce']))+'\n').encode());process.stdin.flush()
                    elif event['phase']=='finished':
                        after=base64.b64decode(event['after_sram'],validate=True);durable(a.output/'after-sram.bin',after)
                        # Persist even a failure/ambiguous outcome before verification raises.
                        durable(a.output/'REMOTE-RESULT.json',json.dumps(event,indent=2).encode())
                        result=verify_finished(a.packet,m,event)
                        durable(a.output/'RESULT.json',json.dumps(result,indent=2).encode());print(json.dumps(result,indent=2));finished=True
        require(process.wait(timeout=5)==0,'remote capture process failed')
    finally:
        selector.close()
        if process.poll() is None:process.terminate()
        # Deliberately no target release, cleanup, rmmod, retry or reset.


if __name__=='__main__':main()
