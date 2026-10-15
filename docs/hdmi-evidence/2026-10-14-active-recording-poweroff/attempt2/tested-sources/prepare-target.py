"""Install runtime-only recorder, signal owner and shutdown journal relay."""
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
'h713-hdmi-poweroff-relay.service':'''[Unit]
Description=Bounded HDMI poweroff test journal relay
After=systemd-journald.service
Before=h713-hdmi-capture.service
[Service]
ExecStart=/usr/bin/journalctl --follow --no-pager --all --full -o short-monotonic -u h713-hdmi-capture.service -u h713-hdmi-poweroff-recorder.service -u h713-hdmi-poweroff-signal.service
ExecStop=/bin/sleep 1
Environment=SYSTEMD_COLORS=0 SYSTEMD_URLIFY=0
StandardOutput=tty
StandardError=journal
TTYPath=/dev/ttyS0
''',
'h713-hdmi-poweroff-signal.service':f'''[Unit]
Description=Bounded HDMI signal owner for poweroff test
Requires=h713-hdmi-capture.service
After=h713-hdmi-capture.service
[Service]
ExecStart=/usr/bin/python3 {base}/signal-owner.py start
ExecStop=/usr/bin/python3 {base}/signal-owner.py stop
TimeoutStopSec=75
''',
'h713-hdmi-poweroff-recorder.service':'''[Unit]
Description=Active HDMI recorder for full poweroff test
Requires=h713-hdmi-capture.service h713-hdmi-poweroff-signal.service
After=h713-hdmi-capture.service h713-hdmi-poweroff-signal.service
[Service]
ExecStart=/tmp/h713-linux-return/arecord -q -D hw:H713HDMI,0 -t raw -f S16_LE -r 48000 -c 2 --period-size=256 --buffer-size=16384 -d 90 /tmp/h713-active-poweroff/capture.raw
KillSignal=SIGINT
SuccessExitStatus=1 SIGINT
TimeoutStopSec=10
'''}
for name in units:assert not (system/name).exists(),name
for name,text in units.items():(system/name).write_text(text)
run(['systemd-analyze','verify',*(str(system/name) for name in units)])
run(['systemctl','daemon-reload'])
run(['systemctl','start','h713-hdmi-poweroff-relay.service','h713-hdmi-poweroff-signal.service'])
print('Runtime units verified; bounded signal assertion started.',flush=True)
