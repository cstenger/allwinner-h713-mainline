#!/usr/bin/env python3
"""One-shot cold-U-Boot to runtime-only HDMI audio service coordinator.

No flashing, saved environment, reboot or warm MIPS launch. The operator must
physically cold-cycle and stop at U-Boot before invoking with the explicit flag.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BASE='/tmp/h713-linux-return'
SSH=['ssh','-F','/dev/null','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=5','root@192.168.4.1']
SCP=['scp','-F','/dev/null','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=5']
FIT_SIZE=7789772
FDT_SIZE=0x84f5
FILES=[('modules/hdmi-receiver/h713-hdmi-receiver.ko','h713-hdmi-receiver.ko'),('modules/hdmi-audio/h713-hdmi-audio.ko','h713-hdmi-audio.ko'),('tools/mips/read-comm-trace.py','read-comm-trace.py'),('tools/mips/mips-shell.py','mips-shell.py'),('tools/hdmi/h713-hdmi-session.py','h713-hdmi-session.py'),('tools/hdmi/h713-hdmi-capture.service','h713-hdmi-capture.service'),('tools/hdmi/h713-hdmi-capture-shutdown.conf','h713-hdmi-capture-shutdown.conf'),('build/hdmi-alsa-utils/usr/bin/aplay','arecord'),('docs/hdmi-evidence/2026-10-07-android-audio/audio-dsp-patch.bin','firmware/h713/hdmi-audio-dsp.bin')]


def require(condition,message):
    if not condition:raise RuntimeError(message)


def live_pid(text):
    rows=re.findall(r'chan=([0-9a-f]+) pid=([0-9a-f]+)[^\n]*<== LIVE',text)
    require(len(rows)==1 and int(rows[0][0],16)==0 and int(rows[0][1],16)!=0,'expected one live channel0 PID')
    return rows[0][1]


def variable(text,name):
    values=re.findall(r'^'+re.escape(name)+r'=(?:0x)?([0-9a-fA-F]+)\s*$',text,re.M)
    require(len(values)==1,'missing/ambiguous RAM FDT variable: '+name)
    return int(values[0],16)


class Serial:
    def __init__(self,out,port):self.out=out;self.port=port;self.index=0
    def call(self,command,timeout=20):
        self.index+=1
        p=subprocess.run([sys.executable,str(ROOT/'tools/serial/console.py'),'--port',self.port,'--wait','1',command],capture_output=True,text=True,timeout=timeout)
        text=p.stdout+p.stderr
        (self.out/f'{self.index:02d}-serial.log').write_text(text)
        require(p.returncode==0,'serial command failed; inspect log')
        if not command.startswith('bootm '):require(text.rstrip().endswith('=>'),'U-Boot prompt missing; refusing further commands')
        return text


def boot(serial,mark_attempted,park_capable=False):
    require('U-Boot 2026.07-rc5' in serial.call('version'),'unexpected bootloader or not at U-Boot')
    state=serial.call('md.l 0x0306101c 1')
    values=re.findall(r'^0306101c:\s+([0-9a-fA-F]{8})',state,re.M)
    require(len(values)==1 and int(values[0],16)==0,'MIPS is not exactly parked on the confirmed cold boot')
    mark_attempted()  # Never retry a MIPS launch after this point.
    started=serial.call('h713_disp mips-comm-trace 0x34')
    require('firmware identity accepted' in started and 'firmware readiness proven by MIPS READY' in started and 'application readiness proven' in started,'MIPS launch/readiness failed; cold boot required')
    pid=live_pid(serial.call('h713_disp commdev'))
    response=serial.call(f'h713_disp commcall eaf13de5 chan=0 pid={pid} 3')
    require('MIPS sender completed RETURN' in response and 'RETURN_ACK publication consumed' in response,'source3 IPC completion failed')
    trace=serial.call('h713_disp commtrace')
    require('transition-complete=1' in trace and 'worker-new=00000003' in trace,'source3 worker transition not complete')
    return ram_boot(serial,pid,park_capable)


def ram_boot(serial,pid,park_capable=False):
    fit=serial.call('fatload mmc 1:2 0x50000000 h713-kernel.fit')
    require(re.search(r'^'+str(FIT_SIZE)+r' bytes read',fit,re.M),'unexpected FIT size/load failure')
    serial.call('fdt addr 0x50000000')
    serial.call('fdt get size hdmi_trial_fdt_size /images/fdt-1 data')
    require(variable(serial.call('printenv hdmi_trial_fdt_size'),'hdmi_trial_fdt_size')==FDT_SIZE,'unexpected FIT FDT size')
    serial.call('fdt get addr hdmi_trial_fdt /images/fdt-1 data')
    pointer=variable(serial.call('printenv hdmi_trial_fdt'),'hdmi_trial_fdt')
    require(0x50000000<=pointer and pointer+FDT_SIZE<=0x50000000+FIT_SIZE,'FDT data outside loaded FIT')
    serial.call('cp.b ${hdmi_trial_fdt} 0x4f000000 ${hdmi_trial_fdt_size}')
    serial.call('fdt addr 0x4f000000')
    serial.call('fdt resize 0x1000')
    serial.call('fdt set /soc/audio-bridge@203042c interrupts <0 115 4 0 113 4>')
    irq=serial.call('fdt print /soc/audio-bridge@203042c interrupts')
    require(re.search(r'<0x00000000 0x00000073 0x00000004 0x00000000 0x00000071 0x00000004>',irq),'RAM audio IRQ correction not verified')
    if park_capable:
        serial.call('fdt get value hdmi_shutdown_ccu /soc/clock-controller@2001000 phandle')
        phandle=variable(serial.call('printenv hdmi_shutdown_ccu'),'hdmi_shutdown_ccu')
        require(0 < phandle < 0xffffffff,'invalid CCU phandle')
        serial.call('fdt mknode /soc hdmi-mips-shutdown')
        serial.call('fdt set /soc/hdmi-mips-shutdown compatible h713,hdmi-mips-shutdown-bench')
        serial.call('fdt set /soc/hdmi-mips-shutdown resets <${hdmi_shutdown_ccu} 1 ${hdmi_shutdown_ccu} 2 ${hdmi_shutdown_ccu} 3>')
        serial.call('fdt set /soc/hdmi-mips-shutdown clocks <${hdmi_shutdown_ccu} 19 ${hdmi_shutdown_ccu} 20>')
        for name,ids in [('resets',(1,2,3)),('clocks',(19,20))]:
            actual=serial.call('fdt print /soc/hdmi-mips-shutdown '+name)
            expected='<'+' '.join(f'0x{value:08x}' for index in ids for value in (phandle,index))+'>'
            require(expected in actual,'shutdown consumer '+name+' verification failed')
    output=serial.call('bootm 0x50000000 - 0x4f000000',timeout=35)
    require('Linux version 6.18.38' in output,'expected Linux boot identity missing')
    return {'pid':pid,'source3_verified':True,'fit_bytes':FIT_SIZE,'fdt_bytes':FDT_SIZE,'park_capable':park_capable}


def resume(serial,prior):
    # Only resume the pre-Linux size-guard failure, with its original cold proof.
    require((prior/'mips-launch-attempted').is_file(),'missing original launch marker')
    previous=json.loads((prior/'result.json').read_text())
    require(previous.get('error')=='unexpected FIT FDT size' and previous.get('pass') is False,'resume only supports the pre-Linux FDT size guard')
    logs=[(prior/f'{i:02d}-serial.log').read_text() for i in range(1,11)]
    require(re.search(r'^0306101c:\s+00000000',logs[1],re.M),'original parked proof missing')
    require(all(x in logs[2] for x in ['firmware identity accepted','firmware readiness proven by MIPS READY','application readiness proven']),'original launch proof missing')
    pid=live_pid(logs[3])
    require('MIPS sender completed RETURN' in logs[4] and 'RETURN_ACK publication consumed' in logs[4],'original IPC proof missing')
    require('transition-complete=1' in logs[5] and 'worker-new=00000003' in logs[5],'original source proof missing')
    require('U-Boot 2026.07-rc5' in serial.call('version'),'not at expected U-Boot')
    state=serial.call('md.l 0x0306101c 1')
    require(re.search(r'^0306101c:\s+00000001',state,re.M),'MIPS no longer live')
    require(live_pid(serial.call('h713_disp commdev'))==pid,'live PID changed')
    trace=serial.call('h713_disp commtrace')
    require('transition-complete=1' in trace and 'worker-new=00000003' in trace,'current source3 proof missing')
    result=ram_boot(serial,pid)
    result['resumed_from']=str(prior.resolve())
    return result


def configure_service(remote,park_capable):
    if park_capable:
        remote(f'set -e; mkdir -p /run/systemd/system/h713-hdmi-capture.service.d; cp {BASE}/h713-hdmi-capture-shutdown.conf /run/systemd/system/h713-hdmi-capture.service.d/10-terminal-shutdown.conf','stage-shutdown.log')
    else:
        remote('test ! -e /run/systemd/system/h713-hdmi-capture.service.d/10-terminal-shutdown.conf','capture-only-check.log')
    remote(f'set -e; chmod +x {BASE}/arecord; cp {BASE}/h713-hdmi-capture.service /run/systemd/system/; systemd-analyze verify /run/systemd/system/h713-hdmi-capture.service; systemctl daemon-reload; systemctl start h713-hdmi-capture.service; systemctl is-active h713-hdmi-capture.service; python3 {BASE}/h713-hdmi-session.py status; dmesg | tail -40','service-start.log',timeout=70)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--cold-boot-confirmed',action='store_true',required=True)
    parser.add_argument('--port',default='auto')
    parser.add_argument('--park-capable',action='store_true',help='Add a RAM-only CCU reset/clock consumer for terminal parking tests')
    parser.add_argument('--resume-size-guard',type=Path)
    args=parser.parse_args()
    require(not (args.park_capable and args.resume_size_guard),'parking DT opt-in requires uninterrupted cold path')
    for local,_ in FILES:require((ROOT/local).is_file(),'missing local staging file: '+local)
    patch=(ROOT/'docs/hdmi-evidence/2026-10-07-android-audio/audio-dsp-patch.bin').read_bytes()
    require(len(patch)==2896 and hashlib.sha256(patch).hexdigest()=='8e31db199e0078d142f622436ff0b7249b333dbb6df8ec3fbabc0d8fea6ea0c5','local firmware hash/size mismatch')
    args.output.mkdir(parents=True,exist_ok=False)
    result={'pass':False}
    def run(argv,name,timeout=30,check=True):
        p=subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
        (args.output/name).write_text(p.stdout+p.stderr)
        if check:require(p.returncode==0,f'command failed; see {name}')
        return p
    def remote(command,name,**kwargs):return run(SSH+[command],name,**kwargs)
    try:
        serial=Serial(args.output,args.port)
        if args.resume_size_guard:
            result.update(resume(serial,args.resume_size_guard))
        else:
            result.update(boot(serial,lambda:(args.output/'mips-launch-attempted').write_text('Cold boot required before another launch.\n'),park_capable=args.park_capable))
        run(['nmcli','connection','up','spirits'],'wifi.log',timeout=35,check=False)
        deadline=time.monotonic()+90
        while True:
            p=remote('uname -r','ssh-ready.log',check=False)
            if p.returncode==0:break
            require(time.monotonic()<deadline,'Linux SSH readiness deadline exceeded')
            run(['nmcli','connection','up','spirits'],'wifi-retry.log',timeout=20,check=False)
            time.sleep(1)
        remote(f'set -e; test "$(uname -r)" = 6.18.38; grep -q "HY200 QZ713DF_A1" /proc/device-tree/model; test ! -d /sys/module/h713_hdmi_audio; test ! -f /run/systemd/system/h713-hdmi-capture.service; mkdir -p {BASE}/firmware/h713','identity.log')
        files=FILES
        for index,(local,name) in enumerate(files):run(SCP+[str(ROOT/local),'root@192.168.4.1:'+BASE+'/'+name],f'stage-{index}.log')
        boot_id=remote('cat /proc/sys/kernel/random/boot_id','boot-id.txt').stdout.strip()
        require(re.fullmatch(r'[0-9a-f-]{36}',boot_id),'invalid Linux boot ID')
        proof=args.output/'cold-boot-proof.json'
        proof.write_text(json.dumps({'boot_id':boot_id,'cold_boot_confirmed':True,'parked_status_before_launch':0,'source3_verified':True,'pid':result['pid']})+'\n')
        run(SCP+[str(proof),'root@192.168.4.1:'+BASE+'/cold-boot-proof.json'],'stage-proof.log')
        configure_service(remote,args.park_capable)
        result['pass']=True;result['runtime_service']='active';result['terminal_shutdown_ordered']=args.park_capable
    except Exception as error:
        result['error']=str(error)
        raise
    finally:(args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)


if __name__=='__main__':
    try:main()
    except Exception as error:sys.exit(str(error))
