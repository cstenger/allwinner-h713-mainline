#!/usr/bin/env python3
"""Run a bounded sink trial and record source-side DRM evidence.

With --run-hdmird, start the fixed callback-aware HDMI daemon command as soon
as the source connector is enabled.  Keeping that trigger inside this monitor
avoids spending the short HPD assertion window on host-side orchestration.
With --tvfe-only, test HPD/EDID without explicitly holding TVCAP or enabling
receiver clocks. --probe-port-status samples the
firmware's read-only HDMI status RPC before, during, and after the window.
"""
import argparse,hashlib,json,subprocess,time
from datetime import datetime,timezone
from pathlib import Path
SSH=['ssh','-F','/dev/null','-o','BatchMode=yes','-o','ConnectTimeout=5','-o','ServerAliveInterval=2','-o','ServerAliveCountMax=1','root@192.168.4.1']
CONNECTOR=Path('/sys/class/drm/card1-HDMI-A-1')
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--stock-io',action='store_true',help='Use four saved/restored stock timing/control settings')
parser.add_argument('--seconds',type=int,choices=range(1,31),default=10,help='Bounded HPD hold in seconds (1–30)')
parser.add_argument('--run-hdmird',action='store_true',help='Run the fixed SetSource(3) trial as soon as the source is enabled')
parser.add_argument('--tvfe-only',action='store_true',help='Require TVFE and EDID clock only; no explicit TVCAP/receiver-clock hold')
parser.add_argument('--probe-port-status',action='store_true',help='Sample the read-only MIPS HDMI port-status RPC during the signal window')
parser.add_argument('--read-detn',action='store_true',help='Also run the optional DETN register snapshot when the GPU connects')
args=parser.parse_args()
if args.tvfe_only and args.read_detn:
 parser.error('--read-detn requires the full receiver power hold')
