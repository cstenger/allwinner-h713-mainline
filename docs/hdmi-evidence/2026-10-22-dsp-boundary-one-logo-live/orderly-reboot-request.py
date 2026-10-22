from pathlib import Path
import subprocess
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
if boot != '013a628c-db47-4614-b89e-d663d4f9b2b2':
    raise SystemExit('Unexpected boot; no reboot')
for unit in ('capture','signal','speaker'):
    state = subprocess.check_output(['systemctl','is-active','h713-hdmi-' + unit + '.service'], text=True).strip()
    if state != 'active':
        raise SystemExit('Unexpected owner state; no reboot')
print('H713_DSP_BOUNDARY_ORDERLY_REBOOT boot=' + boot, flush=True)
subprocess.run(['sync'], check=True)
subprocess.run(['systemctl','reboot'], check=True)
