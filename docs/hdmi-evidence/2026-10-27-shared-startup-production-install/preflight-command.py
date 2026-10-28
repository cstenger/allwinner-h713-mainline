expected={'schema': 'h713-shared-startup-update-v1', 'fit_sha256': '0877293b3a71b9ccd28c0f0ef9725752a86dffd243851a5213eb023cd3a51c70', 'previous': {'h713-hdmi.scr': '391835c5400cc5e583be8c1b82144ff85e03b483c8502b412147c6f7d9abb376', 'h713-hdmi.cmd': '298fb56d6525e4984d75fd2a0dbe998dd6dba7e813393dd798a4a32371de99fb'}, 'candidate': {'h713-hdmi.scr': 'fcea3a9589432f9b44781178d70433486aac5872a618970039b3326744e7fe7b', 'h713-hdmi.cmd': '9be0cbe3d00d3bf3717f50f30d00b70eb4e546b1926e2becc7585df25593f60a'}, 'gp6': {'cold': '00000000', 'launch': '48444d49', 'healthy': '48444f4b', 'unknown': 'logo-only'}, 'preboot': 'if itest.l *0x0709011c == 0xfa57b007; then mw.l 0x0709011c 0; run fastboot_mode; elif itest.l *0x0709011c == 0xb007c0de; then mw.l 0x0709011c 0; setenv bootdelay -1; fi; usb start', 'bootcmd': 'if fatload mmc 1:2 0x52000000 h713-hdmi.scr; then source 0x52000000; else echo HDMI startup script missing - use h713_hdmi_previous_bootcmd for recovery; fi', 'requires_policy_and_install_approval': True}

import pathlib,os,zlib,struct,hashlib,json,subprocess
P=pathlib.Path
# Documented installed narrowing defect: active environment LBA 0x32ec00.
fd=os.open('/dev/mmcblk0',os.O_RDONLY|os.O_CLOEXEC)
try:raw=os.pread(fd,0x10000,0x32ec00*512)
finally:os.close(fd)
assert len(raw)==0x10000
stored=struct.unpack('<I',raw[:4])[0];actual=zlib.crc32(raw[4:]);assert actual==stored,'active saved environment CRC mismatch'
env=dict(entry.split(b'=',1) for entry in raw[4:].split(b'\0\0',1)[0].split(b'\0') if b'=' in entry)
r={'active_env_lba':'0x32ec00','saved_env_sha256':hashlib.sha256(raw).hexdigest(),'saved_env_crc':'%08x'%actual,'preboot':env[b'preboot'].decode(),'bootcmd':env[b'bootcmd'].decode()}
assert r['preboot']==expected['preboot'];assert r['bootcmd']==expected['bootcmd']
source=subprocess.run(['findmnt','-n','-o','SOURCE','/mnt/boot'],capture_output=True,text=True)
if source.returncode!=0:
 assert P('/mnt/boot').is_dir()
 subprocess.run(['mount','-t','vfat','/dev/mmcblk0p2','/mnt/boot'],check=True)
source=subprocess.run(['findmnt','-n','-o','SOURCE','/mnt/boot'],capture_output=True,text=True,check=True).stdout.strip()
assert source=='/dev/mmcblk0p2';r['fat_source']=source
for name in ('h713-hdmi.scr','h713-kernel.fit'):r[name]=hashlib.sha256((P('/mnt/boot')/name).read_bytes()).hexdigest()
assert r['h713-hdmi.scr']==expected['previous']['h713-hdmi.scr'];assert r['h713-kernel.fit']==expected['fit_sha256']
print(json.dumps(r,indent=2))
