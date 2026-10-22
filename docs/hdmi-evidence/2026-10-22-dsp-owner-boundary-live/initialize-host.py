import pathlib,subprocess
p=pathlib.Path(__file__).resolve().parent
ssh=['ssh','-F','/dev/null','-o','BatchMode=yes','-o','ConnectTimeout=5','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=1','root@192.168.4.1']
b='/root/hdmi-dsp-owner-boundary-2026-10-22/boundary'
try:r=subprocess.run(ssh+['python3 '+b+'/dsp-owner-boundary.py --bundle '+b+' initialize --intent '+b+'/arm-intent.json'],capture_output=True,timeout=60)
except subprocess.TimeoutExpired as e:
 (p/'initialize-uncertain.log').open('xb').write((e.stdout or b'')+(e.stderr or b'')+b'\nHOST DEADLINE uncertain; no retry\n');raise
(p/'initialize.log').open('xb').write(r.stdout+r.stderr);print(r.stdout.decode()+r.stderr.decode());raise SystemExit(r.returncode)
