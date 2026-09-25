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
parser.add_argument('--v4l2-frames',type=int,default=0,help='Capture this many NV16 frames from /dev/video1 with FFmpeg (1–120)')
parser.add_argument('--read-detn',action='store_true',help='Also run the optional DETN register snapshot when the GPU connects')
args=parser.parse_args()
if args.tvfe_only and args.read_detn:
 parser.error('--read-detn requires the full receiver power hold')
if args.coherent_count>1 and not args.dump_coherent:
 parser.error('--coherent-count requires --dump-coherent')
if args.v4l2_frames and args.seconds<10:
 parser.error('--v4l2-frames requires a signal window of at least 10 seconds')
if not 0<=args.v4l2_frames<=120:
 parser.error('--v4l2-frames must be between 0 and 120')
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
if args.v4l2_frames:
 check_cmd+=' && test -d /sys/module/h713_hdmi_v4l2 && test "$(cat /sys/class/video4linux/video1/name)" = "H713 HDMI1 ring capture" && command -v ffmpeg >/dev/null'
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
v4l2_proc=None
v4l2_remote=f'/tmp/{OUT.name}-v4l2.nv16'
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
  if args.v4l2_frames and s['status']=='connected' and s['enabled']=='enabled' and v4l2_proc is None:
   v4l2_cmd=(f'timeout -s KILL {args.seconds}s ffmpeg -nostdin -y -hide_banner -loglevel info '
             f'-f v4l2 -input_format nv16 -video_size 640x480 -i /dev/video1 '
             f'-fps_mode passthrough -frames:v {args.v4l2_frames} -pix_fmt nv16 '
             f'-f rawvideo {v4l2_remote}')
   v4l2_proc=subprocess.Popen(SSH+[v4l2_cmd],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
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
 if args.v4l2_frames:
  if v4l2_proc is None:
   print(json.dumps({'v4l2_error':'GPU never enabled output'}),flush=True)
   result=1
  else:
   try:
    a,b=v4l2_proc.communicate(timeout=5)
   except subprocess.TimeoutExpired:
    v4l2_proc.kill();a,b=v4l2_proc.communicate()
   (OUT/'v4l2-ffmpeg.log').write_text(a+b)
   if v4l2_proc.returncode:
    print(json.dumps({'v4l2_error':f'FFmpeg exited {v4l2_proc.returncode}','log_tail':(a+b)[-800:]}),flush=True)
    result=1
   else:
    local=OUT/'v4l2.nv16'
    copied=subprocess.run(['scp','-F','/dev/null','-o','BatchMode=yes','-o','ConnectTimeout=5',f'root@192.168.4.1:{v4l2_remote}',str(local)],capture_output=True,timeout=45)
    if copied.returncode or local.stat().st_size!=args.v4l2_frames*2*640*480:
     print(json.dumps({'v4l2_error':copied.stderr.decode(errors='replace'),'bytes':local.stat().st_size if local.exists() else 0}),flush=True)
     result=1
    else:
     for index in (0,args.v4l2_frames-1):
      with local.open('rb') as stream:
       stream.seek(index*2*640*480)
       frame=stream.read(2*640*480)
      raw=OUT/f'v4l2-frame-{index+1:03d}.bin';png=OUT/f'v4l2-frame-{index+1:03d}.png'
      raw.write_bytes(frame)
      subprocess.run([sys.executable,str(Path(__file__).with_name('nv16-to-png.py')),str(raw),str(png)],check=True,capture_output=True)
     summary=subprocess.run([sys.executable,str(Path(__file__).with_name('summarize-v4l2-stream.py')),str(local)],text=True,capture_output=True,check=True)
     (OUT/'v4l2-summary.json').write_text(summary.stdout)
     print(json.dumps({'v4l2_stream':str(local),'frames':args.v4l2_frames,'first_png':'v4l2-frame-001.png','last_png':f'v4l2-frame-{args.v4l2_frames:03d}.png'}),flush=True)
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
