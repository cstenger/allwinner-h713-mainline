from pathlib import Path
import hashlib,json,os,shutil,subprocess
b=Path('/root/hdmi-dsp-retention-2026-10-21')
m=json.loads((b/'manifest.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='96cae8c6-c621-4133-b416-0583ae9ca996'
assert 'h713_tvfe_retain=1' not in Path('/proc/cmdline').read_text().split()
for n,h in m['bundle'].items(): assert sha(b/n)==h,n
g=Path('/usr/lib/systemd/system-shutdown/h713-hdmi-hold-guard')
assert sha(g)==m['guard_previous_expected_sha256']
backup=b/'previous-hold-guard'
assert not backup.exists()
shutil.copy2(g,backup)
assert sha(backup)==m['guard_previous_expected_sha256']
tmp=g.with_name(g.name+'.retention-tmp')
assert not tmp.exists()
shutil.copyfile(b/g.name,tmp);tmp.chmod(0o755);os.replace(tmp,g)
assert sha(g)==m['bundle'][g.name]
subprocess.run(['sync'],check=True)
print(json.dumps({'guard':sha(g),'backup':sha(backup),'backup_mode':oct(backup.stat().st_mode & 0o7777),'bundle_verified':True}))
