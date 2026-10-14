import json,subprocess
from pathlib import Path
bundle='/tmp/h713-linux-return'
def run(argv,check=True,timeout=40):
 p=subprocess.run(argv,text=True,capture_output=True,timeout=timeout)
 print(json.dumps({'argv':argv,'rc':p.returncode,'out':p.stdout,'err':p.stderr}),flush=True)
 if check:assert p.returncode==0
 return p
assert Path('/proc/asound/H713HDMI/pcm0c/sub0/status').read_text().strip()=='closed'
assert Path('/sys/module/h713_hdmi_receiver/parameters/shutdown_ready').read_text().strip()=='Y'
run(['systemctl','stop','h713-hdmi-capture.service'])
state=json.loads(Path('/run/h713-hdmi-session/state.json').read_text())
assert state['phase']=='stopped' and state['restore_verified'] is True,state
assert not Path('/sys/module/h713_hdmi_audio').exists()
assert Path('/sys/module/h713_hdmi_receiver/parameters/clients').read_text().strip()=='0'
run(['journalctl','-b','-u','h713-hdmi-capture.service','--no-pager','-n','25'])
for register in ('2001600','200160c'):
 run(['/root/mmio-rw','r',register])
run(['python3',bundle+'/h713-hdmi-session.py','park','--terminal-shutdown'],timeout=30)
state=json.loads(Path('/run/h713-hdmi-session/state.json').read_text())
assert state['phase']=='parked',state
assert not Path('/sys/module/h713_hdmi_receiver').exists()
assert 'MIPS core      parked' in run(['python3',bundle+'/mips-shell.py','--status']).stdout
for register in ('2001600','200160c'):
 run(['/root/mmio-rw','r',register])
run(['dmesg','--color=never'])
for name in ('/sys/kernel/debug/clk/clk_summary','/sys/kernel/debug/pm_genpd/pm_genpd_summary'):
 if Path(name).exists():print(name+'\n'+Path(name).read_text(),flush=True)
before=run(['dmesg','--color=never']).stdout
# A terminal state survives harmless stop calls and rejects any new start/park.
run(['python3',bundle+'/h713-hdmi-session.py','stop'])
assert json.loads(Path('/run/h713-hdmi-session/state.json').read_text())['phase']=='parked'
assert run(['python3',bundle+'/h713-hdmi-session.py','start'],False).returncode!=0
assert run(['python3',bundle+'/h713-hdmi-session.py','park','--terminal-shutdown'],False).returncode!=0
assert run(['dmesg','--color=never']).stdout==before
run(['runuser','-u','media','--','env','XDG_RUNTIME_DIR=/run/user/1000','systemctl','--user','is-active','wireplumber.service'])
assert Path('/sys/module/firmware_class/parameters/path').read_text().strip()==''
assert not Path('/sys/module/h713_scp_probe').exists()
assert not Path('/sys/module/h713_ddc_pins').exists()
Path('/run/systemd/system/h713-hdmi-capture.service').unlink()
run(['systemctl','daemon-reload'])
print('TERMINAL PARK AND RECEIVER RELEASE PASS',flush=True)
