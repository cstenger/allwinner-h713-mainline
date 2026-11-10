import hashlib,importlib.util,json,pathlib,re
p=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('analyzer',pathlib.Path('tools/hdmi/analyze-dsp-owner-boundary.py'));a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
r=json.loads((p/'board-export/snapshot-25.json').read_text());sham=json.loads((p/'cold-boot/sham-record.json').read_text());s=r['state'];u=(p/'steps-uart.log').read_text();cold=(p/'cold-catch/serial.log').read_text();boot=(p/'cold-boot/serial.log').read_text(errors='replace');ledger=json.loads((p/'board-export/ledger.json').read_text());matched=a.compare(sham,r)
assert matched['classification']=='matched_tested_shutdown_boundaries_preserved_patch'
assert r['boot_id']==r['proof']['boot_id']==r['baseline']['boot_id']==ledger['boot']=='77d7afff-6ff8-4629-961d-1fa56dc3015d'
assert not ledger['uncertain'] and ledger['snapshot']==25 and ledger['state_hash']==hashlib.sha256(json.dumps(s,sort_keys=True).encode()).hexdigest()
assert re.findall(r'H713 OWNER step=(\d+) BEGIN',u)==re.findall(r'H713 OWNER step=(\d+) DONE',u)==list(map(str,range(1,26)))
for event in ('BUSY_WAIT','COMMAND_WRITE_BEGIN','COMMAND_SENT','DONE_WAIT','COMPLETE'):
 assert re.findall(r'H713 OWNER pair=(\d) dev=(\d) '+event,u)==[(str(i),str(d)) for i in range(4) for d in range(2)]
addresses=['0003','800c','800d','00ac','0077','004d','805a','8059','0130','0012','0017','801a','8017','007c','007d','007e','8102','8103','0102','0103','0059','005a']
expected=list(zip(reversed(addresses),[f'{v:04x}' for v in reversed(s['graph_saved'])]))
assert re.findall(r'H713 OWNER graph-restore address=([0-9a-f]{4}) value=([0-9a-f]{4}) verified',u)==expected
assert u.index('H713 OWNER step=7 BEGIN')<u.index('H713 OWNER graph-restore')<u.index('H713 OWNER step=7 DONE')
for n in range(1,26):
 x=json.loads((p/f'step-{n:02}.json').read_text());t=x['state']
 assert x['preflight_valid'] and t['step']==n and not t['failed'] and not t['timeout'] and t['arm']==2
 assert t['ctl']==(0 if n==19 else 0x700) and t['cfg']==(0x011a5e00 if n<13 else 0) and t['graph_remaining']==(22 if n<7 else 0) and t['graph_saved']==sham['state']['graph_saved']
assert cold.count('U-Boot SPL ')==1 and 'U-Boot SPL ' not in boot and 'U-Boot SPL ' not in u
assert boot.count('H713 HDMI cold startup handoff verified')==1 and boot.count('worker-new=00000003')==1 and boot.count('transition-complete=1')==1
assert 'pinned 724-pair DSP patch verified versions 1/1' in u and not re.search(r'H713 OWNER.*(?:TIMEOUT|SKIPPED|FAIL)',u)
assert 'reboot: Power down' in u and 'poweroff with HDMI holds retained' in u and 'CLOSE' in (p/'steps-uart-events.log').read_text()
meta=json.loads((p/'export.log').read_text());archive=(p/'board-export.tar.gz').read_bytes();assert len(archive)==meta['size'] and hashlib.sha256(archive).hexdigest()==meta['sha256']
out={'result':'PASS','matched_analysis':matched,'boot_id':r['boot_id'],'baseline_reads_match':True,'graph_saved_match':True,'ordered_steps':25,'sent_completed_requests':8,'verified_graph_restores':22,'AudioTop_sequence':'700/011a5e00 -> 700/0 -> 0/0 -> 700/0','ledger_certain':True,'export_sha256':meta['sha256'],'export_size':meta['size'],'power_down':'274.472661','recorder_closed':True}
(p/'validation.json').write_text(json.dumps(out,indent=2)+'\n');(p/'analysis.json').write_text(json.dumps(a.analyze(r),indent=2)+'\n');(p/'matched-analysis.json').write_text(json.dumps(matched,indent=2)+'\n');print(json.dumps(out,indent=2))
