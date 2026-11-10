#!/usr/bin/env python3
"""Read-only HDMI session health for the warm shared-startup test.

One SSH call runs tools/hdmi/check-startup.sh unchanged on the board (after
the services settle) and samples the production audio path without adding
a reader: production's hdmi-speaker owns the HDMI capture PCM (GStreamer
alsasrc hw:H713HDMI -> plughw:Codec), so a second consumer cannot open it.
Two samples 3 s apart give the driver's period rate and xruns and the
speaker's codec playback progress. Whether the tone is audible is the
operator's check. The host side judges the record and compares the cold and
warm sessions. Nothing is written on the board except a scratch directory
in /run.
"""
import argparse,json,pathlib,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[2]
SSH=['ssh','-F','/dev/null','-o','BatchMode=yes','-o','ConnectTimeout=5','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=1','root@192.168.4.1']
RATE=48000
PERIOD_FRAMES=256     # driver period (hw_params period_size)
RATE_TOLERANCE=0.02   # measured rates within 2% of nominal (pointer jitter over 3 s is ~0.2%)
REMOTE=r'''
import json,os,pathlib,subprocess,sys,time
P=pathlib.Path;label=sys.argv[1];out={'label':label}
run=P('/run/h713-warm-shared');run.mkdir(exist_ok=True)
out['boot_id']=P('/proc/sys/kernel/random/boot_id').read_text().strip()
out['uptime']=float(P('/proc/uptime').read_text().split()[0])
h=P('/proc/device-tree/chosen/h713,hdmi-boot-v1');out['handoff']=h.read_bytes().hex() if h.exists() else None
# Services settle about 20 s after kernel start; wait for a final state, never restart anything.
units=('h713-hdmi-capture','h713-hdmi-signal')
deadline=time.monotonic()+120
while time.monotonic()<deadline:
    states=[subprocess.run(['systemctl','is-active',u],capture_output=True,text=True).stdout.strip() for u in units]
    if all(s in ('active','failed','inactive') for s in states) and 'activating' not in states:break
    time.sleep(2)
out['units']=dict(zip(units,states))
(run/'check-startup.sh').write_text(sys.stdin.read())
r=subprocess.run(['sh',str(run/'check-startup.sh')],capture_output=True,text=True,timeout=60)
out['check_startup']={'rc':r.returncode,'output':r.stdout+r.stderr}
import re
def status(path):
    return P(path).read_text() if P(path).exists() else ''
def owner(text):
    m=re.search(r'owner_pid\s*:\s*(\d+)',text)
    if not m:return None
    c=P('/proc/'+m.group(1)+'/comm');return c.read_text().strip() if c.exists() else None
def ptr(text):
    m=re.search(r'hw_ptr\s*:\s*(\d+)',text);return int(m.group(1)) if m else None
def sample():
    cap=status('/proc/asound/H713HDMI/pcm0c/sub0/status');play=status('/proc/asound/Codec/pcm0p/sub0/status')
    prm=lambda k:int(P('/sys/module/h713_hdmi_audio/parameters/'+k).read_text())
    return {'t':time.monotonic(),'periods':prm('period_active'),'xruns':prm('period_xruns'),'capture_state':cap.split('\n',1)[0],
            'capture_owner':owner(cap),'capture_ptr':ptr(cap),'play_state':play.split('\n',1)[0],'play_owner':owner(play),'play_ptr':ptr(play)}
out['speaker']=subprocess.run(['systemctl','is-active','h713-hdmi-speaker'],capture_output=True,text=True).stdout.strip()
speaker_exec=subprocess.run(['systemctl','show','h713-hdmi-speaker','-p','ExecStart','--value'],capture_output=True,text=True).stdout
out['route_kind']='pipewire' if 'pipewire-speaker.py' in speaker_exec else 'direct'
if r.returncode==0 and P('/sys/module/h713_hdmi_audio').exists():
    # The speaker fades in after a silent pre-roll (cold boot: playback from ~80 s).
    deadline=time.monotonic()+150
    while time.monotonic()<deadline and not status('/proc/asound/Codec/pcm0p/sub0/status').startswith('state: RUNNING'):time.sleep(2)
    out['speaker_wait_s']=round(150-(deadline-time.monotonic()),1)
    a=sample();time.sleep(3);b=sample();out['flow']=[a,b]
if out['route_kind']=='pipewire':
    rpw=subprocess.run(['python3','/usr/lib/h713-hdmi-speaker/pipewire-speaker.py','check'],capture_output=True,text=True,timeout=15)
    out['pipewire_check']={'rc':rpw.returncode,'output':rpw.stdout,'stderr':rpw.stderr}
    if rpw.returncode==0:out['pipewire_route']=json.loads(rpw.stdout)
j=subprocess.run(['journalctl','-k','-b','--no-pager','-o','cat'],capture_output=True,text=True).stdout
out['dsp_lines']=[l for l in j.splitlines() if 'DSP versions' in l or 'patch verified' in l]
# Video is observed through the installed bridge; never open another stream.
def video_sample():
    base=P('/sys/module/h713_hdmi_v4l2/parameters')
    return {'t':time.monotonic(), 'signal':status('/sys/devices/platform/h713-hdmi-ring/signal').strip(),
            'units':{u:subprocess.run(['systemctl','is-active',u],capture_output=True,text=True).stdout.strip()
                     for u in ('h713-hdmi-ring','h713-hdmi-video')},
            'counters':{k:int((base/k).read_text()) if (base/k).exists() else None
                        for k in ('frames_produced','frames_delivered','frames_rejected')}}
a=video_sample();time.sleep(3);b=video_sample();out['video']=[a,b]
out['video_status']=subprocess.run(['systemctl','status','h713-hdmi-ring','h713-hdmi-video','--no-pager','-l'],capture_output=True,text=True).stdout
out['video_properties']=subprocess.run(['systemctl','show','h713-hdmi-video','-p','ActiveState,Result,NRestarts,ActiveEnterTimestampMonotonic,ExecMainStartTimestampMonotonic'],capture_output=True,text=True).stdout
out['video_journal']=subprocess.run(['journalctl','-b','-u','h713-hdmi-ring','-u','h713-hdmi-video','--no-pager','-o','short-monotonic'],capture_output=True,text=True).stdout
out['bridge_dmesg']=[l for l in j.splitlines() if 'h713-hdmi-v4l2' in l]
print(json.dumps(out))
'''
def evaluate_video(rec):
    reasons=[];samples=rec.get('video',[])
    if len(samples)!=2:return ['no video flow samples']
    a,b=samples
    if b['t']<=a['t']:reasons.append('invalid video sample interval')
    for s in samples:
        if s.get('signal')!='locked 1280x720':reasons.append('video signal not locked 1280x720')
        if any(s.get('units',{}).get(u)!='active' for u in ('h713-hdmi-ring','h713-hdmi-video')):
            reasons.append('video units not active')
    for k in ('frames_produced','frames_delivered','frames_rejected'):
        x,y=a.get('counters',{}).get(k),b.get('counters',{}).get(k)
        if x is None or y is None:reasons.append('missing video counter '+k)
        elif (y<=x if k!='frames_rejected' else y!=x):reasons.append('video counter failed '+k)
    if not rec.get('bridge_dmesg'):reasons.append('no bridge boot log')
    return reasons
