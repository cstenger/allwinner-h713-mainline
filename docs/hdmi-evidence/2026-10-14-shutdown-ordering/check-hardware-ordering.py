"""Fresh-boot validation: a real PCM consumer must close before automatic park."""
import json,subprocess,time
from pathlib import Path
unit='h713-hdmi-capture.service'
client=Path('/run/systemd/system/h713-hdmi-order-client.service')
state_path=Path('/run/h713-hdmi-session/state.json')
def run(argv,check=True,timeout=70):
 p=subprocess.run(argv,text=True,capture_output=True,timeout=timeout)
 print(json.dumps({'argv':argv,'rc':p.returncode,'out':p.stdout,'err':p.stderr}),flush=True)
 if check:assert p.returncode==0
 return p
assert not client.exists()
assert json.loads(state_path.read_text())['phase']=='ready'
assert Path('/sys/module/h713_hdmi_receiver/parameters/shutdown_ready').read_text().strip()=='Y'
assert 'h713-hdmi-session.py shutdown --terminal-shutdown' in run(['systemctl','show',unit,'-p','ExecStop','--value']).stdout
try:
 client.write_text('[Unit]\nDescription=Bounded HDMI recording ordering consumer\nRequires=h713-hdmi-capture.service\nAfter=h713-hdmi-capture.service\n[Service]\nExecStart=/tmp/h713-linux-return/arecord -q -D hw:H713HDMI,0 -t raw -f S16_LE -r 48000 -c 2 --period-size=256 --buffer-size=16384 -d 60 /dev/null\nKillSignal=SIGINT\nSuccessExitStatus=1 SIGINT\nTimeoutStopSec=10\n')
 run(['systemctl','daemon-reload'])
 run(['systemctl','start',client.name])
 deadline=time.monotonic()+5
 status=Path('/proc/asound/H713HDMI/pcm0c/sub0/status')
 while 'state: RUNNING' not in status.read_text():
  assert time.monotonic()<deadline
  time.sleep(.05)
 text=status.read_text();print(text,flush=True)
 pid=int(next(line.split(':',1)[1] for line in text.splitlines() if line.startswith('owner_pid')))
 assert pid==int(run(['systemctl','show',client.name,'-p','MainPID','--value']).stdout)
 assert Path(f'/proc/{pid}/comm').read_text().strip()=='arecord'
 # Stopping only the dependency must propagate to the consumer and order it first.
 run(['systemctl','stop',unit])
 assert run(['systemctl','is-active',client.name],False).returncode!=0
 assert json.loads(state_path.read_text())['phase']=='parked'
 assert not Path('/sys/module/h713_hdmi_audio').exists()
 assert not Path('/sys/module/h713_hdmi_receiver').exists()
 journal=run(['journalctl','-b','-u',unit,'-u',client.name,'--no-pager','-o','short-monotonic']).stdout
 assert journal.index('Stopped '+client.name)<journal.index('Stopping '+unit),journal
 run(['python3','/tmp/h713-linux-return/h713-hdmi-session.py','shutdown','--terminal-shutdown'])
 for register in ('306101c','2001600','200160c'):run(['/root/mmio-rw','r',register])
 run(['dmesg','--color=never'])
 run(['runuser','-u','media','--','env','XDG_RUNTIME_DIR=/run/user/1000','systemctl','--user','is-active','wireplumber.service'])
 assert Path('/sys/module/firmware_class/parameters/path').read_text().strip()==''
 Path('/run/systemd/system/h713-hdmi-capture.service.d/10-terminal-shutdown.conf').unlink()
 Path('/run/systemd/system/h713-hdmi-capture.service.d').rmdir()
 Path('/run/systemd/system/'+unit).unlink()
 print('HARDWARE AUTOMATIC SHUTDOWN ORDERING PASS',flush=True)
finally:
 run(['systemctl','stop',client.name])
 client.unlink(missing_ok=True)
 run(['systemctl','daemon-reload'])
