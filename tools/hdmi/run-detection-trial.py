#!/usr/bin/env python3
"""Run the staged ten-second sink trial and record source-side DRM evidence."""
import argparse,hashlib,json,subprocess,time
from datetime import datetime,timezone
from pathlib import Path
SSH=['ssh','-F','/dev/null','-o','BatchMode=yes','-o','ConnectTimeout=5','-o','ServerAliveInterval=2','-o','ServerAliveCountMax=1','root@192.168.4.1']
CONNECTOR=Path('/sys/class/drm/card1-HDMI-A-1')
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--stock-io',action='store_true',help='Use four saved/restored stock timing/control settings')
parser.add_argument('--seconds',type=int,choices=range(1,31),default=10,help='Bounded HPD hold in seconds (1–30)')
args=parser.parse_args()
OUT=Path('/tmp')/('h713-hdmi-trial-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
OUT.mkdir();print(f'Logs: {OUT}',flush=True)
def ssh(command):return subprocess.run(SSH+[command],text=True,capture_output=True,timeout=15)
def sample():
 try:return {'status':(CONNECTOR/'status').read_text().strip(),'edid':(CONNECTOR/'edid').read_bytes(),'modes':(CONNECTOR/'modes').read_text().splitlines(),'enabled':(CONNECTOR/'enabled').read_text().strip()}
 except OSError as e:return {'status':str(e),'edid':b'','modes':[],'enabled':'unknown'}
if sample()['status']!='disconnected':raise SystemExit('Expected disconnected test connector; leaving hardware unchanged.')
check=ssh('test -d /sys/module/h713_hdmi_power && test -d /sys/module/h713_edid_clock && test -L /sys/bus/platform/devices/h713-edid-clock-hold/driver')
if check.returncode:raise SystemExit('Required power/EDID holds are missing.')
command=f'set -e; if test -d /sys/module/h713_scp_probe; then rmmod h713_scp_probe; fi; insmod /tmp/h713-ddc-pins.ko run=1; insmod /tmp/h713-scp-probe.ko run=1 edid_trial=1 stock_io={int(args.stock_io)} hold_ms={args.seconds*1000}; dmesg | tail -7; cat /sys/module/h713_scp_probe/parameters/peripheral_restored /sys/module/h713_scp_probe/parameters/restored /sys/module/h713_scp_probe/parameters/edid_mismatch'
p=subprocess.Popen(SSH+[command],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
records=[];last=None;receiver=None;start=time.monotonic();ended=None;result=1
try:
 while time.monotonic()-start<args.seconds+12:
  s=sample();digest=hashlib.sha256(s['edid']).hexdigest() if s['edid'] else None
  r={'seconds':round(time.monotonic()-start,3),'status':s['status'],'edid_bytes':len(s['edid']),'edid_sha256':digest,'modes':s['modes'],'enabled':s['enabled']}
  key=(r['status'],digest,tuple(r['modes']),r['enabled'])
  if key!=last:
   records.append(r);print(json.dumps(r),flush=True);last=key
   if digest:(OUT/f'edid-{digest[:16]}.bin').write_bytes(s['edid'])
  if s['status']=='connected' and receiver is None:
   receiver=subprocess.Popen(SSH+['bash /tmp/h713-check-power.sh --read-thdmirx'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  if p.poll() is not None:
   ended=ended or time.monotonic()
   if time.monotonic()-ended>2:break
  time.sleep(.25)
 if p.poll() is None:p.kill()
 stdout,stderr=p.communicate(timeout=3);(OUT/'target.log').write_text(stdout+stderr);print(stdout+stderr,flush=True);result=p.returncode
finally:
 if receiver is not None:
  try:
   a,b=receiver.communicate(timeout=3);(OUT/'receiver.log').write_text(a+b)
  except subprocess.TimeoutExpired:
   receiver.kill();a,b=receiver.communicate();(OUT/'receiver.log').write_text(a+b+'\nRead did not complete.\n')
 cleanup=ssh('if test -d /sys/module/h713_scp_probe; then rmmod h713_scp_probe; fi; if test -d /sys/module/h713_ddc_pins; then rmmod h713_ddc_pins; fi; /root/mmio-rw r 7000400; /root/mmio-rw r 7022004')
 (OUT/'cleanup.log').write_text(cleanup.stdout+cleanup.stderr);print(cleanup.stdout+cleanup.stderr,flush=True)
 (OUT/'source.json').write_text(json.dumps(records,indent=2)+'\n')
 if cleanup.returncode:result=cleanup.returncode
raise SystemExit(result)
