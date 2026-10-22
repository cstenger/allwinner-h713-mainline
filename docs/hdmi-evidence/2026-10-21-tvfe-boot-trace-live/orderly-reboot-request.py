from pathlib import Path
import subprocess
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
if boot != 'd7017dce-174d-4795-bf23-0049f73f04b4':
    raise SystemExit('Unexpected boot; no reboot')
for unit in ('capture','signal','speaker'):
    state = subprocess.check_output(['systemctl','is-active','h713-hdmi-' + unit + '.service'], text=True).strip()
    if state != 'active':
        raise SystemExit('Unexpected owner state; no reboot')
print('H713_TVFE_TRACE_ORDERLY_REBOOT boot=' + boot, flush=True)
subprocess.run(['sync'], check=True)
subprocess.run(['systemctl','reboot'], check=True)
