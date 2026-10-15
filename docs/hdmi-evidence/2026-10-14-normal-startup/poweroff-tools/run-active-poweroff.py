"""Prove live HDMI PCM, request normal poweroff once, observe bounded shutdown."""
import argparse,importlib.util,json,os,re,shlex,subprocess,time
from pathlib import Path
root=Path(__file__).resolve().parents[4]
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
console=load('console',root/'tools/serial/console.py')
rate=load('rate',root/'tools/hdmi/run-audio-rate-test.py')
ssh=['ssh','-F','/dev/null','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=5','-o','ServerAliveInterval=2','-o','ServerAliveCountMax=2','root@192.168.4.1']
p=argparse.ArgumentParser();p.add_argument('output',type=Path);out=p.parse_args().output
out.mkdir(parents=True,exist_ok=False)
def remote(command,name,timeout=25):
 result=subprocess.run(ssh+[command],capture_output=True,text=True,timeout=timeout)
 (out/name).write_text(result.stdout+result.stderr)
 if result.returncode:raise RuntimeError('board command failed: '+name)
 return result.stdout
fd=console.open_port('/dev/ttyUSB0');player=None;request=None;triggered=False;result={'pass':False}
try:
 remote('python3 /tmp/h713-active-poweroff/prepare-target.py','prepare.log')
 deadline=time.monotonic()+15
 while True:
  try:card,device,eld=rate.find_pcm();break
  except RuntimeError:
   if time.monotonic()>=deadline:raise RuntimeError('HDMI ELD timeout; no poweroff requested')
   time.sleep(.2)
 (out/'eld.txt').write_text(eld.read_text())
 remote('systemctl start h713-hdmi-poweroff-recorder.service','recorder-start.log')
 deadline=time.monotonic()+5
 while True:
  status=remote('cat /proc/asound/H713HDMI/pcm0c/sub0/status','recording-status.txt')
  if 'state: RUNNING' in status:break
  if time.monotonic()>=deadline:raise RuntimeError('recorder did not start; no poweroff requested')
  time.sleep(.1)
 rate.make_wave(out/'tone.wav',48000,tone_seconds=50)
 playback=(out/'playback.log').open('w')
 player=subprocess.Popen(['aplay','--disable-resample','-v','-D',f'hw:{card},{device}',str(out/'tone.wav')],stdout=playback,stderr=subprocess.STDOUT)
 time.sleep(4)
 params=Path(f'/proc/asound/card{card}/pcm{device}p/sub0/hw_params').read_text()
 (out/'host-hw-params.txt').write_text(params);rate.check_hw_params(params,48000)
 code="from pathlib import Path; import sys; f=open('/tmp/h713-active-poweroff/capture.raw','rb'); f.seek(384000); sys.stdout.buffer.write(f.read(65536))"
 sample=subprocess.run(ssh+['python3 -c '+shlex.quote(code)],capture_output=True,timeout=10)
 assert sample.returncode==0 and len(sample.stdout)==65536,sample.stderr
 (out/'settled-sample.raw').write_bytes(sample.stdout)
 tone=rate.analysis.analyze(sample.stdout);(out/'tone-analysis.json').write_text(json.dumps(tone,indent=2)+'\n')
 assert tone['tone_pass'] and tone['capture_rate_hz']==48000,tone
 assert player.poll() is None,'source playback ended before poweroff'
 assert remote('cat /sys/module/h713_hdmi_audio/parameters/period_xruns','xruns-before.txt').strip()=='0'
 print('Live HDMI stereo tones verified; recorder RUNNING. Requesting normal poweroff once.',flush=True)
 (out/'poweroff-attempted').write_text('One normal systemctl poweroff with active owned recorder; no force/reboot/retry.\n')
 triggered=True;started=time.monotonic();down_at=None;chunks=[];backend_reported=False
 request=subprocess.Popen(ssh+['python3 /tmp/h713-active-poweroff/request-poweroff.py'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 with (out/'serial-poweroff.log').open('wb') as serial:
  while time.monotonic()-started<200:
   try:data=os.read(fd,16384)
   except BlockingIOError:data=b''
   if data:
    serial.write(data);serial.flush();chunks.append(data)
    trace=b''.join(chunks)
    if not backend_reported and b'Stopping h713-hdmi-capture.service' in trace:
     backend_reported=True;print('Recorder/signal teardown reached capture backend shutdown.',flush=True)
    if down_at is None and b'reboot: Power down' in trace:
     down_at=time.monotonic();print('Serial reached Power down; watching for 90 seconds.',flush=True)
   if down_at is not None and time.monotonic()-down_at>=90:break
   time.sleep(.05)
 text=b''.join(chunks).decode(errors='replace')
 try:stdout,stderr=request.communicate(timeout=1)
 except subprocess.TimeoutExpired:
  request.terminate();stdout,stderr=request.communicate(timeout=3)
 (out/'ssh-poweroff.log').write_bytes(stdout+stderr)
 stages=['H713 ACTIVE POWEROFF','Stopped h713-hdmi-poweroff-recorder.service','EDID/HPD, SCP SRAM/vectors and DDC ownership restored','Stopped h713-hdmi-signal.service','Stopping h713-hdmi-capture.service','"phase": "parked"','reboot: Power down']
 positions=[text.find(stage) for stage in stages]
 after=text.split('reboot: Power down',1)[1] if down_at is not None else ''
 result.update(active_tone_capture_verified=True,source_rate_hz=48000,recorder_running_at_request='H713 ACTIVE POWEROFF' in text,stage_positions=dict(zip(stages,positions)),shutdown_order_verified=all(x>=0 for x in positions) and positions==sorted(positions),dsp_restore_verified='"dsp_restored_words": 22' in text,tvfe_restore_verified='"tvfe_restored_words": 15' in text,receiver_removed='"receiver_removed": true' in text,powerdown_seen=down_at is not None,seconds_after_powerdown=None if down_at is None else time.monotonic()-down_at,unexpected_reboot_seen=bool(re.search(r'U-Boot|Starting kernel|Booting Linux|Linux version',after)),lamp_fan_operator_confirmation_pending=True,ssh_returncode=request.returncode)
 result['pass']=all(result[key] for key in ('recorder_running_at_request','shutdown_order_verified','dsp_restore_verified','tvfe_restore_verified','receiver_removed','powerdown_seen')) and not result['unexpected_reboot_seen'] and result['seconds_after_powerdown']>=90
 print(json.dumps(result),flush=True)
except Exception as error:
 result['error']=str(error);raise
finally:
 os.close(fd)
 if player is not None:
  if player.poll() is None:player.terminate()
  try:player.wait(timeout=3)
  except subprocess.TimeoutExpired:player.kill();player.wait(timeout=3)
  playback.close()
 if not triggered:
  subprocess.run(ssh+['systemctl stop h713-hdmi-poweroff-recorder.service h713-hdmi-poweroff-relay.service'],capture_output=True,timeout=85)
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
if not result['pass']:raise SystemExit('Poweroff test failed; inspect evidence, do not automatically retry')
