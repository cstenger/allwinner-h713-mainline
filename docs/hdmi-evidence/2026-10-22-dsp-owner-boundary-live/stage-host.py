import pathlib,subprocess,json,tarfile,io
p=pathlib.Path(__file__).resolve().parent
ssh=['ssh','-F','/dev/null','-o','BatchMode=yes','-o','ConnectTimeout=5','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=1','root@192.168.4.1']
remote=r'''
import pathlib,os,hashlib,subprocess,json
P=pathlib.Path
boot=P('/proc/sys/kernel/random/boot_id').read_text().strip()
assert boot!='dcfe762c-9cb5-44ca-a546-049f03e2a1fd'
assert os.uname().release=='6.18.38' and os.uname().version=='#1 SMP Fri Oct 16 15:44:49 PDT 2026'
cmd=P('/proc/cmdline').read_text().split();assert 'panic=0' in cmd and 'h713_owner_boundary=1' in cmd
assert P('/proc/sys/kernel/panic').read_text().strip()=='0'
assert P('/proc/device-tree/chosen/h713,dsp-owner-boundary-v1').read_bytes()==bytes.fromhex('4f574e31')
h=P('/proc/device-tree/chosen/h713,hdmi-boot-v1').read_bytes();assert len(h)==12 and h[:4]==bytes.fromhex('48444d49') and int.from_bytes(h[4:8],'big')==0 and int.from_bytes(h[8:12],'big')>0
for u in ('capture','signal','speaker'):
 n='h713-hdmi-'+u+'.service';assert 'systemd.mask='+n in cmd
 assert subprocess.run(['systemctl','is-active',n],capture_output=True,text=True).stdout.strip()=='inactive'
for n in ('h713_hdmi_audio','h713_hdmi_receiver','h713_hdmi_signal','h713_ddc_pins','h713_scp_probe','h713_hdmi_dsp_probe','h713_hdmi_dsp_observe','h713_hdmi_power','h713_hdmi_tvfe_hold'):assert not P('/sys/module',n).exists(),n
sha=lambda p:hashlib.sha256(P(p).read_bytes()).hexdigest()
assert sha('/usr/lib/systemd/system-shutdown/h713-hdmi-hold-guard')=='5ad26677ac791d2be659db88165d689d997705f45ee4d516015e786342ad764d'
bak=P('/root/hdmi-dsp-retention-2026-10-21/previous-hold-guard');assert sha(bak)=='96f37655b33bf78d95b33fa4f431721be5a7506c73c12dcd4df58032cad27113' and bak.stat().st_mode&0o7777==0o755
assert not P('/run/h713-owner-boundary').exists()
subprocess.run(['dmesg','-n','7'],check=True)
assert int(P('/proc/sys/kernel/printk').read_text().split()[0])==7
b=P('/root/hdmi-dsp-owner-boundary-2026-10-22/boundary');b.mkdir(exist_ok=False)
print(json.dumps({'boot_id':boot,'uname_version':os.uname().version,'cmdline':cmd,'owners_absent':True,'services_masked_inactive':True,'guard_original_backup_verified':True,'remote_bundle_directory':str(b)}))
'''
r=subprocess.run(ssh+['python3 -'],input=remote,text=True,capture_output=True,timeout=20)
(p/'cold-health.log').open('x').write(r.stdout+r.stderr);print(r.stdout+r.stderr);assert r.returncode==0
buf=io.BytesIO()
with tarfile.open(fileobj=buf,mode='w') as t:
 for f in (p.parent/'candidate/bundle').rglob('*'):
  if f.is_file():t.add(f,arcname=str(f.relative_to(p.parent/'candidate/bundle')))
 t.add(p/'cold-boot/arm-intent.json',arcname='arm-intent.json')
 t.add(p/'cold-boot/sham-record.json',arcname='sham-record.json')
r=subprocess.run(ssh+['tar -x -C /root/hdmi-dsp-owner-boundary-2026-10-22/boundary'],input=buf.getvalue(),capture_output=True,timeout=20)
(p/'stage.log').open('xb').write(r.stdout+r.stderr);assert r.returncode==0;print('Exact bundle plus fresh intent and sham staged')
