from pathlib import Path
import subprocess
expected = 'fe51947d-10f3-405b-9b6f-0d56fb04a824'
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
if boot != expected:
    raise SystemExit('Boot ID changed; refusing reboot')
for unit in ('capture', 'signal', 'speaker'):
    state = subprocess.check_output(['systemctl', 'is-active', 'h713-hdmi-' + unit + '.service'], text=True).strip()
    if state != 'active':
        raise SystemExit('Inactive production unit: ' + unit)
print('H713_PRELOGO_ORDERLY_REBOOT boot=' + boot, flush=True)
subprocess.run(['sync'], check=True)
subprocess.run(['systemctl', 'reboot'], check=True)
