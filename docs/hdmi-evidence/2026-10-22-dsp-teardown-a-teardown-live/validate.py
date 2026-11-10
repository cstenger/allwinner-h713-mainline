# Run from repository root: checks the matched teardown evidence independently of the helper.
import json,re,hashlib,pathlib,importlib.util
R=pathlib.Path(__file__).resolve().parent;SHAM=R.parent/'2026-10-22-dsp-teardown-a-sham-live/board-export/snapshot-37.json'
s=importlib.util.spec_from_file_location('a','tools/hdmi/analyze-dsp-teardown-a.py');a=importlib.util.module_from_spec(s);s.loader.exec_module(a)
rec=json.loads((R/'board-export/snapshot-37.json').read_text());host=json.loads((R/'snapshot-37.json').read_text());sham=json.loads(SHAM.read_text())
out={'classification':a.analyze(rec)['classification'],'matched':a.compare(sham,rec)['classification']}
out['host_matches_board_state']=host['state']==rec['state']
out['sham_bytes_staged_equal']=(R/'cold-boot/sham-record.json').read_bytes()==SHAM.read_bytes()
uart=(R/'steps-uart.log').read_bytes().decode(errors='replace')
begin=[int(x) for x in re.findall(r'H713 TEARDOWN step=(\d+) BEGIN arm=2',uart)];done=[int(x) for x in re.findall(r'H713 TEARDOWN step=(\d+) DONE',uart)]
out['uart_begin_done_ordered']=begin==done==list(range(1,38))
out['uart_complete_requests']=len(re.findall(r'COMPLETE status=00000120 response=00000001',uart))
out['uart_graph_restores']=len(re.findall(r'graph-restore address=\w+ value=\w+ verified',uart))
out['uart_spdi_restore']=re.findall(r'spdi-restore [^\r\n]*',uart)
out['uart_bridge_restore']=re.findall(r'bridge-restore [^\r\n]*',uart)
out['uart_order']=uart.find('graph-restore')<uart.find('spdi-restore')<uart.find('bridge-restore')<uart.find('step=26 BEGIN')
out['uart_no_failure']=not re.search(r'FAILED|TIMEOUT|SKIPPED',uart)
out['uart_power_down']='reboot: Power down' in uart
j=rec['journal'];out['journal_initial_zero_then_patch']=0<=j.find('DSP versions 0000/0000')<j.find('pinned 724-pair DSP patch verified versions 1/1')
cold=(R/'cold-boot/serial.log').read_bytes().decode(errors='replace')
out['cold_handoff']=cold.count('H713 HDMI cold startup handoff verified')==1 and cold.count('H713 panel 720p timing re-latched after source 3')==1 and cold.count('Starting kernel')==1
m=json.loads((R/'export-verified.json').read_text());out['export_sha_verified']=hashlib.sha256((R/'board-export.tar.gz').read_bytes()).hexdigest()==m['sha256']
out['boot_distinct_from_sham']=rec['boot_id']!=sham['boot_id']
print(json.dumps(out,indent=1));(R/'validation.json').write_text(json.dumps(out,indent=1)+'\n')