OUT=Path('/tmp')/('h713-hdmi-trial-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
OUT.mkdir();print(f'Logs: {OUT}',flush=True)
def ssh(command):return subprocess.run(SSH+[command],text=True,capture_output=True,timeout=15)
def sample():
 try:return {'status':(CONNECTOR/'status').read_text().strip(),'edid':(CONNECTOR/'edid').read_bytes(),'modes':(CONNECTOR/'modes').read_text().splitlines(),'enabled':(CONNECTOR/'enabled').read_text().strip()}
 except OSError as e:return {'status':str(e),'edid':b'','modes':[],'enabled':'unknown'}
if sample()['status']!='disconnected':raise SystemExit('Expected disconnected test connector; leaving hardware unchanged.')
check_cmd='test -d /sys/module/h713_hdmi_power && test -d /sys/module/h713_edid_clock && test -L /sys/bus/platform/devices/h713-edid-clock-hold/driver'
if args.tvfe_only:
 check_cmd+=' && test "$(cat /sys/devices/h713-hdmi-tvfe/power/runtime_status)" = active'
else:
 check_cmd+=' && test "$(cat /sys/devices/h713-hdmi-tvcap/power/runtime_status)" = active'
if args.probe_port_status:
 check_cmd+=' && test -d /sys/module/hy310_cpu_comm && test -x /root/cpu-comm-probe'
if args.read_detn:
 check_cmd+=' && test -f /tmp/h713-check-power.sh'
if args.run_hdmird:
 check_cmd+=' && test -d /sys/module/h713_thdmirx_init && test -d /sys/module/hy310_cpu_comm && test -x /root/hy310-hdmird-callback'
check=ssh(check_cmd)
if check.returncode:raise SystemExit('Required target prerequisites are missing.')
command=f'set -e; if test -d /sys/module/h713_scp_probe; then rmmod h713_scp_probe; fi; insmod /tmp/h713-ddc-pins.ko run=1; insmod /tmp/h713-scp-probe.ko run=1 edid_trial=1 stock_io={int(args.stock_io)} hold_ms={args.seconds*1000}; dmesg | tail -7; cat /sys/module/h713_scp_probe/parameters/peripheral_restored /sys/module/h713_scp_probe/parameters/restored /sys/module/h713_scp_probe/parameters/edid_mismatch'
records=[];last=None;receiver=None;daemon=None;start=time.monotonic();ended=None;result=1
port_status=[];last_port_sample=-10
def probe_port_status(phase):
 r=ssh('timeout 5s /root/cpu-comm-probe THal_Vp_HDMI_GetPortStatus_1_000')
 item={'seconds':round(time.monotonic()-start,3),'phase':phase,'returncode':r.returncode,'output':r.stdout+r.stderr}
 port_status.append(item);print(json.dumps({'port_status':item}),flush=True)
 return r.returncode==0
if args.probe_port_status and not probe_port_status('before'):
 raise SystemExit('Port-status RPC failed before the signal window; leaving HPD unchanged.')
p=subprocess.Popen(SSH+[command],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
try:
 while time.monotonic()-start<args.seconds+12:
  s=sample();digest=hashlib.sha256(s['edid']).hexdigest() if s['edid'] else None
  r={'seconds':round(time.monotonic()-start,3),'status':s['status'],'edid_bytes':len(s['edid']),'edid_sha256':digest,'modes':s['modes'],'enabled':s['enabled']}
  key=(r['status'],digest,tuple(r['modes']),r['enabled'])
  if key!=last:
   records.append(r);print(json.dumps(r),flush=True);last=key
   if digest:(OUT/f'edid-{digest[:16]}.bin').write_bytes(s['edid'])
  if args.read_detn and s['status']=='connected' and receiver is None and not args.tvfe_only:
   receiver=subprocess.Popen(SSH+['bash /tmp/h713-check-power.sh --read-thdmirx'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  if args.probe_port_status and s['status']=='connected' and s['enabled']=='enabled' and time.monotonic()-last_port_sample>=2:
   probe_port_status('video-enabled');last_port_sample=time.monotonic()
  if args.run_hdmird and s['enabled']=='enabled' and daemon is None:
   daemon=subprocess.Popen(SSH+['timeout 18s /root/hy310-hdmird-callback --src 3 --no-socket --post-signal-timeout 6000'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  if p.poll() is not None:
   ended=ended or time.monotonic()
   if time.monotonic()-ended>2:break
  time.sleep(.25)
 if p.poll() is None:p.kill()
 stdout,stderr=p.communicate(timeout=3);(OUT/'target.log').write_text(stdout+stderr);print(stdout+stderr,flush=True);result=p.returncode
finally:
 if daemon is not None:
  try:
   a,b=daemon.communicate(timeout=3);(OUT/'daemon.log').write_text(a+b)
  except subprocess.TimeoutExpired:
   daemon.kill();a,b=daemon.communicate();(OUT/'daemon.log').write_text(a+b+'\nDaemon did not complete.\n')
  if daemon.returncode:result=daemon.returncode
 if receiver is not None:
  try:
   a,b=receiver.communicate(timeout=3);(OUT/'receiver.log').write_text(a+b)
  except subprocess.TimeoutExpired:
   receiver.kill();a,b=receiver.communicate();(OUT/'receiver.log').write_text(a+b+'\nRead did not complete.\n')
  if receiver.returncode:result=receiver.returncode
 cleanup=ssh('if test -d /sys/module/h713_scp_probe; then rmmod h713_scp_probe; fi; if test -d /sys/module/h713_ddc_pins; then rmmod h713_ddc_pins; fi; /root/mmio-rw r 7000400; /root/mmio-rw r 7022004')
 (OUT/'cleanup.log').write_text(cleanup.stdout+cleanup.stderr);print(cleanup.stdout+cleanup.stderr,flush=True)
 (OUT/'source.json').write_text(json.dumps(records,indent=2)+'\n')
 if args.probe_port_status:
  probe_port_status('after')
  (OUT/'port-status.json').write_text(json.dumps(port_status,indent=2)+'\n')
 if cleanup.returncode:result=cleanup.returncode
raise SystemExit(result)
