import hashlib,json,os,platform,sys
from pathlib import Path
bundle=Path('/root/hdmi-dsp-access-audit-2026-10-21')
expected=sys.argv[1]
def checkboot():
    if Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=expected:
        raise RuntimeError('Wrong boot; no action')
checkboot()
if platform.release()!='6.18.38':raise RuntimeError('Wrong kernel')
manifest=json.loads((bundle/'manifest.json').read_text())
if manifest['schema']!='h713-dsp-access-prefix-v1':raise RuntimeError('Wrong schema')
for name,key in [('h713-hdmi-dsp-access-audit.ko','module_sha256'),('dsp-access-audit.py','helper_sha256'),('h713-hdmi-hold-guard','guard_sha256')]:
    if hashlib.sha256((bundle/name).read_bytes()).hexdigest()!=manifest[key]:raise RuntimeError('Wrong file '+name)
    print('PASS bundle '+name,flush=True)
for name in ['h713_hdmi_dsp_access_audit','h713_hdmi_dsp_observe','h713_hdmi_receiver','h713_hdmi_audio','h713_hdmi_signal','h713_scp_probe']:
    if Path('/sys/module',name).exists():raise RuntimeError('Owner loaded '+name)
guard=Path('/usr/lib/systemd/system-shutdown/h713-hdmi-hold-guard')
old=guard.read_bytes()
if hashlib.sha256(old).hexdigest()!='365fe6c97cefb24794d5e4a315d6711b08a8a136874eebb00a08a750cc8e7de6':raise RuntimeError('Unexpected old guard')
new=(bundle/'h713-hdmi-hold-guard').read_bytes()
checkboot()
print('BEFORE backup and atomic guard replacement; no module load',flush=True)
with (bundle/'previous-hold-guard').open('xb') as f:
    f.write(old);f.flush();os.fsync(f.fileno())
os.chmod(bundle/'previous-hold-guard',0o755)
temp=guard.with_name(guard.name+'.prefix-audit-new')
with temp.open('xb') as f:
    f.write(new);f.flush();os.fchmod(f.fileno(),0o755);os.fsync(f.fileno())
checkboot()
os.replace(temp,guard)
fd=os.open(guard.parent,os.O_RDONLY|os.O_DIRECTORY)
try:os.fsync(fd)
finally:os.close(fd)
if guard.read_bytes()!=new:raise RuntimeError('Guard readback mismatch')
if (bundle/'previous-hold-guard').read_bytes()!=old:raise RuntimeError('Backup mismatch')
print('PASS guard installed and exact backup/readback verified; NO module loaded or access step sent',flush=True)
