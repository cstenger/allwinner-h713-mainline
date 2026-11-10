import subprocess,json,pathlib,hashlib,tarfile
p=pathlib.Path(__file__).resolve().parent
ssh=['ssh','-F','/dev/null','-o','BatchMode=yes','-o','ConnectTimeout=5','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=1','root@192.168.4.1']
r=subprocess.run(ssh+['python3 /root/hdmi-dsp-owner-boundary-2026-10-22/sham/dsp-owner-boundary.py --bundle /root/hdmi-dsp-owner-boundary-2026-10-22/sham export'],capture_output=True,timeout=20)
(p/'export.log').open('xb').write(r.stdout+r.stderr)
assert r.returncode==0
m=json.loads(r.stdout);print(m)
r=subprocess.run(ssh+['cat '+m['archive']],capture_output=True,timeout=20)
assert r.returncode==0 and len(r.stdout)==m['size'] and hashlib.sha256(r.stdout).hexdigest()==m['sha256']
a=p/'board-export.tar.gz';a.open('xb').write(r.stdout)
with tarfile.open(a) as t:t.extractall(p,filter='data')
print('Host archive verified and extracted')
