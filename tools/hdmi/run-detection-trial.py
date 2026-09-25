#!/usr/bin/env python3
"""Run a bounded sink trial and record source-side DRM evidence.

With --run-hdmird, start the fixed callback-aware HDMI daemon command as soon
as the source connector is enabled.  Keeping that trigger inside this monitor
avoids spending the short HPD assertion window on host-side orchestration.
With --tvfe-only, test HPD/EDID without explicitly holding TVCAP or enabling
receiver clocks. --probe-port-status samples the
firmware's read-only HDMI status RPC before, during, and after the window.
--probe-port-cache samples the guarded MIPS DRAM-only TMDS count cache.
"""
import argparse,hashlib,json,subprocess,sys,time
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
parser.add_argument('--probe-port-cache',action='store_true',help='Sample the guarded MIPS HDMI port cache in DRAM during the signal window')
parser.add_argument('--probe-framebuf',action='store_true',help='Hash reserved framebuf pages before/during/after video (read-only)')
parser.add_argument('--dump-candidate',action='store_true',help='Save two read-only 320 KiB candidate memory samples during video')
parser.add_argument('--probe-ring',action='store_true',help='Sample CRC changes across six candidate luma slots during video')
parser.add_argument('--dump-nv16',action='store_true',help='Save one read-only Y/UV candidate pair and color PNG during video')
parser.add_argument('--dump-coherent',action='store_true',help='Save double-checked completed NV16 frames and color PNGs during video')
parser.add_argument('--coherent-count',type=int,choices=range(1,9),default=1,help='Verified frames to save with --dump-coherent (default: 1)')
parser.add_argument('--read-detn',action='store_true',help='Also run the optional DETN register snapshot when the GPU connects')
args=parser.parse_args()
if args.tvfe_only and args.read_detn:
 parser.error('--read-detn requires the full receiver power hold')
if args.coherent_count>1 and not args.dump_coherent:
 parser.error('--coherent-count requires --dump-coherent')
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
if args.probe_port_cache:
 check_cmd+=' && test -f /root/hdmi-safe-trace/read-mips-port-cache.py'
if args.probe_framebuf:
 check_cmd+=' && test -f /root/hdmi-safe-trace/read-framebuf-pages.py'
if args.dump_candidate:
 check_cmd+=' && test -f /root/hdmi-safe-trace/read-candidate-frame.py'
if args.probe_ring:
 check_cmd+=' && test -f /root/hdmi-safe-trace/read-framebuf-ring.py'
if args.dump_nv16:
 check_cmd+=' && test -f /root/hdmi-safe-trace/read-nv16-pair.py'
if args.dump_coherent:
 check_cmd+=' && test -f /root/hdmi-safe-trace/read-coherent-frame.py'
if args.read_detn:
 check_cmd+=' && test -f /tmp/h713-check-power.sh'
if args.run_hdmird:
 check_cmd+=' && test -d /sys/module/h713_thdmirx_init && test -d /sys/module/hy310_cpu_comm && test -x /root/hy310-hdmird-callback'
check=ssh(check_cmd)
if check.returncode:raise SystemExit('Required target prerequisites are missing.')
command=f'set -e; if test -d /sys/module/h713_scp_probe; then rmmod h713_scp_probe; fi; insmod /tmp/h713-ddc-pins.ko run=1; insmod /tmp/h713-scp-probe.ko run=1 edid_trial=1 stock_io={int(args.stock_io)} hold_ms={args.seconds*1000}; dmesg | tail -7; cat /sys/module/h713_scp_probe/parameters/peripheral_restored /sys/module/h713_scp_probe/parameters/restored /sys/module/h713_scp_probe/parameters/edid_mismatch'
records=[];last=None;receiver=None;daemon=None;start=time.monotonic();ended=None;result=1
port_status=[];last_port_sample=-10
port_cache=[];last_cache_sample=-10
framebuf=[];last_frame_sample=-10
candidate_times=[]
ring_done=False
nv16_done=False
nv16_failed=False
coherent_done=False
coherent_failed=False
def probe_port_status(phase):
 r=ssh('timeout 5s /root/cpu-comm-probe THal_Vp_HDMI_GetPortStatus_1_000')
 item={'seconds':round(time.monotonic()-start,3),'phase':phase,'returncode':r.returncode,'output':r.stdout+r.stderr}
 port_status.append(item);print(json.dumps({'port_status':item}),flush=True)
 return r.returncode==0
