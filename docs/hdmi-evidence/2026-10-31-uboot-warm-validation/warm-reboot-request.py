from pathlib import Path
import os,json,subprocess
expected='85768624-6a6e-4637-a50f-f45b2c156f31'
base=Path('/var/lib/h713-uboot-migration/warm-20261031-01')
assert Path('/proc/device-tree/model').read_text().strip('\0\n')=='HY200 QZ713DF_A1 (Allwinner H713)'
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==expected
assert json.loads(Path('/run/h713-hdmi-session/state.json').read_text())==dict(boot_id=expected,phase='ready')
fd=os.open(base/'request.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as f:
 json.dump(dict(expected_preboot_id=expected,maximum_reboots=1,method='ordinary sync and systemctl reboot',no_prompt_hold=True,no_latch_arming=True),f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
subprocess.run(['sync'],check=True)
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==expected
print('Issuing single ordinary systemctl reboot from '+expected,flush=True)
subprocess.run(['systemctl','reboot'],check=True)
