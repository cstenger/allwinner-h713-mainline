import hashlib,importlib.util,json,subprocess,time
from pathlib import Path
root=Path('/home/chris/Projects/h713'); current=Path('/home/chris/.codex/worktrees/hdmi-capture-current/h713');out=root/'docs/hdmi-evidence/2026-10-07-audio-dispatch/audio-holds'
ssh=['ssh','-F','/dev/null','-o','BatchMode=yes','-o','ConnectTimeout=5','root@192.168.4.1']
def snap():
 p=subprocess.run(ssh+['python3 /root/hdmi-safe-trace/read-mips-audio-cache.py'],capture_output=True,text=True,timeout=8);p.check_returncode();return json.loads(p.stdout)
subprocess.run(['python3',str(current/'tools/hdmi/make-audio-test.py'),'/tmp/h713-cache-tone.wav','--seconds','8'],check=True)
spec=importlib.util.spec_from_file_location('pcm',current/'tools/hdmi/find-hdmi-audio-pcm.py');pcm=importlib.util.module_from_spec(spec);spec.loader.exec_module(pcm)
probe=Path('/tmp/h713-dsp-current-modules/scp-probe/h713-scp-probe.ko')
expected='0c41c7071c4606fc328fbc0d8ef2b52783af3dded199d1aad698ebedc5a3c0e0'
if hashlib.sha256(probe.read_bytes()).hexdigest()!=expected:raise RuntimeError('canonical probe identity mismatch')
subprocess.run(['scp','-F','/dev/null','-o','BatchMode=yes',str(probe),'root@192.168.4.1:/tmp/'],check=True)
remote_sha=subprocess.run(ssh+['sha256sum /tmp/h713-scp-probe.ko'],capture_output=True,text=True,check=True).stdout.split()[0]
if remote_sha!=expected:raise RuntimeError('staged probe identity mismatch')
log=(out/'cache-trial.log').open('w');trial=subprocess.Popen(['python3',str(current/'tools/hdmi/run-detection-trial.py'),'--seconds','30','--stock-io','--probe-port-cache'],stdout=log,stderr=subprocess.STDOUT)
trace_log=(out/'dispatch-watch.jsonl').open('w')
watch=subprocess.Popen(ssh+['python3 /root/hdmi-safe-trace/read-audio-dispatch-trace.py --watch 45 --interval .25'],stdout=trace_log,stderr=subprocess.STDOUT)
player=None;rows=[];start=time.monotonic()
try:
 for n in range(22):
  if trial.poll() is not None:raise RuntimeError('HPD trial ended before playback')
  x=snap();port=x['ports'][0];rows.append({'elapsed':time.monotonic()-start,'phase':'waiting','state':x})
  if port['state']==5 and (port['hactive'],port['vactive'],port['pixel_repeat'])==(1280,720,0):break
  time.sleep(.25)
 else:raise RuntimeError('receiver did not lock 720p')
 connectors=[p for p in Path('/sys/class/drm').glob('card*-HDMI-A-*') if hashlib.sha256((p/'edid').read_bytes()).hexdigest()=='edab9bfc48547939fcb26f7775558c94569a11abb4beb1132e22f2ad4c173d34']
 if len(connectors)!=1:raise RuntimeError('canonical EDID not found')
 device=pcm.find_pcm('H713 HDMI IN');(out/'source-audio-pcm.json').write_text(json.dumps(device,indent=2)+'\n')
 player=subprocess.Popen(['aplay','-D',device['pcm'],'/tmp/h713-cache-tone.wav'],stdout=log,stderr=subprocess.STDOUT)
 for n in range(10):
  x=snap();rows.append({'elapsed':time.monotonic()-start,'phase':'tone' if player.poll() is None else 'after-tone','state':x}); print(json.dumps({'phase':rows[-1]['phase'],'port':x['ports'][0]}),flush=True);time.sleep(.6)
 player.wait(timeout=10)
 if player.returncode:raise RuntimeError('aplay failed')
finally:
 if player is not None and player.poll() is None:player.terminate();player.wait(timeout=5)
 (out/'audio-cache-trial.json').write_text(json.dumps(rows,indent=2)+'\n')
 trial.wait(timeout=45);log.close()
 (out/'audio-cache-after.json').write_text(json.dumps(snap(),indent=2)+'\n')
 watch.wait(timeout=50);trace_log.close()
 print('HPD trial exit',trial.returncode)
 if trial.returncode:raise RuntimeError('HPD trial failed')
