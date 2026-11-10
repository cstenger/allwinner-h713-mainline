"""Exercise the real unit dependency graph with harmless command overrides."""
import hashlib,json,subprocess
from pathlib import Path
base=Path('/tmp/h713-shutdown-ordering')
unit=Path('/run/systemd/system/h713-hdmi-capture.service')
drop=Path(str(unit)+'.d')
client=Path('/run/systemd/system/h713-hdmi-order-client.service')
def run(argv):
 p=subprocess.run(argv,text=True,capture_output=True,timeout=30)
 print(json.dumps({'argv':argv,'rc':p.returncode,'out':p.stdout,'err':p.stderr}),flush=True)
 assert p.returncode==0
 return p.stdout
assert not unit.exists() and not drop.exists() and not client.exists()
assert not Path('/sys/module/h713_hdmi_audio').exists()
assert not Path('/sys/module/h713_hdmi_receiver').exists()
hook=Path('/usr/lib/systemd/system-shutdown/h713-off')
hook_hash=hashlib.sha256(hook.read_bytes()).hexdigest()
try:
 unit.write_bytes((base/unit.name).read_bytes());drop.mkdir()
 (drop/'10-terminal-shutdown.conf').write_bytes((base/'h713-hdmi-capture-shutdown.conf').read_bytes())
 run(['systemd-analyze','verify',str(unit)])
 run(['systemctl','daemon-reload'])
 command=run(['systemctl','show',unit.name,'-p','ExecStop','--value'])
 assert 'h713-hdmi-session.py shutdown --terminal-shutdown' in command
 assert 'h713-hdmi-session.py stop ' not in command
 after=run(['systemctl','show',unit.name,'-p','After','--value'])
 assert 'user@1000.service' in after
 run(['systemctl','cat',unit.name])
 # Keep the real dependency graph; replace hardware commands only.
 (drop/'90-ordering-test.conf').write_text('[Service]\nExecStart=\nExecStart=/usr/bin/python3 /tmp/h713-shutdown-ordering/record.py start-backend\nExecStop=\nExecStop=/usr/bin/python3 /tmp/h713-shutdown-ordering/record.py stop-backend\n')
 client.write_text('[Unit]\nDescription=HDMI ordering test consumer\nRequires=h713-hdmi-capture.service\nAfter=h713-hdmi-capture.service\n[Service]\nType=oneshot\nRemainAfterExit=yes\nExecStart=/usr/bin/python3 /tmp/h713-shutdown-ordering/record.py start-client\nExecStop=/usr/bin/python3 /tmp/h713-shutdown-ordering/record.py stop-client\n')
 run(['systemctl','daemon-reload'])
 start=run(['systemctl','show',unit.name,'-p','ExecStart','--value'])
 assert 'record.py start-backend' in start
 run(['systemd-analyze','verify',str(unit),str(client)])
 run(['systemctl','start',client.name])
 run(['systemctl','stop',unit.name,client.name])
 events=[json.loads(line) for line in (base/'events.jsonl').read_text().splitlines()]
 print(json.dumps({'events':events}),flush=True)
 assert [x['event'] for x in events]==['start-backend','start-client','stop-client','stop-backend']
 assert all(x['user_manager']=='active' for x in events)
 assert hashlib.sha256(hook.read_bytes()).hexdigest()==hook_hash
 print('SYSTEMD ORDERING FIXTURE PASS; hardware commands overridden',flush=True)
finally:
 subprocess.run(['systemctl','stop',client.name,unit.name],capture_output=True,timeout=30)
 for path in (client,drop/'90-ordering-test.conf',drop/'10-terminal-shutdown.conf',unit):
  path.unlink(missing_ok=True)
 if drop.exists():drop.rmdir()
 run(['systemctl','daemon-reload'])
