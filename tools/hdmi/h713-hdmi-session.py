#!/usr/bin/env python3
"""Target-side guarded HDMI audio session with opt-in terminal shutdown.

Requires the proven live source3 trace. Receiver lifetime remains independent
of this service. A boot-ID latch forbids retry after stop or failed setup.
"""
import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

BASE='/sys/module/'
AUDIO='h713_hdmi_audio'
OWNER='h713_hdmi_receiver'
PCM='/proc/asound/H713HDMI/pcm0c/sub0/status'
FW_PATH='/sys/module/firmware_class/parameters/path'
BOOT_ID='/proc/sys/kernel/random/boot_id'
STATE='/run/h713-hdmi-session/state.json'
PATCH_SHA='8e31db199e0078d142f622436ff0b7249b333dbb6df8ec3fbabc0d8fea6ea0c5'


class Board:
    def exists(self,path):return Path(path).exists()
    def read(self,path):return Path(path).read_text()
    def binary(self,path):return Path(path).read_bytes()
    def write(self,path,text):Path(path).write_text(text)
    def state(self,value):
        p=Path(STATE);p.parent.mkdir(parents=True,exist_ok=True)
        tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(value)+'\n');tmp.chmod(0o600);os.replace(tmp,p)
    def run(self,argv,check=True,timeout=15):
        p=subprocess.run(argv,text=True,capture_output=True,timeout=timeout)
        if check and p.returncode:raise RuntimeError(f'{argv[0]} failed: {p.stderr or p.stdout}')
        return p


