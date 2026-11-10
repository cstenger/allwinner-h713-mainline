"""Require a live owned PCM at the exact normal poweroff request."""
import json,subprocess
from pathlib import Path
state=json.loads(Path('/run/h713-hdmi-session/state.json').read_text())
assert state['phase']=='ready'
text=Path('/proc/asound/H713HDMI/pcm0c/sub0/status').read_text()
assert 'state: RUNNING' in text,text
pid=int(next(line.split(':',1)[1] for line in text.splitlines() if line.startswith('owner_pid')))
main=int(subprocess.check_output(['systemctl','show','h713-hdmi-poweroff-recorder.service','-p','MainPID','--value'],text=True))
assert pid==main and Path(f'/proc/{pid}/comm').read_text().strip()=='arecord'
assert Path('/sys/module/h713_hdmi_audio/parameters/graph_ready').read_text().strip()=='Y'
assert Path('/sys/module/h713_hdmi_audio/parameters/dsp_failed').read_text().strip()=='N'
marker={'active_recording_poweroff_request':True,'recorder_pid':pid,'pcm_status':text,'boot_id':state['boot_id']}
line=json.dumps(marker)+'\n'
Path('/tmp/h713-active-poweroff/request-state.json').write_text(line)
with open('/dev/ttyS0','w') as serial:serial.write('H713 ACTIVE POWEROFF '+line);serial.flush()
print(line,flush=True)
subprocess.run(['systemctl','poweroff'],check=True)
