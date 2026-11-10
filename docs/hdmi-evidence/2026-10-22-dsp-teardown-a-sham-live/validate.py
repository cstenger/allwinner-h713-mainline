# Run from repository root: checks the sham evidence independently of the helper.
import json,re,hashlib,pathlib,importlib.util
R=pathlib.Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('a','tools/hdmi/analyze-dsp-teardown-a.py');a=importlib.util.module_from_spec(s);s.loader.exec_module(a)
rec=json.loads((R/'board-export/snapshot-37.json').read_text());host=json.loads((R/'snapshot-37.json').read_text())
out={'classification':a.analyze(rec)['classification']}
out['host_matches_board_state']=host['state']==rec['state']
uart=(R/'steps-uart.log').read_bytes().decode(errors='replace')
begin=[int(x) for x in re.findall(r'H713 TEARDOWN step=(\d+) BEGIN arm=1',uart)];done=[int(x) for x in re.findall(r'H713 TEARDOWN step=(\d+) DONE',uart)]
out['uart_begin_done_ordered']=begin==done==list(range(1,38))
out['uart_complete_requests']=len(re.findall(r'COMPLETE status=00000120 response=00000001',uart))
out['uart_graph_restores']=len(re.findall(r'graph-restore address=\w+ value=\w+ verified',uart))
out['uart_no_sham_writes']=not re.search(r'spdi-restore|bridge-restore',uart)
out['uart_no_failure']=not re.search(r'FAILED|TIMEOUT|SKIPPED',uart)
out['uart_power_down']='reboot: Power down' in uart
j=rec['journal'];out['journal_initial_zero_then_patch']=j.find('DSP versions 0000/0000')>=0 and j.find('DSP versions 0000/0000')<j.find('pinned 724-pair DSP patch verified versions 1/1')
cold=(R/'cold-boot/serial.log').read_bytes().decode(errors='replace')
out['cold_handoff']=cold.count('H713 HDMI cold startup handoff verified')==1 and cold.count('H713 panel 720p timing re-latched after source 3')==1 and cold.count('Starting kernel')==1
m=json.loads((R/'export-verified.json').read_text());out['export_sha_verified']=hashlib.sha256((R/'board-export.tar.gz').read_bytes()).hexdigest()==m['sha256']
out['sham_canonical_sha256']=a.canonical(rec)
print(json.dumps(out,indent=1));(R/'validation.json').write_text(json.dumps(out,indent=1)+'\n')
