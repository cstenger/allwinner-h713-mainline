import hashlib,json,os,pathlib,subprocess
b=pathlib.Path('/root/hdmi-dsp-minimum-2026-10-22')
proof=json.loads((b/'arm-proof.json').read_text());manifest=json.loads((b/'manifest.json').read_text())
boot=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert proof['verified'] and proof['warm_boot_id']==boot and proof['cold_boot_id']=='e5d341d0-ce97-4a87-b2b5-37aecd31fa7d'
assert os.uname().version==manifest['kernel_uts_version']
assert hashlib.sha256(pathlib.Path('/usr/lib/systemd/system-shutdown/h713-hdmi-hold-guard').read_bytes()).hexdigest()==manifest['bundle']['h713-hdmi-hold-guard']
s=json.loads(pathlib.Path('/sys/kernel/h713_dsp_retention/state').read_text())
assert s['step']==58 and s['hold']==1 and s['violated']==s['failed']==s['claimed']==0
l=json.loads(pathlib.Path('/run/h713-dsp-minimum/ledger.json').read_text())
assert l['boot']==boot and not l['uncertain'] and l['snapshot']==58
assert pathlib.Path('/run/h713-dsp-minimum-export.tar.gz').exists()
for unit in ('capture','signal','speaker'):
    assert subprocess.run(['systemctl','is-active','h713-hdmi-'+unit+'.service'],capture_output=True,text=True).stdout.strip()=='inactive'
print('H713_DSP_MINIMUM_END_POWEROFF boot='+boot,flush=True)
subprocess.run(['sync'],check=True)
subprocess.run(['systemctl','poweroff'],check=True)