class Session:
    def __init__(self,board,bundle):self.b=board;self.bundle=str(Path(bundle));self.boot=self.b.read(BOOT_ID).strip()
    def param(self,module,name):return self.b.read(BASE+module+'/parameters/'+name).strip()
    def loaded(self,module):return self.b.exists(BASE+module)
    def save(self,phase,**extra):self.b.state({'boot_id':self.boot,'phase':phase,**extra})
    def prior(self):
        if not self.b.exists(STATE):return None
        state=json.loads(self.b.read(STATE))
        return state if state.get('boot_id')==self.boot else None
    def ipc(self):
        p=self.b.run(['python3',self.bundle+'/mips-shell.py','--cmd','help win'],timeout=6)
        if 'VS:/' not in p.stdout:raise RuntimeError('MIPS IPC prompt missing')
    def owner_ready(self,clients=None):
        for key,value in [('clock_count','4'),('init_error','0'),('firmware_pin','Y'),('edid_ready','Y')]:
            if self.param(OWNER,key)!=value:raise RuntimeError('receiver readiness failed: '+key)
        if clients is not None and self.param(OWNER,'clients')!=str(clients):raise RuntimeError('unexpected receiver client count')
        for domain in ('tvfe','tvcap'):
            if self.b.read('/sys/devices/h713-hdmi-'+domain+'/power/runtime_status').strip()!='active':raise RuntimeError('receiver domain inactive')
    def audio_ready(self):
        self.owner_ready(1)
        for key,value in [('graph_ready','Y'),('dsp_failed','N'),('manage_dsp','Y'),('manage_tvfe','Y'),('require_receiver_owner','Y')]:
            if self.param(AUDIO,key)!=value:raise RuntimeError('audio readiness failed: '+key)
    def start(self):
        if self.loaded(AUDIO):
            self.audio_ready()
            prior=self.prior()
            if not prior or prior.get('phase')!='ready':raise RuntimeError('audio exists without this service ownership; refusing adoption')
            return {'phase':'ready','already_ready':True}
        prior=self.prior()
        if prior:raise RuntimeError('initialization already attempted on this boot; physical cold boot required')
        for legacy in ('h713_hdmi_power','h713_edid_clock','h713_hdmi_tvfe_hold','h713_hdmi_dsp_probe','h713_scp_probe','h713_ddc_pins'):
            if self.loaded(legacy):raise RuntimeError('competing diagnostic owner: '+legacy)
        proof=json.loads(self.b.read(self.bundle+'/cold-boot-proof.json'))
        if proof.get('boot_id')!=self.boot or proof.get('cold_boot_confirmed') is not True or proof.get('parked_status_before_launch')!=0 or proof.get('source3_verified') is not True:
            raise RuntimeError('cold-U-Boot proof does not match this Linux boot')
        patch=self.b.binary(self.bundle+'/firmware/h713/hdmi-audio-dsp.bin')
        if len(patch)!=2896 or hashlib.sha256(patch).hexdigest()!=PATCH_SHA:raise RuntimeError('pinned firmware hash/size mismatch')
        release=self.b.run(['uname','-r']).stdout.strip()
        if release!='6.18.38':raise RuntimeError('unexpected kernel release')
        for module in ('h713-hdmi-receiver.ko','h713-hdmi-audio.ko'):
            if self.b.run(['modinfo','-F','vermagic',self.bundle+'/'+module]).stdout.split()[0]!=release:raise RuntimeError('module ABI mismatch')
        status=self.b.run(['python3',self.bundle+'/mips-shell.py','--status']).stdout
        if 'MIPS core      ALIVE' not in status:raise RuntimeError('MIPS is not proven live; guarded cold U-Boot launch required')
        trace=json.loads(self.b.run(['python3',self.bundle+'/read-comm-trace.py','--source-only']).stdout)
        if trace.get('guards')!='43414e31/43414e31' or trace.get('source3_transition_complete')!=1 or trace.get('source3_worker_new')!='00000003':raise RuntimeError('source3 trace guard failed')
        self.save('attempted')
        try:
            if not self.loaded(OWNER):self.b.run(['insmod',self.bundle+'/h713-hdmi-receiver.ko','armed=1','live_source3=1'])
            if self.param(OWNER,'init_error')!='0':raise RuntimeError('receiver partial setup failed; holds retained')
            current=int(self.param(OWNER,'clock_count'))
            if not 0<=current<=4:raise RuntimeError('invalid receiver clock stage')
            for stage in range(current+1,5):
                self.b.write(BASE+OWNER+'/parameters/clock_count',str(stage)+'\n');self.ipc()
            self.owner_ready(0);self.ipc()
            original=self.b.read(FW_PATH).rstrip('\n')
            try:
                self.b.write(FW_PATH,self.bundle+'/firmware\n')
                self.b.run(['insmod',self.bundle+'/h713-hdmi-audio.ko','armed=1','live_source3=1','receiver_powered=1'],timeout=20)
            finally:
                self.b.write(FW_PATH,original+'\n')
                if self.b.read(FW_PATH).rstrip('\n')!=original:raise RuntimeError('firmware search-path restoration failed')
            self.audio_ready();self.save('ready')
            return {'phase':'ready','already_ready':False}
        except Exception as error:
            self.save('failed',error=str(error),cold_boot_required=True)
            raise
    def stop(self):
        if not self.loaded(AUDIO):
            prior=self.prior() or {}
            if prior.get('phase') in ('parking','parked','parking_failed'):
                return {'phase':prior['phase'],'already_stopped':True,'receiver_retained':self.loaded(OWNER)}
            self.save('stopped',cold_boot_required=True,restore_verified=prior.get('restore_verified') is True)
            return {'phase':'stopped','already_stopped':True,'receiver_retained':self.loaded(OWNER)}
        prior=self.prior()
        if not prior or prior.get('phase')!='ready':raise RuntimeError('audio is not owned by this service; refusing removal')
        self.audio_ready()
        if self.b.read(PCM).strip()!='closed':raise RuntimeError('capture is open; close its client before stopping')
        wp=['runuser','-u','media','--','env','XDG_RUNTIME_DIR=/run/user/1000','systemctl','--user']
        active=self.b.run(wp+['is-active','wireplumber.service'],check=False)
        if active.returncode not in (0,3):raise RuntimeError('cannot establish WirePlumber state')
        restore=active.returncode==0
        try:
            if restore:self.b.run(wp+['stop','wireplumber.service'])
            if self.b.read(PCM).strip()!='closed':raise RuntimeError('capture opened during stop; retained audio')
            before=self.b.run(['dmesg','--color=never']).stdout
            self.b.run(['rmmod',AUDIO])
            self.save('stopped',cold_boot_required=True)
            after=self.b.run(['dmesg','--color=never']).stdout
            if not after.startswith(before):raise RuntimeError('kernel log changed during restore; verification unavailable')
            tail=after[len(before):]
            if len(re.findall(r'DSP restore [0-9a-f]{4}=[0-9a-f]{4} verified',tail))!=22 or 'managed DSP graph restored 22 words' not in tail or '15 clock words and bus verified' not in tail:
                raise RuntimeError('DSP/TVFE restore verification missing; cold boot required')
            if self.loaded(AUDIO):raise RuntimeError('audio removal incomplete')
            self.owner_ready(0);self.ipc()
            self.save('stopped',cold_boot_required=True,restore_verified=True)
            return {'phase':'stopped','already_stopped':False,'receiver_retained':True,'dsp_restored_words':22,'tvfe_restored_words':15}
        finally:
            if restore:self.b.run(wp+['start','wireplumber.service'])
    def park(self):
        prior=self.prior() or {}
        if self.loaded(AUDIO) or prior.get('phase')!='stopped' or prior.get('restore_verified') is not True:
            raise RuntimeError('verified managed audio stop required before terminal parking')
        if self.param(OWNER,'shutdown_ready')!='Y':
            raise RuntimeError('parking-capable RAM device tree and receiver owner required')
        for module in ('h713_scp_probe','h713_ddc_pins','h713_hdmi_v4l2'):
            if self.loaded(module):raise RuntimeError('competing client/helper: '+module)
        self.owner_ready(0);self.ipc()
        self.save('parking',cold_boot_required=True,restore_verified=True)
        try:
            self.b.write(BASE+OWNER+'/parameters/park_for_shutdown','1\n')
            if self.param(OWNER,'parked')!='Y' or self.param(OWNER,'park_failed')!='N':
                raise RuntimeError('terminal parking not verified; receiver holds retained')
            status=self.b.run(['python3',self.bundle+'/mips-shell.py','--status']).stdout
            if 'MIPS core      parked' not in status:
                raise RuntimeError('hardware MIPS parked status missing; receiver holds retained')
            self.b.write(BASE+OWNER+'/parameters/release_when_parked','1\n')
            if self.param(OWNER,'firmware_pin')!='N' or self.param(OWNER,'clients')!='0' or self.param(OWNER,'edid_ready')!='N':
                raise RuntimeError('parked receiver release not verified')
            self.b.run(['rmmod',OWNER])
            if self.loaded(OWNER):raise RuntimeError('receiver removal incomplete')
            self.save('parked',cold_boot_required=True,restore_verified=True)
            return {'phase':'parked','receiver_removed':True,'cold_boot_required':True}
        except Exception as error:
            self.save('parking_failed',cold_boot_required=True,restore_verified=True,error=str(error))
            raise

    def shutdown(self):
        prior=self.prior() or {}
        if prior.get('phase')=='parked' and not self.loaded(AUDIO) and not self.loaded(OWNER):
            return {'phase':'parked','already_parked':True,'receiver_removed':True}
        if prior.get('phase') in ('parking','parking_failed'):
            raise RuntimeError('terminal parking already attempted; physical cold boot required')
        # Check capability before stopping audio. Never leave a capture-only
        # owner half transitioned because a shutdown drop-in was misapplied.
        if not self.loaded(OWNER) or self.param(OWNER,'shutdown_ready')!='Y':
            raise RuntimeError('parking-capable receiver owner required for terminal shutdown')
        stopped=self.stop()  # Failure prevents every reset/release operation.
        parked=self.park()
        return {**parked,'audio_stop':stopped}

    def status(self):
        return {'boot_id':self.boot,'state':self.prior(),'audio_loaded':self.loaded(AUDIO),'receiver_loaded':self.loaded(OWNER)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('start','stop','status','park','shutdown'))
    parser.add_argument('--bundle',type=Path,default=Path('/tmp/h713-linux-return'))
    parser.add_argument('--terminal-shutdown',action='store_true',help='Explicit terminal parking opt-in; no restart is provided')
    args=parser.parse_args()
    if args.action in ('park','shutdown') and not args.terminal_shutdown:parser.error(args.action+' requires --terminal-shutdown')
    Path('/run/h713-hdmi-session').mkdir(exist_ok=True)
    with open('/run/h713-hdmi-session/lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        session=Session(Board(),args.bundle)
        print(json.dumps(getattr(session,args.action)()),flush=True)


if __name__=='__main__':
    try:main()
    except Exception as error:sys.exit(str(error))
