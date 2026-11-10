from pathlib import Path
import hashlib,json,os,subprocess
p=Path('/root/hdmi-dsp-boundary-2026-10-22')
m=json.loads((p/'manifest.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert m['purpose']=='bench DSP boundary attribution; not installed' and m['built'] and m['symvers_unchanged']
assert 'h713_tvfe_retain=1' not in Path('/proc/cmdline').read_text().split()
for n,h in m['bundle'].items():assert sha(p/n)==h,n
assert sha(Path('/usr/lib/systemd/system-shutdown/h713-hdmi-hold-guard'))==m['bundle']['h713-hdmi-hold-guard']
original=Path('/root/hdmi-dsp-retention-2026-10-21/previous-hold-guard')
assert sha(original)=='96f37655b33bf78d95b33fa4f431721be5a7506c73c12dcd4df58032cad27113'
assert (original.stat().st_mode & 0o7777)==0o755
assert not (p/'arm-proof.json').exists()
b=json.loads((p/'cold-census.json').read_text())
assert b['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert b['hdmi_handoff'] and b['tv_domains_both_on'] and all(v=='active' for v in b['units'].values())
assert any('pinned 724-pair DSP patch verified versions 1/1' in l for l in b['dsp_journal'])
subprocess.run(['sync'],check=True)
print(json.dumps({'boot_id':b['boot_id'],'bundle_verified':True,'existing_guard_verified':True,'original_backup_verified':True,'original_backup_mode':'0755','guard_unchanged':True}))
