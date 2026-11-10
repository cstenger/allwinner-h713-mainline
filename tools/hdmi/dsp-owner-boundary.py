#!/usr/bin/env python3
"""Explicit owner-only bench operations, ledger and immutable same-boot proof."""
import argparse,fcntl,hashlib,importlib.util,json,os,subprocess,time,tarfile
from pathlib import Path
SYS=Path('/sys/module/h713_hdmi_audio/parameters')
RUN=Path('/run/h713-owner-boundary')
STAGES={1:'census',2:'positive-lock',3:'positive-device0',6:'positive-control',7:'graph-restored',8:'graph-lock',9:'graph-device0',12:'graph-boundary',13:'config-transition',14:'config-lock',15:'config-device0',18:'config-boundary',19:'control-off',20:'control-restored',21:'control-lock',22:'control-device0',25:'complete'}
UNITS=('capture','signal','speaker')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def preflight(b):
    m=json.loads((b/'manifest.json').read_text());proof=json.loads((b/'arm-proof.json').read_text())
    assert m['schema']=='h713-owner-boundary-build-v1'
    assert proof['schema']=='h713-owner-arm-v1' and proof['arm'] in (1,2)
    assert proof['module_sha256']==m['bundle']['h713-hdmi-audio.ko'] and proof['cold_script_sha256']==m['cold_script_sha256']
    if Path('/sys/module/h713_hdmi_audio').exists():
        assert sha('/sys/module/h713_hdmi_audio/notes/.note.gnu.build-id')==m['module_note_sha256']
    assert proof['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    assert proof['manifest_sha256']==sha(b/'manifest.json')
    assert os.uname().release==m['kernel_release'] and os.uname().version==m['kernel_uts_version']
    assert Path('/proc/device-tree/chosen/h713,dsp-owner-boundary-v1').read_bytes()==bytes.fromhex('4f574e31')
    assert Path('/proc/device-tree/chosen/h713,hdmi-boot-v1').exists()
    cmdline=Path('/proc/cmdline').read_text().split()
    assert 'h713_owner_boundary=1' in cmdline and Path('/proc/sys/kernel/panic').read_text().strip()=='0'
    assert int(Path('/proc/sys/kernel/printk').read_text().split()[0])>=6
    assert sha('/usr/lib/systemd/system-shutdown/h713-hdmi-hold-guard')==m['guard_sha256']
    for n,h in m['bundle'].items():assert sha(b/n)==h,n
    assert sha(b/'firmware/h713/hdmi-audio-dsp.bin')==m['firmware_sha256']
    for unit in UNITS:
        assert 'systemd.mask=h713-hdmi-'+unit+'.service' in cmdline
        assert subprocess.run(['systemctl','is-active','h713-hdmi-'+unit+'.service'],capture_output=True,text=True).stdout.strip()=='inactive'
    for module in ('h713_hdmi_signal','h713_ddc_pins','h713_scp_probe','h713_hdmi_dsp_probe','h713_hdmi_dsp_observe','h713_hdmi_power','h713_hdmi_tvfe_hold'):
        assert not Path('/sys/module',module).exists(),module
    return m,proof

def initialize(b,proof):
    assert proof['schema']=='h713-owner-arm-v1' and proof['arm'] in (1,2) and not proof.get('verified')
    assert proof['manifest_sha256']==sha(b/'manifest.json')
    assert not (b/'arm-proof.json').exists() and not RUN.exists() and not Path('/sys/module/h713_hdmi_audio').exists()
    assert not Path('/sys/module/h713_hdmi_receiver').exists()
    proof.update(boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),verified=False)
    with (b/'arm-proof.json').open('x') as f:f.write(json.dumps(proof,indent=2)+'\n')
    m,_=preflight(b)
    original=Path('/root/hdmi-dsp-retention-2026-10-21/previous-hold-guard')
    assert sha(original)=='96f37655b33bf78d95b33fa4f431721be5a7506c73c12dcd4df58032cad27113' and original.stat().st_mode&0o7777==0o755
    RUN.mkdir();(RUN/'ledger.json').write_text(json.dumps({'boot':proof['boot_id'],'uncertain':True})+'\n')
    if proof['arm']==2:
        sham=json.loads((b/'sham-record.json').read_text());a=load(b/'analyze-dsp-owner-boundary.py','owner_analysis')
        assert a.analyze(sham)['classification']=='sham_positive_control_passed'
        assert sham['boot_id']!=proof['boot_id'] and sham['proof']['manifest_sha256']==proof['manifest_sha256']
        assert hashlib.sha256((json.dumps(sham,sort_keys=True)+'\n').encode()).hexdigest()==proof['sham_record_sha256']
    (b/'owner-arm.txt').write_text(str(proof['arm'])+'\n')
    r=subprocess.run(['python3',str(b/'h713-hdmi-session.py'),'start','--bundle',str(b),'--boot-handoff'],capture_output=True,text=True,timeout=45)
    (RUN/'initialization.log').write_text(r.stdout+r.stderr);r.check_returncode()
    assert sha('/sys/module/h713_hdmi_audio/notes/.note.gnu.build-id')==m['module_note_sha256']
    assert SYS.joinpath('owner_arm').read_text().strip()==str(proof['arm'])
    initial=json.loads(SYS.joinpath('owner_state').read_text())
    assert initial['step']==initial['attempted']==initial['failed']==initial['timeout']==initial['claimed']==initial['terminal']==0 and initial['graph_remaining']==22
    assert SYS.joinpath('graph_ready').read_text().strip()=='Y' and SYS.joinpath('dsp_failed').read_text().strip()=='N'
    baseline=json.loads(subprocess.check_output(['python3',str(b/'read-owner-census.py'),'no-reset-owner-baseline'],text=True))
    assert baseline['boot_id']==proof['boot_id'] and baseline['tv_domains_both_on'] and baseline['reads']['mips_status']=='00000001'
    assert baseline['reads']['audiotop_ctl']=='00000700' and baseline['reads']['audiotop_cfg']=='011a5e00'
    assert any('DSP versions 0000/0000' in l for l in baseline['dsp_journal']) and any('pinned 724-pair DSP patch verified versions 1/1' in l for l in baseline['dsp_journal'])
    if proof['arm']==2:
        assert sham['baseline']['reads']==baseline['reads']
        assert sham['state']['graph_saved']==json.loads(SYS.joinpath('owner_state').read_text())['graph_saved']
    (b/'baseline.json').write_text(json.dumps(baseline,indent=2)+'\n')
    proof['verified']=True;(b/'arm-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    (RUN/'ledger.json').write_text(json.dumps({'boot':proof['boot_id'],'uncertain':False})+'\n')
    print(json.dumps(proof,indent=2))

def observe(b,action,number,ack):
    m,proof=preflight(b);assert proof['verified']
    assert SYS.joinpath('owner_arm').read_text().strip()==str(proof['arm'])
    if action=='step':assert SYS.joinpath('dsp_failed').read_text().strip()=='N'
    ledger_path=RUN/'ledger.json';ledger=json.loads(ledger_path.read_text());assert ledger['boot']==proof['boot_id']
    state=json.loads(SYS.joinpath('owner_state').read_text());assert state['arm']==proof['arm']
    if action=='step':
        assert not ledger['uncertain'] and not state['failed'] and not state['terminal'] and number==state['step']+1
        if state['step'] in STAGES:
            assert ack==STAGES[state['step']] and ledger.get('snapshot')==state['step'] and ledger.get('state_hash')==hashlib.sha256(json.dumps(state,sort_keys=True).encode()).hexdigest()
        ledger['uncertain']=True;ledger_path.write_text(json.dumps(ledger)+'\n')
        print(json.dumps({'event':'before-step','boot':proof['boot_id'],'number':number}),flush=True)
        SYS.joinpath('owner_step').write_text(str(number)+'\n')
        state=json.loads(SYS.joinpath('owner_state').read_text());assert state['step']==number and not state['failed']
        ledger['uncertain']=False;ledger_path.write_text(json.dumps(ledger)+'\n')
    journal=subprocess.check_output(['journalctl','_BOOT_ID='+proof['boot_id'].replace('-',''),'_TRANSPORT=kernel','--no-pager','-o','cat'],text=True)
    record={'boot_id':proof['boot_id'],'proof':proof,'state':state,'baseline':json.loads((b/'baseline.json').read_text()),'preflight_valid':not state['failed'] and not ledger['uncertain'],'monotonic_ns':time.monotonic_ns(),'journal':journal}
    if action=='snapshot':
        if not state['failed'] and not ledger['uncertain']:
            record['debug']={n:Path(p).read_text() for n,p in {'clocks':'/sys/kernel/debug/clk/clk_summary','domains':'/sys/kernel/debug/pm_genpd/pm_genpd_summary'}.items()}
        ledger.update(snapshot=state['step'],state_hash=hashlib.sha256(json.dumps(state,sort_keys=True).encode()).hexdigest());ledger_path.write_text(json.dumps(ledger)+'\n')
        (RUN/('snapshot-%02d.json'%state['step'])).write_text(json.dumps(record,indent=2)+'\n')
    record['analysis']=load(b/'analyze-dsp-owner-boundary.py','owner_analysis').analyze(record)
    print(json.dumps(record,indent=2))

def finish(b,action,export_sha):
    m,proof=preflight(b);assert proof['verified']
    state=json.loads(SYS.joinpath('owner_state').read_text())
    ledger=json.loads((RUN/'ledger.json').read_text())
    assert state['terminal'] and not state['failed'] and not state['claimed']
    assert ledger['boot']==proof['boot_id'] and not ledger['uncertain'] and ledger['snapshot']==state['step']
    assert ledger['state_hash']==hashlib.sha256(json.dumps(state,sort_keys=True).encode()).hexdigest()
    archive=Path('/run/h713-owner-boundary-export.tar.gz')
    if action=='export':
        journal=subprocess.check_output(['journalctl','_BOOT_ID='+proof['boot_id'].replace('-',''),'_TRANSPORT=kernel','--no-pager','-o','cat'])
        (RUN/'final-journal.txt').write_bytes(journal)
        (RUN/'final-state.json').write_text(json.dumps(state,indent=2)+'\n')
        with tarfile.open(archive,'x:gz') as t:
            t.add(RUN,arcname='board-export')
            for name in ('arm-proof.json','baseline.json','manifest.json'):t.add(b/name,arcname=name)
        print(json.dumps({'boot_id':proof['boot_id'],'archive':str(archive),'size':archive.stat().st_size,'sha256':sha(archive)}))
    else:
        assert export_sha and export_sha==sha(archive)
        print('H713_OWNER_BOUNDARY_POWEROFF boot='+proof['boot_id'],flush=True)
        subprocess.run(['sync'],check=True);subprocess.run(['systemctl','poweroff'],check=True)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',required=True,type=Path);p.add_argument('action',choices=('initialize','snapshot','step','export','poweroff'));p.add_argument('--intent',type=Path);p.add_argument('--export-sha256');p.add_argument('--number',type=int);p.add_argument('--stage-ack');a=p.parse_args()
    with (a.bundle/'host.lock').open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if a.action=='initialize':initialize(a.bundle,json.loads(a.intent.read_text()))
        elif a.action in ('export','poweroff'):finish(a.bundle,a.action,a.export_sha256)
        else:observe(a.bundle,a.action,a.number,a.stage_ack)
if __name__=='__main__':main()