def probe_port_cache(phase):
 r=ssh('python3 /root/hdmi-safe-trace/read-mips-port-cache.py')
 item={'seconds':round(time.monotonic()-start,3),'phase':phase,'returncode':r.returncode,'output':r.stdout+r.stderr}
 port_cache.append(item);print(json.dumps({'port_cache':item}),flush=True)
 return r.returncode==0
def probe_framebuf(phase):
 r=ssh('python3 /root/hdmi-safe-trace/read-framebuf-pages.py')
 if r.returncode:
  print(json.dumps({'framebuf_error':r.stderr,'phase':phase}),flush=True)
  return False
 try: snapshot=json.loads(r.stdout)
 except ValueError:
  print(json.dumps({'framebuf_error':'invalid JSON','phase':phase}),flush=True)
  return False
 (OUT/f'framebuf-{phase}.json').write_text(json.dumps(snapshot,separators=(',',':'))+'\n')
 baseline=framebuf[0]['crc32'] if framebuf else snapshot['crc32']
 changed=[i for i,(a,b) in enumerate(zip(baseline,snapshot['crc32'])) if a!=b]
 item={'phase':phase,'seconds':round(time.monotonic()-start,3),'changed_pages':len(changed),'first_changed_pages':changed[:32]}
 framebuf.append(snapshot)
 print(json.dumps({'framebuf':item}),flush=True)
 return True
def dump_candidate():
 r=subprocess.run(SSH+['python3 /root/hdmi-safe-trace/read-candidate-frame.py'],capture_output=True,timeout=15)
 if r.returncode or len(r.stdout)!=0x50000:
  print(json.dumps({'candidate_error':r.stderr.decode(errors='replace'),'bytes':len(r.stdout)}),flush=True)
  return False
 name=f'candidate-{len(candidate_times)+1}.bin'
 (OUT/name).write_bytes(r.stdout)
 png=OUT/name.replace('.bin','.png')
 subprocess.run([sys.executable,str(Path(__file__).with_name('luma-to-png.py')),str(OUT/name),str(png)],check=True,capture_output=True)
 candidate_times.append(round(time.monotonic()-start,3))
 print(json.dumps({'candidate':name,'png':png.name,'seconds':candidate_times[-1],'bytes':len(r.stdout)}),flush=True)
 return True
def probe_ring():
 r=ssh('python3 /root/hdmi-safe-trace/read-framebuf-ring.py')
 if r.returncode:
  print(json.dumps({'ring_error':r.stderr}),flush=True)
  return False
 data=json.loads(r.stdout)
 (OUT/'ring.json').write_text(json.dumps(data,indent=2)+'\n')
 changes=[sum(a['crc32'][i]!=b['crc32'][i] for a,b in zip(data['samples'],data['samples'][1:])) for i in range(6)]
 print(json.dumps({'ring_samples':len(data['samples']),'slot_changes':changes}),flush=True)
 return True
def dump_nv16():
 r=subprocess.run(SSH+['python3 /root/hdmi-safe-trace/read-nv16-pair.py --pair 0'],capture_output=True,timeout=15)
 if r.returncode or len(r.stdout)!=2*640*480:
  print(json.dumps({'nv16_error':r.stderr.decode(errors='replace'),'bytes':len(r.stdout)}),flush=True)
  return False
 raw=OUT/'candidate-nv16.bin';png=OUT/'candidate-nv16.png'
 raw.write_bytes(r.stdout)
 subprocess.run([sys.executable,str(Path(__file__).with_name('nv16-to-png.py')),str(raw),str(png)],check=True,capture_output=True)
 print(json.dumps({'nv16':raw.name,'png':png.name,'seconds':round(time.monotonic()-start,3),'bytes':len(r.stdout)}),flush=True)
 return True