def flow(rec):
    """Measured audio flow between the two samples, or None."""
    f=rec.get('flow')
    if not f or len(f)!=2:return None
    a,b=f;dt=b['t']-a['t']
    if dt<=0:return None
    # The DMA-position pointer is exact; the period counter undercounts ~1.4% on
    # hardware (coalesced one-shot IRQs), so it is reported but not judged.
    return {'dt':dt,'capture_rate':(b['capture_ptr']-a['capture_ptr'])/dt,'period_rate':(b['periods']-a['periods'])*PERIOD_FRAMES/dt,'xruns':b['xruns']-a['xruns'],
            'play_rate':(b['play_ptr']-a['play_ptr'])/dt if a.get('play_ptr') is not None and b.get('play_ptr') is not None else None,
            'capture_running':a['capture_state']==b['capture_state']=='state: RUNNING','play_running':a['play_state']==b['play_state']=='state: RUNNING',
            'owners':sorted({a['capture_owner'],b['capture_owner'],a['play_owner'],b['play_owner']},key=str)}
def evaluate(rec,require_video=False):
    """Pass only with the unchanged startup check, the DSP gate and audio flowing to the speaker."""
    out={'label':rec.get('label'),'boot_id':rec.get('boot_id'),'reasons':[]}
    cs=rec.get('check_startup',{})
    if cs.get('rc')!=0 or 'PASS' not in cs.get('output','').splitlines()[-1:]:out['reasons'].append('check-startup.sh did not pass')
    dsp=rec.get('dsp_lines',[])
    if not any('DSP versions 0000/0000' in l for l in dsp):out['reasons'].append('DSP did not start at 0/0')
    if not any('patch verified versions 1/1' in l for l in dsp):out['reasons'].append('DSP patch not verified 1/1')
    if rec.get('speaker')!='active':out['reasons'].append('h713-hdmi-speaker not active')
    f=flow(rec);out['flow']=f
    if f is None:out['reasons'].append('no audio flow samples')
    else:
        if not f['capture_running']:out['reasons'].append('capture PCM not RUNNING')
        if not f['play_running']:out['reasons'].append('speaker playback not RUNNING')
        expected=['pipewire'] if rec.get('route_kind')=='pipewire' else ['hdmi-speaker']
        if f['owners']!=expected:out['reasons'].append('PCMs not owned by '+expected[0]+': '+','.join(map(str,f['owners'])))
        if abs(f['capture_rate']/RATE-1)>RATE_TOLERANCE:out['reasons'].append('capture rate %.0f Hz is not 48 kHz'%f['capture_rate'])
        if f['xruns']:out['reasons'].append('%d capture xruns while sampling'%f['xruns'])
        if f['play_rate'] is None or abs(f['play_rate']/RATE-1)>RATE_TOLERANCE:out['reasons'].append('speaker playback not advancing at 48 kHz')
    if rec.get('route_kind')=='pipewire':
        route=rec.get('pipewire_route',{})
        if (rec.get('pipewire_check',{}).get('rc')!=0 or route.get('verified') is not True or
                route.get('version')!=1 or route.get('boot_id')!=rec.get('boot_id')):
            out['reasons'].append('PipeWire route/ownership verification failed')
    if require_video:out['reasons'].extend(evaluate_video(rec))
    out['passed']=not out['reasons'];return out
