#!/usr/bin/env python3
"""Host side of one Phase B cold cycle. Each action runs once; nothing retries.

  health-stage  verify fresh board boot, owners absent; stage exact bundle
  initialize    remote initialize (60 s deadline)
  uart          sole UART recorder until RUN/stop-steps-uart exists
  step N ACK    one remote step (20 s deadline); snapshot likewise
  export        export, fetch, verify host checksum, extract
  poweroff      checked poweroff using the verified export checksum
"""
import argparse,hashlib,io,json,os,pathlib,select,subprocess,sys,tarfile,time
ROOT=pathlib.Path(__file__).resolve().parents[2]
CANDIDATE=ROOT/'build/hdmi-dsp-teardown-b-2026-10-23/candidate'
REMOTE='/root/hdmi-dsp-teardown-b-2026-10-23/'
SSH=['ssh','-F','/dev/null','-o','BatchMode=yes','-o','ConnectTimeout=5','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=1','root@192.168.4.1']
PREVIOUS_BOOTS=('dcfe762c-9cb5-44ca-a546-049f03e2a1fd','77d7afff-6ff8-4629-961d-1fa56dc3015d','7397c984-778a-455a-925d-44f060e5ad33','835e0bf5-fc43-4269-9740-58d153feef99')
HEALTH=r'''
import pathlib,os,hashlib,subprocess,json,sys
P=pathlib.Path
boot=P('/proc/sys/kernel/random/boot_id').read_text().strip()
assert boot not in json.loads(sys.argv[1])
assert os.uname().release=='6.18.38' and os.uname().version=='#1 SMP Fri Oct 16 15:44:49 PDT 2026'
cmd=P('/proc/cmdline').read_text().split();assert 'panic=0' in cmd and 'h713_teardown_b=1' in cmd and 'h713_teardown_a=1' not in cmd and 'h713_owner_boundary=1' not in cmd
assert P('/proc/sys/kernel/panic').read_text().strip()=='0'
assert P('/proc/device-tree/chosen/h713,dsp-teardown-b-v1').read_bytes()==bytes.fromhex('54445242')
h=P('/proc/device-tree/chosen/h713,hdmi-boot-v1').read_bytes();assert len(h)==12 and h[:4]==bytes.fromhex('48444d49') and int.from_bytes(h[4:8],'big')==0 and int.from_bytes(h[8:12],'big')>0
for u in ('capture','signal','speaker'):
 n='h713-hdmi-'+u+'.service';assert 'systemd.mask='+n in cmd
 assert subprocess.run(['systemctl','is-active',n],capture_output=True,text=True).stdout.strip()=='inactive'
for n in ('h713_hdmi_audio','h713_hdmi_receiver','h713_hdmi_signal','h713_ddc_pins','h713_scp_probe','h713_hdmi_dsp_probe','h713_hdmi_dsp_observe','h713_hdmi_power','h713_hdmi_tvfe_hold'):assert not P('/sys/module',n).exists(),n
sha=lambda p:hashlib.sha256(P(p).read_bytes()).hexdigest()
assert sha('/usr/lib/systemd/system-shutdown/h713-hdmi-hold-guard')=='5ad26677ac791d2be659db88165d689d997705f45ee4d516015e786342ad764d'
bak=P('/root/hdmi-dsp-retention-2026-10-21/previous-hold-guard');assert sha(bak)=='96f37655b33bf78d95b33fa4f431721be5a7506c73c12dcd4df58032cad27113' and bak.stat().st_mode&0o7777==0o755
assert not P('/run/h713-teardown-b').exists()
subprocess.run(['dmesg','-n','7'],check=True)
assert int(P('/proc/sys/kernel/printk').read_text().split()[0])==7
b=P(sys.argv[2]);b.mkdir(parents=True,exist_ok=False)
print(json.dumps({'boot_id':boot,'uname_version':os.uname().version,'cmdline':cmd,'owners_absent':True,'services_masked_inactive':True,'guard_original_backup_verified':True,'remote_bundle_directory':str(b)}))
'''
def create(path,data):
    """Write a new evidence file; an existing one means this action already ran."""
    with path.open('xb' if isinstance(data,bytes) else 'x') as f:f.write(data)
def decode(v):return v.decode(errors='replace') if isinstance(v,bytes) else (v or '')
def remote(run,name,command,timeout,data=None):
    """One SSH call. A deadline is uncertain and is recorded; never retried."""
    try:r=subprocess.run(SSH+[command],input=data,capture_output=True,timeout=timeout)
    except subprocess.TimeoutExpired as e:
        create(run/(name+'-uncertain.log'),decode(e.stdout)+decode(e.stderr)+'\nHOST DEADLINE: uncertain, no retry\n')
        raise SystemExit('HOST DEADLINE: uncertain, no retry')
    create(run/(name+'.log'),r.stdout+r.stderr)
    if r.returncode:print(decode(r.stdout)+decode(r.stderr));raise SystemExit(r.returncode)
    return r.stdout
