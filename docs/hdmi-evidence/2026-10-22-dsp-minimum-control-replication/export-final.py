"""Export software diagnostic records without performing another observer operation."""
import hashlib,json,pathlib,subprocess,tarfile
b=pathlib.Path('/root/hdmi-dsp-minimum-2026-10-22')
r=pathlib.Path('/run/h713-dsp-minimum')
proof=json.loads((b/'arm-proof.json').read_text())
boot=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert proof['verified'] and proof['warm_boot_id']==boot and proof['cold_boot_id']=='47702c3c-7090-4848-9e9c-2ffdb41ca930'
s=json.loads(pathlib.Path('/sys/kernel/h713_dsp_retention/state').read_text())
assert s['step']==58 and s['hold']==1 and s['failed']==s['violated']==s['claimed']==0
ledger=json.loads((r/'ledger.json').read_text())
assert ledger['boot']==boot and not ledger['uncertain'] and ledger['snapshot']==58
out=pathlib.Path('/run/h713-dsp-minimum-export')
out.mkdir(exist_ok=False)
(out/'state.json').write_text(json.dumps(s,indent=2)+'\n')
(out/'boot-id.txt').write_text(boot+'\n')
(out/'cmdline.txt').write_text(pathlib.Path('/proc/cmdline').read_text())
(out/'journal.txt').write_bytes(subprocess.check_output(['journalctl','_BOOT_ID='+boot.replace('-',''),'_TRANSPORT=kernel','--no-pager','-o','cat']))
archive=pathlib.Path('/run/h713-dsp-minimum-export.tar.gz')
with tarfile.open(archive,'x:gz') as t:
    t.add(r,arcname='board-export')
    t.add(out,arcname='final')
    t.add(b/'arm-proof.json',arcname='arm-proof.json')
print(json.dumps({'boot_id':boot,'size':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}))