def compare(cold,warm,require_video=False):
    """The warm session must be a new boot whose audio path behaves like the cold one."""
    a,b=evaluate(cold,require_video),evaluate(warm,require_video);out={'cold':a,'warm':b,'reasons':[]}
    if cold.get('label')!='cold' or warm.get('label')!='warm':out['reasons'].append('labels must be cold then warm')
    if not cold.get('boot_id') or cold.get('boot_id')==warm.get('boot_id'):out['reasons'].append('warm record is not a new boot')
    if not a['passed']:out['reasons'].append('cold session did not pass')
    if not b['passed']:out['reasons'].append('warm session did not pass')
    out['passed']=not out['reasons'];return out
def collect(label,timeout=360):
    """One SSH call; a deadline is reported, never retried."""
    stage=subprocess.run(SSH+['cat > /run/h713-warm-shared-check.py'],input=REMOTE,text=True,capture_output=True,timeout=20)
    if stage.returncode:raise RuntimeError('could not stage remote checker: '+stage.stderr)
    # check-startup.sh travels on stdin, exactly as the repository holds it.
    r=subprocess.run(SSH+['python3 /run/h713-warm-shared-check.py '+label],input=(ROOT/'tools/hdmi/check-startup.sh').read_text(),text=True,capture_output=True,timeout=timeout)
    if r.returncode:raise RuntimeError('remote checker failed: '+r.stderr[-500:])
    return json.loads(r.stdout)
def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    sub=p.add_subparsers(dest='action',required=True)
    c=sub.add_parser('collect');c.add_argument('label',choices=('cold','warm'));c.add_argument('--output',required=True,type=pathlib.Path)
    m=sub.add_parser('compare');m.add_argument('cold',type=pathlib.Path);m.add_argument('warm',type=pathlib.Path)
    a=p.parse_args()
    if a.action=='collect':
        rec=collect(a.label)
        with a.output.open('x') as f:f.write(json.dumps(rec,indent=2)+'\n')
        res=evaluate(rec);print(json.dumps(res,indent=2));raise SystemExit(0 if res['passed'] else 1)
    res=compare(json.loads(a.cold.read_text()),json.loads(a.warm.read_text()));print(json.dumps(res,indent=2));raise SystemExit(0 if res['passed'] else 1)
if __name__=='__main__':main()
