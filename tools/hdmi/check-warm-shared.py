#!/usr/bin/env python3
"""Read-only HDMI session health for the warm shared-startup test.

One SSH call runs tools/hdmi/check-startup.sh unchanged on the board (after
the services settle), records 5 s of the HDMI source through the user's
PipeWire (the production consumer path) and reports level, PCM state and
DSP version lines. The host side judges the record and compares the cold
and warm sessions of one test. Nothing is written on the board except a
scratch directory in /run and the 5 s recording in /tmp.
"""
import argparse,array,io,json,math,pathlib,subprocess,sys,wave
ROOT=pathlib.Path(__file__).resolve().parents[2]
SSH=['ssh','-F','/dev/null','-o','BatchMode=yes','-o','ConnectTimeout=5','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=1','root@192.168.4.1']
RATE=48000
MIN_RMS=0.01          # "signal present"; the reference tone clip is far above this
MAX_DB_CHANGE=3.0     # warm level must match cold within this, same source
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
card=os.readlink('/proc/asound/H713HDMI') if P('/proc/asound/H713HDMI').exists() else None
out['card']=card
if card and r.returncode==0:
    node='alsa_input._sys_devices_h713-hdmi-audio-dma_sound_'+card+'.stereo-fallback'
    wav='/tmp/h713-warm-shared-'+label+'.wav'
    if P(wav).exists():P(wav).unlink()
    rec=subprocess.Popen(['systemd-run','--wait','--collect','--uid=media','-E','XDG_RUNTIME_DIR=/run/user/1000','--quiet',
        'timeout','-s','INT','5','pw-record','--target',node,'--rate','48000','--channels','2','--format','s16',wav],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    time.sleep(2.5)
    out['pcm_during']=P('/proc/asound/H713HDMI/pcm0c/sub0/status').read_text()
    so,se=rec.communicate(timeout=30);out['record']={'rc':rec.returncode,'output':so+se,'node':node}
    out['wav_hex']=P(wav).read_bytes().hex() if P(wav).exists() else None
j=subprocess.run(['journalctl','-k','-b','--no-pager','-o','cat'],capture_output=True,text=True).stdout
out['dsp_lines']=[l for l in j.splitlines() if 'DSP versions' in l or 'patch verified' in l]
print(json.dumps(out))
'''
def wav_level(data,skip_s=0.5):
    """RMS and peak (full scale = 1) of an s16 stereo WAV, skipping the start gap."""
    with wave.open(io.BytesIO(data)) as w:
        if w.getsampwidth()!=2 or w.getnchannels()!=2 or w.getframerate()!=RATE:raise ValueError('unexpected WAV format')
        frames=w.getnframes();w.readframes(int(skip_s*RATE));samples=array.array('h',w.readframes(frames))
    if sys.byteorder!='little':samples.byteswap()
    if not samples:return {'frames':frames,'rms':0.0,'peak':0.0}
    rms=math.sqrt(sum(s*s for s in samples)/len(samples))/32768
    return {'frames':frames,'rms':rms,'peak':max(abs(s) for s in samples)/32768}
def evaluate(rec):
    """Pass only with the unchanged startup check, a running PCM and a present signal."""
    out={'label':rec.get('label'),'boot_id':rec.get('boot_id'),'reasons':[]}
    cs=rec.get('check_startup',{})
    if cs.get('rc')!=0 or 'PASS' not in cs.get('output','').splitlines()[-1:]:out['reasons'].append('check-startup.sh did not pass')
    dsp=rec.get('dsp_lines',[])
    if not any('DSP versions 0000/0000' in l for l in dsp):out['reasons'].append('DSP did not start at 0/0')
    if not any('patch verified versions 1/1' in l for l in dsp):out['reasons'].append('DSP patch not verified 1/1')
    if 'state: RUNNING' not in rec.get('pcm_during',''):out['reasons'].append('capture PCM not RUNNING while recording')
    if not rec.get('wav_hex'):out['reasons'].append('no recording')
    else:
        level=wav_level(bytes.fromhex(rec['wav_hex']));out['level']=level
        if level['frames']<4*RATE:out['reasons'].append('recording shorter than 4 s')
        if level['rms']<MIN_RMS:out['reasons'].append('audio level below %.3f (silence)'%MIN_RMS)
    out['passed']=not out['reasons'];return out
def compare(cold,warm):
    """The warm session must be a new boot carrying the same source at the same level."""
    a,b=evaluate(cold),evaluate(warm);out={'cold':a,'warm':b,'reasons':[]}
    if cold.get('label')!='cold' or warm.get('label')!='warm':out['reasons'].append('labels must be cold then warm')
    if not cold.get('boot_id') or cold.get('boot_id')==warm.get('boot_id'):out['reasons'].append('warm record is not a new boot')
    if not a['passed']:out['reasons'].append('cold session did not pass')
    if not b['passed']:out['reasons'].append('warm session did not pass')
    if a.get('level') and b.get('level') and a['level']['rms']>0 and b['level']['rms']>0:
        out['level_change_db']=20*math.log10(b['level']['rms']/a['level']['rms'])
        if abs(out['level_change_db'])>MAX_DB_CHANGE:out['reasons'].append('warm level differs from cold by more than %.0f dB'%MAX_DB_CHANGE)
    out['passed']=not out['reasons'];return out
def collect(label,timeout=200):
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
