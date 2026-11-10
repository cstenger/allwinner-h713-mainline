#!/usr/bin/env python3
"""One guarded qualification step at a time; no recovery or automatic reboot retry."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import time

REPO=Path(__file__).resolve().parents[2]
KNOWN=REPO/'local/recovery/2026-11-03-production-install-03/known_hosts'
SSH=['ssh','-F','/dev/null','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
     '-o','UserKnownHostsFile='+str(KNOWN),'-o','ConnectTimeout=5',
     '-o','ServerAliveInterval=2','-o','ServerAliveCountMax=2','root@192.168.4.1']
UNITS=['h713-hdmi-'+name+'.service' for name in
       ('prepare','capture','signal','ring','video','speaker','health-ack','readvertise')]

# This code runs only read-only commands and sysfs/proc reads on the board.
REMOTE=r'''
import json,subprocess,time
from pathlib import Path
UNITS=['h713-hdmi-'+name+'.service' for name in ('prepare','capture','signal','ring','video','speaker','health-ack','readvertise')]
def read(path):return Path(path).read_text().strip()
def command(args):return subprocess.run(args,check=True,capture_output=True,text=True,timeout=30).stdout
def snapshot():
    boot=read('/proc/sys/kernel/random/boot_id')
    raw=command(['systemctl','show',*UNITS,'user@1000.service','-p','Id','-p','ActiveState','-p','Result','-p','NRestarts','-p','InactiveExitTimestampMonotonic','-p','ExecMainStartTimestampMonotonic','-p','ExecMainExitTimestampMonotonic','-p','ActiveEnterTimestampMonotonic'])
    services={}
    for block in raw.strip().split('\n\n'):
        row=dict(line.split('=',1) for line in block.splitlines() if '=' in line)
        services[row.pop('Id')]=row
    result={'boot_id':boot,'uptime':float(read('/proc/uptime').split()[0]),'services':services}
    errors={}
    try:
        for key,path in {'rejected':'/sys/module/h713_hdmi_v4l2/parameters/frames_rejected','xruns':'/sys/module/h713_hdmi_audio/parameters/period_xruns','bad_guard':'/sys/module/h713_hdmi_v4l2/parameters/sig_bad_guard','invalid_pair':'/sys/module/h713_hdmi_v4l2/parameters/afbd_invalid'}.items():errors[key]=int(read(path))
        result.update(errors=errors,frames=int(read('/sys/module/h713_hdmi_v4l2/parameters/frames_produced')),signal=read('/sys/devices/platform/h713-hdmi-ring/signal'),readvertised=int(read('/sys/module/h713_hdmi_signal/parameters/readvertised')),capture_pcm=read('/proc/asound/H713HDMI/pcm0c/sub0/status'),playback_pcm=read('/proc/asound/Codec/pcm0p/sub0/status'))
    except OSError as error:result['not_ready']=str(error)
    # Optional second-advertisement counters (startup HPD pulse / HPD-only diagnostic).
    for key in ('hpd_pulses','hpd_cycles'):
        try:result[key]=int(read('/sys/module/h713_hdmi_signal/parameters/'+key))
        except (OSError,ValueError):pass
    if read('/proc/sys/kernel/random/boot_id')!=boot:raise RuntimeError('boot changed during snapshot')
    return result
def gather(previous=None):
    result=snapshot()
    result['journal']=command(['journalctl','-b','-o','short-monotonic','--no-pager',*[arg for unit in UNITS+['user@1000.service'] for arg in ['-u',unit]]])
    result['dmesg']=command(['dmesg','--color=never'])
    result['startup_time']=command(['systemd-analyze','time'])
    result['failed_units']=command(['systemctl','--failed','--no-legend','--plain','--no-pager'])
    if previous:
        result['previous_journal']=command(['journalctl','--boot='+previous.replace('-',''),'-o','short-monotonic','--no-pager',*[arg for unit in UNITS+['user@1000.service'] for arg in ['-u',unit]]])
    return result
'''


def need(condition,message):
    if not condition:raise RuntimeError(message)


def healthy(row):
    need(set(UNITS)<=set(row.get('services',{})),'missing service evidence')
    for name in UNITS:
        unit=row['services'][name]
        need(unit.get('ActiveState')=='active' and unit.get('NRestarts')=='0'
             and unit.get('Result')=='success','service state/restart/result: '+name)
    need(row.get('errors')=={'rejected':0,'xruns':0,'bad_guard':0,'invalid_pair':0},'capture errors or missing counters')
    need(row.get('signal')=='locked 1280x720','source is not locked 720p')
    for key in ('capture_pcm','playback_pcm'):
        need('state: RUNNING' in row.get(key,''),'PCM not running: '+key)


def startup_evidence(row):
    healthy(row)
    journal=row['journal']
    checks=[json.loads(line.split('MIPS IPC completion ',1)[1]) for line in journal.splitlines() if 'MIPS IPC completion ' in line]
    need(len(checks)==5,'expected exactly five startup IPC completions')
    for check in checks:
        need(check.get('schema')=='h713-mips-ipc-v1' and check.get('complete') is True
             and check.get('command')=='help win' and check.get('reply_bytes')==66
             and 0<=check.get('elapsed_seconds',-1)<1.5,'invalid IPC completion')
    need('"already_ready": true' in journal,'capture did not adopt prepared backend')
    acknowledgements=[]
    for line in journal.splitlines():
        if '{' not in line:continue
        try:record=json.loads(line[line.index('{'):])
        except ValueError:continue
        if record.get('boot_id')==row['boot_id'] and record.get('gp6_after')=='48444f4b' and record.get('gp7')=='00000000':acknowledgements.append(record)
    need(bool(acknowledgements),'automatic HDOK/GP7 acknowledgement missing')
    need(not row['failed_units'].strip(),'failed system units')
    def mark(name,key):return float(row['services'][name][key])/1e6
    prepare=mark('h713-hdmi-prepare.service','ExecMainStartTimestampMonotonic')
    user_start=mark('user@1000.service','ExecMainStartTimestampMonotonic')
    user_ready=mark('user@1000.service','ActiveEnterTimestampMonotonic')
    prepare_end=mark('h713-hdmi-prepare.service','ExecMainExitTimestampMonotonic')
    overlap=max(0,min(user_ready,prepare_end)-max(user_start,prepare))
    need(overlap>0,'no observed prepare/user-session overlap')
    return {'ipc_seconds':[c['elapsed_seconds'] for c in checks],
            'prepare_start':prepare,'user_overlap_seconds':overlap,
            'capture_ready':mark('h713-hdmi-capture.service','ActiveEnterTimestampMonotonic'),
            'video_active':mark('h713-hdmi-video.service','ActiveEnterTimestampMonotonic'),
            'readvertised':row['readvertised'],'startup_time':row['startup_time']}


def shutdown_evidence(journal):
    need('EDID/HPD, SCP SRAM/vectors and DDC ownership restored' in journal,'signal restoration missing')
    need('"phase": "parked"' in journal and '"receiver_removed": true' in journal
         and '"dsp_restored_words": 22' in journal and '"tvfe_restored_words": 15' in journal,'backend parking/restoration missing')
    def position(unit):
        match=re.search(r'Stopped '+re.escape(unit)+r'(?:\s|\.)',journal)
        need(match is not None,'shutdown stop evidence missing: '+unit)
        return match.start()
    video=position('h713-hdmi-video.service');speaker=position('h713-hdmi-speaker.service')
    signal=position('h713-hdmi-signal.service');capture=position('h713-hdmi-capture.service')
    prepare=position('h713-hdmi-prepare.service');user=position('user@1000.service')
    need(max(video,speaker)<signal<capture<min(prepare,user),'shutdown ordering failed')
    return 'PASS: consumers -> signal -> capture -> prepare/user-session'


def stable(samples):
    need(len(samples)>=2,'missing stability interval')
    for row in samples:
        healthy(row);need(row['boot_id']==samples[0]['boot_id'],'boot changed in stability interval')
        for name in UNITS:
            need(row['services'][name]['ExecMainStartTimestampMonotonic']==samples[0]['services'][name]['ExecMainStartTimestampMonotonic'],'service identity changed: '+name)
    for before,after in zip(samples,samples[1:]):
        need(after['uptime']>before['uptime'] and after['frames']>before['frames'],'time/frame counter stalled or reset')
    seconds=samples[-1]['uptime']-samples[0]['uptime']
    need(seconds>=30,'stability interval shorter than 30 seconds')
    fps=(samples[-1]['frames']-samples[0]['frames'])/seconds
    need(fps>=50,'stable video frame rate below 50 fps')
    return {'seconds':seconds,'fps':fps,'frames':samples[-1]['frames']-samples[0]['frames']}


def remote(script,timeout=90):
    return subprocess.run(SSH+['python3','-'],input=script,capture_output=True,text=True,timeout=timeout)


def save(path,data):
    path.write_text(json.dumps(data,indent=2)+'\n')


def read_remote(script,path):
    result=remote(script)
    path.with_suffix('.stderr').write_text(result.stderr)
    path.write_text(result.stdout)
    need(result.returncode==0,'read-only board collection failed: '+str(path))
    return json.loads(result.stdout)


def collect(directory,audit,expected=None,previous=None):
    identity=read_remote(audit,directory/'identity.json')
    need(identity.get('status','').startswith('PASS'),'73-file/runtime audit failed')
    row=read_remote(REMOTE+f'\nprint(json.dumps(gather({previous!r})))\n',directory/'initial.json')
    need(row['boot_id']==identity['boot_id'],'boot changed across collection')
    if expected:need(row['boot_id']==expected,'unexpected boot ID')
    timing=startup_evidence(row)
    if previous:shutdown=shutdown_evidence(row['previous_journal'])
    else:shutdown='not requested for this baseline'
    samples=[row]
    for index in range(1,7):
        time.sleep(5)
        sample=read_remote(REMOTE+'\nprint(json.dumps(snapshot()))\n',directory/f'sample-{index}.json')
        healthy(sample);samples.append(sample)
    result={'status':'PASS digital','boot_id':row['boot_id'],'timing':timing,'stability':stable(samples),'preceding_shutdown':shutdown,'files_verified':identity['files_verified'],'operator_picture_audio':'pending observation'}
    save(directory/'result.json',result)
    print(json.dumps(result),flush=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('collect','warm'))
    parser.add_argument('--root',type=Path,required=True);parser.add_argument('--label',required=True)
    parser.add_argument('--from-boot',required=True);parser.add_argument('--audit',type=Path,required=True)
    parser.add_argument('--previous-boot',help='For read-only continuation after a reboot transport disconnect')
    args=parser.parse_args()
    need(re.fullmatch(r'[a-z0-9-]+',args.label),'invalid run label')
    need(re.fullmatch(r'[0-9a-f-]{36}',args.from_boot),'invalid expected boot ID')
    if args.previous_boot:need(re.fullmatch(r'[0-9a-f-]{36}',args.previous_boot),'invalid preceding boot ID')
    audit=args.audit.read_text();directory=args.root/args.label;directory.mkdir(exist_ok=False)
    save(directory/'request.json',{'action':args.action,'expected_boot':args.from_boot,'host_utc':datetime.now(timezone.utc).isoformat()})
    if args.action=='collect':return collect(directory,audit,expected=args.from_boot,previous=args.previous_boot)
    try:
        identity=read_remote(audit,directory/'before-identity.json')
        need(identity.get('status','').startswith('PASS') and identity['boot_id']==args.from_boot,'pre-reboot audit/boot mismatch')
        before=read_remote(REMOTE+'\nprint(json.dumps(gather()))\n',directory/'before.json')
        need(before['boot_id']==args.from_boot,'pre-reboot boot changed');startup_evidence(before)
        script="from pathlib import Path\nimport subprocess\nassert Path('/proc/sys/kernel/random/boot_id').read_text().strip()=="+repr(args.from_boot)+"\nsubprocess.run(['sync'],check=True)\nsubprocess.run(['systemctl','reboot','--no-block'],check=True)\n"
        timed_out=False
        try:response=remote(script,timeout=20)
        except subprocess.TimeoutExpired as error:
            # A lost old SSH connection is not permission to resend a reset.
            # Preserve partial output, then require independent new-boot proof.
            timed_out=True
            def decoded(value):return value.decode(errors='replace') if isinstance(value,bytes) else (value or '')
            response=subprocess.CompletedProcess(SSH,255,decoded(error.stdout),decoded(error.stderr))
        save(directory/'reboot-response.json',{'returncode':response.returncode,'stdout':response.stdout,'stderr':response.stderr,'timed_out':timed_out})
        # SSH may be killed by an ordinary successful shutdown before its exit
        # status reaches the host. Never resend: observe a new boot and its
        # complete prior-shutdown evidence, or fail after the bounded deadline.
        need(response.returncode in (0,255),'reboot command failed; no automatic retry')
        if response.returncode==255:
            print('SSH closed during reboot; observing only, no command retry',flush=True)
        print('Warm reboot requested once; waiting for new boot and healthy HDMI',flush=True)
        deadline=time.monotonic()+180;attempts=[];newboot=None
        while time.monotonic()<deadline:
            response=remote(REMOTE+'\nprint(json.dumps(snapshot()))\n',timeout=30)
            attempts.append({'host_utc':datetime.now(timezone.utc).isoformat(),'returncode':response.returncode,'stdout':response.stdout,'stderr':response.stderr})
            save(directory/'readiness-attempts.json',attempts)
            if response.returncode==0:
                row=json.loads(response.stdout)
                if row['boot_id']!=args.from_boot:
                    need(newboot in (None,row['boot_id']),'multiple unexpected boots during recovery')
                    newboot=row['boot_id']
                    need(not any(u.get('ActiveState')=='failed' for u in row['services'].values()),'service failed during startup; no retry')
                    try:healthy(row)
                    except RuntimeError:pass
                    else:break
            time.sleep(3)
        else:raise RuntimeError('new healthy boot not observed within 180 seconds')
        print('New healthy boot '+newboot+'; collecting audit and 30-second stability interval',flush=True)
        return collect(directory,audit,expected=newboot,previous=args.from_boot)
    except BaseException as error:
        save(directory/'FAILED.json',{'error':str(error),'no_recovery_attempted':True})
        raise


if __name__=='__main__':main()
