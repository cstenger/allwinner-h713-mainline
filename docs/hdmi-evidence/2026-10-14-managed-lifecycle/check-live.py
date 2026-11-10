import subprocess,json,time
from pathlib import Path
base='/tmp/h713-linux-return'
def run(argv,check=True):
 p=subprocess.run(argv,text=True,capture_output=True,timeout=15)
 print(json.dumps({'argv':argv,'rc':p.returncode,'out':p.stdout,'err':p.stderr}),flush=True)
 if check:assert p.returncode==0
 return p
before=run(['dmesg','--color=never']).stdout
p=run(['python3',base+'/h713-hdmi-session.py','start'])
assert json.loads(p.stdout)['already_ready'] is True
assert run(['dmesg','--color=never']).stdout==before
with open('/tmp/h713-managed-busy.log','w') as log:
 reader=subprocess.Popen([base+'/arecord','-D','hw:H713HDMI,0','-t','raw','-f','S16_LE','-r','48000','-c','2','--period-size=256','--buffer-size=16384','-d','5','/dev/null'],stdout=log,stderr=log)
 try:
  deadline=time.monotonic()+3
  while 'state: RUNNING' not in Path('/proc/asound/H713HDMI/pcm0c/sub0/status').read_text():
   assert reader.poll() is None and time.monotonic()<deadline
   time.sleep(.05)
  before=run(['dmesg','--color=never']).stdout
  p=run(['python3',base+'/h713-hdmi-session.py','stop'],False)
  assert p.returncode!=0 and 'capture is open' in p.stderr
  assert Path('/sys/module/h713_hdmi_audio/parameters/graph_ready').read_text().strip()=='Y'
  assert run(['dmesg','--color=never']).stdout==before
 finally:
  assert reader.wait(timeout=8)==0
assert Path('/proc/asound/H713HDMI/pcm0c/sub0/status').read_text().strip()=='closed'
print('LIVE GUARDS PASS',flush=True)
