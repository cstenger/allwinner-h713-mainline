import hashlib,importlib.util,json,pathlib,re
p=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('analyzer',pathlib.Path('tools/hdmi/analyze-dsp-owner-boundary.py'));a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
r=json.loads((p/'board-export/snapshot-25.json').read_text());s=r['state'];u=(p/'steps-uart.log').read_text();cold=(p/'cold-catch/serial.log').read_text();boot=(p/'cold-boot/serial.log').read_text();ledger=json.loads((p/'board-export/ledger.json').read_text())
assert a.analyze(r)['classification']=='sham_positive_control_passed'
assert r['boot_id']==r['proof']['boot_id']==r['baseline']['boot_id']==ledger['boot']=='dcfe762c-9cb5-44ca-a546-049f03e2a1fd'
assert not ledger['uncertain'] and ledger['snapshot']==25 and ledger['state_hash']==hashlib.sha256(json.dumps(s,sort_keys=True).encode()).hexdigest()
assert re.findall(r'H713 OWNER step=(\d+) BEGIN',u)==re.findall(r'H713 OWNER step=(\d+) DONE',u)==list(map(str,range(1,26)))
for event in ('BUSY_WAIT','COMMAND_WRITE_BEGIN','COMMAND_SENT','DONE_WAIT','COMPLETE'):
    assert re.findall(r'H713 OWNER pair=(\d) dev=(\d) '+event,u)==[(str(i),str(d)) for i in range(4) for d in range(2)]
assert len(s['graph_saved'])==22
for n in range(1,26):
    x=json.loads((p/f'step-{n:02}.json').read_text());t=x['state']
    assert x['preflight_valid'] and t['step']==n and not t['failed'] and not t['timeout'] and t['arm']==1
    assert t['ctl']==0x700 and t['cfg']==0x011a5e00 and t['graph_remaining']==22 and t['graph_saved']==s['graph_saved']
assert cold.count('U-Boot SPL ')==1 and 'U-Boot SPL ' not in boot and 'U-Boot SPL ' not in u
assert boot.count('H713 HDMI cold startup handoff verified')==1
assert boot.count('worker-new=00000003')==1 and boot.count('transition-complete=1')==1
assert 'pinned 724-pair DSP patch verified versions 1/1' in u
assert not re.search(r'H713 OWNER.*(?:TIMEOUT|SKIPPED|FAIL)',u)
assert 'reboot: Power down' in u and 'poweroff with HDMI holds retained' in u
assert 'CLOSE' in (p/'steps-uart-events.log').read_text()
meta=json.loads((p/'export.log').read_text());archive=(p/'board-export.tar.gz').read_bytes()
assert len(archive)==meta['size'] and hashlib.sha256(archive).hexdigest()==meta['sha256']
out={'result':'PASS','analysis':a.analyze(r),'boot_id':r['boot_id'],'ordered_steps':25,'sent_completed_requests':8,'AudioTop':'00000700/011a5e00 throughout measured steps','graph_remaining':22,'ledger_certain':True,'export_sha256':meta['sha256'],'export_size':meta['size'],'sham_record_canonical_sha256':hashlib.sha256((json.dumps(r,sort_keys=True)+'\n').encode()).hexdigest(),'power_down':'414.276830','recorder_closed':True}
(p/'validation.json').write_text(json.dumps(out,indent=2)+'\n');(p/'analysis.json').write_text(json.dumps(a.analyze(r),indent=2)+'\n');print(json.dumps(out,indent=2))
