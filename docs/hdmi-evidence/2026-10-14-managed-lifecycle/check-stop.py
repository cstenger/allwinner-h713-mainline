import subprocess,json
from pathlib import Path
base='/tmp/h713-linux-return'
def run(argv,check=True):
 p=subprocess.run(argv,text=True,capture_output=True,timeout=40)
 print(json.dumps({'argv':argv,'rc':p.returncode,'out':p.stdout,'err':p.stderr}),flush=True)
 if check:assert p.returncode==0
 return p
assert Path('/proc/asound/H713HDMI/pcm0c/sub0/status').read_text().strip()=='closed'
run(['systemctl','stop','h713-hdmi-capture.service'])
run(['journalctl','-b','-u','h713-hdmi-capture.service','--no-pager','-n','30'])
assert not Path('/sys/module/h713_hdmi_audio').exists()
assert Path('/sys/module/h713_hdmi_receiver/parameters/clients').read_text().strip()=='0'
before=run(['dmesg','--color=never']).stdout
p=run(['python3',base+'/h713-hdmi-session.py','stop'])
assert json.loads(p.stdout)['already_stopped'] is True
assert run(['dmesg','--color=never']).stdout==before
p=run(['systemctl','start','h713-hdmi-capture.service'],False)
assert p.returncode!=0
assert not Path('/sys/module/h713_hdmi_audio').exists()
assert run(['dmesg','--color=never']).stdout==before
run(['journalctl','-b','-u','h713-hdmi-capture.service','--no-pager','-n','15'])
run(['runuser','-u','media','--','env','XDG_RUNTIME_DIR=/run/user/1000','systemctl','--user','is-active','wireplumber.service'])
assert Path('/sys/module/firmware_class/parameters/path').read_text().strip()==''
run(['python3',base+'/h713-hdmi-session.py','status'])
run(['python3',base+'/mips-shell.py','--cmd','help win'])
Path('/run/systemd/system/h713-hdmi-capture.service').unlink()
run(['systemctl','reset-failed','h713-hdmi-capture.service'])
run(['systemctl','daemon-reload'])
print('STOP AND WARM-RESTART GUARDS PASS',flush=True)
