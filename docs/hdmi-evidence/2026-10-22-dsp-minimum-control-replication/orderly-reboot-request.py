from pathlib import Path
import subprocess
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
if boot != '47702c3c-7090-4848-9e9c-2ffdb41ca930':
    raise SystemExit('Unexpected boot; no reboot')
for unit in ('capture','signal','speaker'):
    state = subprocess.check_output(['systemctl','is-active','h713-hdmi-' + unit + '.service'], text=True).strip()
    if state != 'active':
        raise SystemExit('Unexpected owner state; no reboot')
print('H713_DSP_MINIMUM_ORDERLY_REBOOT boot=' + boot, flush=True)
subprocess.run(['sync'], check=True)
subprocess.run(['systemctl','reboot'], check=True)
