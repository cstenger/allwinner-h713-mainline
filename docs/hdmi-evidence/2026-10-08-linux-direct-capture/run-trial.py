import subprocess,time,json,importlib.util,sys
from pathlib import Path
out=Path('/home/chris/Projects/h713/docs/hdmi-evidence/2026-10-08-linux-direct-capture')
base=Path('/home/chris/.codex/worktrees/hdmi-capture-current/h713/tools/hdmi')
ssh=['ssh','-F','/dev/null','-o','BatchMode=yes','-o','ConnectTimeout=5','root@192.168.4.1']
def remote(cmd,name,binary=False):
 r=subprocess.run(ssh+[cmd],capture_output=True,timeout=12)
 (out/name).write_bytes(r.stdout if binary else r.stdout+r.stderr)
 if r.returncode:raise RuntimeError((cmd,r.returncode,r.stderr.decode()))
 return r.stdout
subprocess.run([sys.executable,str(base/'make-audio-test.py'),str(out/'tone.wav'),'--seconds','10'],check=True)
spec=importlib.util.spec_from_file_location('pcm',base/'find-hdmi-audio-pcm.py'); mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
log=(out/'signal-window.log').open('w'); trial=None;player=None; result={}
try:
 remote('cat /sys/devices/h713-hdmi-audbrg-dma/capture','dma-before.bin',True)
 trial=subprocess.Popen([sys.executable,'tools/hdmi/run-detection-trial.py','--seconds','30','--stock-io','--probe-port-cache'],stdout=log,stderr=subprocess.STDOUT)
 deadline=time.monotonic()+18
 while time.monotonic()<deadline:
  if trial.poll() is not None:raise RuntimeError('Signal trial ended early')
  try: pcm=mod.find_pcm('H713 HDMI IN');break
  except RuntimeError:time.sleep(.3)
 else:raise RuntimeError('HDMI ELD did not become valid')
 result['pcm']=pcm
 remote('python3 /root/hdmi-safe-trace/read-mips-audio-cache.py','receiver-before-tone.json')
 plog=(out/'playback.log').open('w');player=subprocess.Popen(['aplay','-D',pcm['pcm'],str(out/'tone.wav')],stdout=plog,stderr=subprocess.STDOUT)
 for n in range(1,5):
  time.sleep(1.5)
  remote(f'echo {n+1} > /sys/module/h713_hdmi_bridge_trial/parameters/snapshot; cat /proc/interrupts; dmesg | tail -5',f'snapshot-{n}.log')
  data=remote('cat /sys/devices/h713-hdmi-audbrg-dma/capture',f'dma-tone-{n}.bin',True)
  if len(data)!=65536:raise RuntimeError('Bad DMA snapshot length')
 result['playback_returncode']=player.wait(timeout=12);plog.close()
 remote('python3 /root/hdmi-safe-trace/read-mips-audio-cache.py','receiver-after-tone.json')
 result['signal_returncode']=trial.wait(timeout=40)
except Exception as e:result['error']=repr(e)
finally:
 if player and player.poll() is None:player.terminate();player.wait(timeout=3)
 if trial and trial.poll() is None:
  try:result['signal_returncode']=trial.wait(timeout=40)
  except subprocess.TimeoutExpired:result['signal_timeout']=True
 log.close();(out/'trial-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
