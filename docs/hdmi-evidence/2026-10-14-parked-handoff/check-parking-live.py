import errno,json,subprocess
from pathlib import Path
base=Path('/sys/module/h713_hdmi_receiver/parameters')
def run(argv):
 p=subprocess.run(argv,text=True,capture_output=True,timeout=10)
 print(json.dumps({'argv':argv,'rc':p.returncode,'out':p.stdout,'err':p.stderr}),flush=True)
 assert p.returncode==0
 return p.stdout
assert (base/'shutdown_ready').read_text().strip()=='Y'
assert (base/'clients').read_text().strip()=='1'
assert (base/'parked').read_text().strip()=='N'
assert (base/'park_failed').read_text().strip()=='N'
before=run(['dmesg','--color=never'])
try:
 (base/'park_for_shutdown').write_text('1\n')
 raise AssertionError('parking incorrectly accepted live audio client')
except OSError as error:
 assert error.errno==errno.EBUSY,error
 print('live-client park refused with EBUSY',flush=True)
assert run(['dmesg','--color=never'])==before
assert (base/'clients').read_text().strip()=='1'
assert (base/'firmware_pin').read_text().strip()=='Y'
assert (base/'parked').read_text().strip()=='N'
assert Path('/sys/module/h713_hdmi_audio/parameters/graph_ready').read_text().strip()=='Y'
assert 'VS:/' in run(['python3','/tmp/h713-linux-return/mips-shell.py','--cmd','help win'])
print('LIVE PARKING GUARD PASS',flush=True)