def dump_coherent():
 r=subprocess.run(SSH+[f'python3 /root/hdmi-safe-trace/read-coherent-frame.py --timeout 8 --count {args.coherent_count}'],capture_output=True,timeout=12)
 if r.returncode or len(r.stdout)!=args.coherent_count*2*640*480:
  print(json.dumps({'coherent_error':r.stderr.decode(errors='replace'),'bytes':len(r.stdout)}),flush=True)
  return False
 try: metadata=[json.loads(line) for line in r.stderr.splitlines()]
 except ValueError:
  print(json.dumps({'coherent_error':'invalid frame metadata'}),flush=True)
  return False
 if len(metadata)!=args.coherent_count:
  print(json.dumps({'coherent_error':'frame metadata count mismatch'}),flush=True)
  return False
 (OUT/'coherent.json').write_text(json.dumps(metadata,indent=2)+'\n')
 for i,item in enumerate(metadata):
  stem='coherent-nv16' if args.coherent_count==1 else f'coherent-{i+1:02d}-nv16'
  raw=OUT/(stem+'.bin');png=OUT/(stem+'.png')
  raw.write_bytes(r.stdout[i*2*640*480:(i+1)*2*640*480])
  subprocess.run([sys.executable,str(Path(__file__).with_name('nv16-to-png.py')),str(raw),str(png)],check=True,capture_output=True)
  print(json.dumps({'coherent':raw.name,'png':png.name,'metadata':item,'seconds':round(time.monotonic()-start,3)}),flush=True)
 return True
if args.probe_port_status and not probe_port_status('before'):
 raise SystemExit('Port-status RPC failed before the signal window; leaving HPD unchanged.')
if args.probe_port_cache and not probe_port_cache('before'):
 raise SystemExit('MIPS port-cache probe failed before the signal window; leaving HPD unchanged.')
if args.probe_framebuf and not probe_framebuf('before'):
 raise SystemExit('Framebuf probe failed before the signal window; leaving HPD unchanged.')
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
  if args.probe_port_cache and s['status']=='connected' and s['enabled']=='enabled' and time.monotonic()-last_cache_sample>=2:
   probe_port_cache('video-enabled');last_cache_sample=time.monotonic()
  if args.probe_framebuf and s['status']=='connected' and s['enabled']=='enabled' and time.monotonic()-last_frame_sample>=4:
   probe_framebuf('video-'+str(len(framebuf)));last_frame_sample=time.monotonic()
  if args.dump_candidate and s['status']=='connected' and s['enabled']=='enabled' and len(candidate_times)<2 and (not candidate_times or time.monotonic()-start-candidate_times[-1]>=4):
   dump_candidate()
  if args.probe_ring and not ring_done and s['status']=='connected' and s['enabled']=='enabled':
   probe_ring();ring_done=True
  if args.dump_nv16 and not nv16_done and s['status']=='connected' and s['enabled']=='enabled':
   nv16_failed=not dump_nv16();nv16_done=True
  if args.dump_coherent and not coherent_done and s['status']=='connected' and s['enabled']=='enabled':
   coherent_failed=not dump_coherent();coherent_done=True
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
 if args.probe_port_cache:
  probe_port_cache('after')
  (OUT/'port-cache.json').write_text(json.dumps(port_cache,indent=2)+'\n')
 if args.probe_framebuf:
  probe_framebuf('after')
 if cleanup.returncode:result=cleanup.returncode
 if nv16_failed:result=1
 if coherent_failed:result=1
raise SystemExit(result)
