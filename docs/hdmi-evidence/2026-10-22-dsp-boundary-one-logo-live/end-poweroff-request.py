from pathlib import Path
import hashlib,json,subprocess
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert boot=='5b3937e4-fc0a-47c9-8fe0-cd701e4eafd6'
s=json.loads(Path('/sys/kernel/h713_dsp_retention/state').read_text())
assert s['schema']=='h713-dsp-boundary-v1' and s['step']==s['attempted']==55
assert s['hold']==s['timeout']==1 and s['violated']==s['failed']==s['claimed']==0
assert s['pairs'][0]['outcome']==[2,3]
assert all(p['outcome']==[0,0] for p in s['pairs'][1:])
assert s['ctl_before']==s['cfg_before']==0
for unit in ('capture','signal','speaker'):
    r=subprocess.run(['systemctl','is-active','h713-hdmi-'+unit+'.service'],capture_output=True,text=True)
    assert r.stdout.strip()=='inactive'
assert not Path('/proc/device-tree/chosen/h713,hdmi-boot-v1').exists()
assert hashlib.sha256(Path('/usr/lib/systemd/system-shutdown/h713-hdmi-hold-guard').read_bytes()).hexdigest()=='5ad26677ac791d2be659db88165d689d997705f45ee4d516015e786342ad764d'
print('H713_DSP_BOUNDARY_END_POWEROFF boot='+boot,flush=True)
subprocess.run(['sync'],check=True)
subprocess.run(['systemctl','poweroff'],check=True)