def bundle(run):return REMOTE+run.name
def helper(run,args):return 'python3 '+bundle(run)+'/dsp-teardown-b.py --bundle '+bundle(run)+' '+args
def health_stage(run):
    plan=json.loads((run/'capture-plan.json').read_text());boot=run/'cold-boot'
    out=remote(run,'cold-health','python3 - '+"'"+json.dumps(PREVIOUS_BOOTS)+"' "+bundle(run),20,HEALTH.encode())
    print(decode(out))
    buf=io.BytesIO()
    with tarfile.open(fileobj=buf,mode='w') as t:
        for f in (CANDIDATE/'bundle').rglob('*'):
            if f.is_file():t.add(f,arcname=str(f.relative_to(CANDIDATE/'bundle')))
        t.add(boot/'arm-intent.json',arcname='arm-intent.json')
        if plan['arm']==2:t.add(boot/'sham-record.json',arcname='sham-record.json')
    remote(run,'stage','tar -x -C '+bundle(run),20,buf.getvalue());print('Exact bundle plus fresh intent staged')
def uart(run,port):
    sys.path.insert(0,str(ROOT/'tools/serial'));from console import open_port
    fd=open_port(port)
    try:
        with (run/'steps-uart.log').open('xb',buffering=0) as raw,(run/'steps-uart-events.log').open('x',buffering=1) as events:
            events.write('OPEN '+port+' monotonic='+str(time.monotonic())+'\n')
            end=time.monotonic()+2400
            while time.monotonic()<end and not (run/'stop-steps-uart').exists():
                if select.select([fd],[],[],1)[0]:
                    b=os.read(fd,65536)
                    if not b:raise RuntimeError('UART lost; no reconnect')
                    raw.write(b)
            events.write('CLOSE monotonic='+str(time.monotonic())+'\n')
    finally:os.close(fd)
def observe(run,action,number,ack):
    if action=='step':
        name='step-%02d'%number;args='step --number %d'%number+(' --stage-ack '+ack if ack else '')
    else:name='snapshot-pending';args='snapshot'
    out=decode(remote(run,name,helper(run,args),20))
    if action=='step':
        event,end=json.JSONDecoder().raw_decode(out);assert event['event']=='before-step' and event['number']==number;record=json.loads(out[end:])
    else:
        record=json.loads(out);name='snapshot-%02d'%record['state']['step'];(run/'snapshot-pending.log').rename(run/(name+'.log'))
    create(run/(name+'.json'),json.dumps(record,indent=2)+'\n')
    s=record['state']
    print(json.dumps({'state':{k:s[k] for k in ('arm','step','failed','timeout','claimed','terminal','requests','ctl','cfg','graph_remaining')},'pairs_seen':[{'pair':i,**x} for i,x in enumerate(s['pairs']) if any(x['phase'])],'ctx_writes':{k:s['ctx'][k] for k in ('spdi_writes','bridge_writes','at_writes','gate')},'tv':{k:s['tv'][k] for k in ('state','offs','ons','resets','writes')},'preflight_valid':record['preflight_valid'],'analysis':record['analysis']}))
def export(run):
    m=json.loads(remote(run,'export',helper(run,'export'),20));print(m)
    data=subprocess.run(SSH+['cat '+m['archive']],capture_output=True,timeout=20)
    assert data.returncode==0 and len(data.stdout)==m['size'] and hashlib.sha256(data.stdout).hexdigest()==m['sha256']
    a=run/'board-export.tar.gz';create(a,data.stdout)
    with tarfile.open(a) as t:t.extractall(run,filter='data')
    create(run/'export-verified.json',json.dumps(m,indent=2)+'\n');print('Host archive verified and extracted')
def poweroff(run):
    m=json.loads((run/'export-verified.json').read_text())
    assert hashlib.sha256((run/'board-export.tar.gz').read_bytes()).hexdigest()==m['sha256']
    try:r=subprocess.run(SSH+[helper(run,'poweroff --export-sha256 '+m['sha256'])],capture_output=True,timeout=20)
    except subprocess.TimeoutExpired as e:r=e
    create(run/'poweroff.log',(getattr(r,'stdout',b'') or b'')+(getattr(r,'stderr',b'') or b''))
    print('Poweroff requested; confirm UART reboot: Power down before closing the recorder')
def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--run',required=True,type=pathlib.Path);p.add_argument('action',choices=('health-stage','initialize','uart','step','snapshot','export','poweroff'))
    p.add_argument('number',nargs='?',type=int);p.add_argument('ack',nargs='?');p.add_argument('--port',default='/dev/ttyUSB0')
    a=p.parse_args();run=a.run.resolve();assert (run/'capture-plan.json').is_file()
    if a.action=='health-stage':health_stage(run)
    elif a.action=='initialize':print(decode(remote(run,'initialize',helper(run,'initialize --intent '+bundle(run)+'/arm-intent.json'),60)))
    elif a.action=='uart':uart(run,a.port)
    elif a.action in ('step','snapshot'):observe(run,a.action,a.number,a.ack)
    elif a.action=='export':export(run)
    else:poweroff(run)
if __name__=='__main__':main()
