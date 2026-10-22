from pathlib import Path
import hashlib,json,subprocess
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert boot=='9fd2d002-951b-43d8-a656-eec7cc02c995'
s=json.loads(Path('/sys/kernel/h713_dsp_retention/state').read_text())
assert s['step']==46 and s['hold']==1 and s['violated']==s['failed']==s['timeout']==s['claimed']==0
for unit in ('capture','signal','speaker'):
    r=subprocess.run(['systemctl','is-active','h713-hdmi-'+unit+'.service'],capture_output=True,text=True)
    assert r.stdout.strip()=='inactive'
assert not Path('/proc/device-tree/chosen/h713,hdmi-boot-v1').exists()
assert hashlib.sha256(Path('/usr/lib/systemd/system-shutdown/h713-hdmi-hold-guard').read_bytes()).hexdigest()=='5ad26677ac791d2be659db88165d689d997705f45ee4d516015e786342ad764d'
print('H713_DSP_RETENTION_END_POWEROFF boot='+boot,flush=True)
subprocess.run(['sync'],check=True)
subprocess.run(['systemctl','poweroff'],check=True)
