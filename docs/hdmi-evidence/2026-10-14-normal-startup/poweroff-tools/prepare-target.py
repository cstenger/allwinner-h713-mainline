"""Install runtime-only recorder and journal relay; the persistent signal service owns HPD."""
import json,subprocess,time
from pathlib import Path
base='/tmp/h713-active-poweroff'
system=Path('/run/systemd/system')
def run(argv):
 p=subprocess.run(argv,text=True,capture_output=True,timeout=20)
 print(json.dumps({'argv':argv,'rc':p.returncode,'out':p.stdout,'err':p.stderr}),flush=True)
 assert p.returncode==0
 return p.stdout
assert json.loads(Path('/run/h713-hdmi-session/state.json').read_text())['phase']=='ready'
units={
'h713-hdmi-poweroff-relay.service':f'''[Unit]
Description=Bounded HDMI poweroff test journal relay
After=systemd-journald.service serial-getty@ttyS0.service
Before=h713-hdmi-capture.service
[Service]
ExecStart=/usr/bin/python3 {base}/journal-relay.py
ExecStop=/bin/sleep 1
StandardOutput=journal
StandardError=journal
''',
'h713-hdmi-poweroff-recorder.service':'''[Unit]
Description=Active HDMI recorder for full poweroff test
Requires=h713-hdmi-signal.service
After=h713-hdmi-signal.service
[Service]
ExecStart=/tmp/arecord -q -D hw:H713HDMI,0 -t raw -f S16_LE -r 48000 -c 2 --period-size=256 --buffer-size=16384 -d 90 /tmp/h713-active-poweroff/capture.raw
KillSignal=SIGINT
SuccessExitStatus=1 SIGINT
TimeoutStopSec=10
'''}
for name in units:assert not (system/name).exists(),name
for name,text in units.items():(system/name).write_text(text)
run(['systemd-analyze','verify',*(str(system/name) for name in units)])
run(['systemctl','daemon-reload'])
for unit in ('h713-hdmi-capture.service','h713-hdmi-signal.service'):assert run(['systemctl','is-active',unit]).strip()=='active',unit
for name in ('ready','failed'):print(name,Path('/sys/module/h713_hdmi_signal/parameters/'+name).read_text().strip(),flush=True)
assert Path('/sys/module/h713_hdmi_signal/parameters/ready').read_text().strip()=='Y'
run(['systemctl','start','h713-hdmi-poweroff-relay.service'])
print('Runtime units verified; persistent signal owner ready.',flush=True)
