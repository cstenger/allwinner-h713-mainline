#!/usr/bin/env python3
"""Repeated bounded HPD loss/return while one ALSA capture stays open.

Software HPD windows exercise automatic recovery; these are not physical cable
cycles. Each return has a unique marker and alternating channel tones. Requires
prepared managed audio; no DSP reinitialization/module lifecycle operations.
"""
import argparse
import importlib.util
import json
import shlex
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('transition',HERE/'run-alsa-rate-transition-test.py')
transition=importlib.util.module_from_spec(spec);spec.loader.exec_module(transition)
capture=transition.capture
spec=importlib.util.spec_from_file_location('marker_analysis',HERE/'audio-endurance-analysis.py')
marker_analysis=importlib.util.module_from_spec(spec);spec.loader.exec_module(marker_analysis)
RATE=48000


def analyze_raw(path,seconds,phases,window_count):
    if path.stat().st_size!=seconds*RATE*4:raise RuntimeError('unexpected raw frame count')
    checks=[]
    with path.open('rb') as stream:
        for phase in phases:
            start=phase['sample_frame']
            stream.seek(start*4)
            data=np.frombuffer(stream.read((3*RATE+16384)*4),dtype='<i2').reshape(-1,2)
            offset,score=marker_analysis.locate(data[:,0],marker_analysis.marker(phase['index']))
            frame=round(start+offset)
            stream.seek((frame+RATE)*4)
            samples=np.frombuffer(stream.read(16384*4),dtype='<i2').reshape(-1,2)
            if phase['swapped']:samples=samples[:,::-1].copy()
            tone=capture.rate_test.analysis.analyze(samples.tobytes())
            checks.append({'cycle':phase['index']+1,'marker_correlation':score,'marker_frame':frame,
                           'tone':tone,'pass':score>=.65 and tone['tone_pass'] and tone['capture_rate_hz']==RATE})
        stream.seek((seconds-1)*RATE*4)
        silent=not any(stream.read(RATE*4))
    return {'pass':len(checks)==window_count and all(c['pass'] for c in checks) and silent,
            'windows':checks,'final_second_all_zero':silent,'frames':seconds*RATE}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--recorder',default='arecord')
    parser.add_argument('--cycles',type=int,choices=range(2,21),default=10)
    args=parser.parse_args()
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    window_count=args.cycles+1
    seconds=window_count*20+20
    capture.remote('set -e; test "$(cat /sys/module/h713_hdmi_audio/parameters/graph_ready)" = Y; '
                   'test "$(cat /sys/module/h713_hdmi_audio/parameters/dsp_failed)" = N; '
                   'test "$(cat /proc/asound/H713HDMI/pcm0c/sub0/status)" = closed; '
                   'test ! -d /sys/module/h713_scp_probe; test ! -d /sys/module/h713_ddc_pins',out/'preflight.txt')
    helper=reader=player=None;logs=[]
    result={'pass':False,'requested_cycles':args.cycles,'phases':[],'seconds':seconds,'kind':'software HPD recovery'}
    def status(name):return transition.parse_status(capture.remote('cat /proc/asound/H713HDMI/pcm0c/sub0/status',out/name))
    try:
        before=capture.read_counters(out/'counters-before.txt')
        owner=None;previous_pointer=None
        for index in range(window_count):
            if reader is not None and reader.poll() is not None:raise RuntimeError('capture ended before all HPD cycles')
            log=(out/f'signal-{index}.log').open('w');logs.append(log)
            helper=subprocess.Popen([sys.executable,str(HERE/'run-detection-trial.py'),'--seconds','12','--stock-io'],stdout=log,stderr=subprocess.STDOUT)
            deadline=time.monotonic()+10
            while True:
                if helper.poll() is not None:raise RuntimeError('signal helper ended before ELD')
                try:card,device,eld=capture.rate_test.find_pcm();break
                except RuntimeError:
                    if time.monotonic()>=deadline:raise RuntimeError('audio ELD timeout')
                    time.sleep(.2)
            (out/f'eld-{index}.txt').write_text(eld.read_text())
            if reader is None:
                raw=(out/'capture.raw').open('wb');logs.append(raw)
                log=(out/'capture.log').open('w');logs.append(log)
                reader=subprocess.Popen(capture.SSH+[
                    f'timeout -k 3s -s INT {seconds+10}s '+shlex.quote(args.recorder)+
                    f' -v -D hw:H713HDMI,0 -t raw -f S16_LE -r 48000 -c 2 --period-size=256 --buffer-size=16384 -d {seconds} -'],stdout=raw,stderr=log)
                time.sleep(.7);owner=status('capture-start.txt')['owner_pid']
            t=np.arange(6*RATE)/RATE
            swapped=bool(index%2);frequencies=(2000,1000) if swapped else (1000,2000)
            samples=np.column_stack([6500*np.sin(2*np.pi*f*t) for f in frequencies]).astype('<i2')
            samples[2*RATE:2*RATE+16384,0]=marker_analysis.marker(index)
            tone=out/f'tone-{index}.wav'
            with wave.open(str(tone),'wb') as wav:
                wav.setnchannels(2);wav.setsampwidth(2);wav.setframerate(RATE);wav.writeframes(samples.tobytes())
            log=(out/f'playback-{index}.log').open('w');logs.append(log)
            player=subprocess.Popen(['aplay','--disable-resample','-v','-D',f'hw:{card},{device}',str(tone)],stdout=log,stderr=subprocess.STDOUT)
            time.sleep(1)
            params=Path(f'/proc/asound/card{card}/pcm{device}p/sub0/hw_params').read_text()
            capture.rate_test.check_hw_params(params,RATE)
            (out/f'host-hw-params-{index}.txt').write_text(params)
            active=status(f'capture-active-{index}.txt')
            if active['owner_pid']!=owner:raise RuntimeError('capture owner changed on return')
            if previous_pointer is not None and active['hw_ptr']<=previous_pointer:raise RuntimeError('capture pointer did not advance')
            result['phases'].append({'index':index,'swapped':swapped,'sample_frame':active['hw_ptr'],'owner_pid':owner})
            if player.wait(timeout=9)!=0:raise RuntimeError('source playback failed')
            if helper.wait(timeout=70)!=0:raise RuntimeError('signal helper or restoration failed')
            if Path('/sys/class/drm/card1-HDMI-A-1/status').read_text().strip()!='disconnected':raise RuntimeError('source did not observe HPD loss')
            capture.remote('set -e; test ! -d /sys/module/h713_scp_probe; test ! -d /sys/module/h713_ddc_pins; '
                           'test "$(cat /sys/module/h713_hdmi_audio/parameters/dsp_failed)" = N',out/f'helper-cleanup-{index}.txt')
            lost=status(f'capture-disconnected-{index}.txt')
            if lost['owner_pid']!=owner:raise RuntimeError('capture owner changed during HPD loss')
            previous_pointer=lost['hw_ptr']
            print(json.dumps({'completed_recoveries':index,'owner_pid':owner}),flush=True)
            if index+1<window_count:time.sleep(3)
        result['capture_returncode']=reader.wait(timeout=seconds)
        if result['capture_returncode']!=0:raise RuntimeError('capture failed')
        raw.flush()
        result['analysis']=analyze_raw(out/'capture.raw',seconds,result['phases'],window_count)
        after=capture.read_counters(out/'counters-after.txt')
        result['counter_delta']={k:after[k]-v for k,v in before.items()}
        result['same_owner_pid']=owner
        capture.remote('cat /proc/asound/H713HDMI/pcm0c/sub0/status',out/'after.txt')
        result['pass']=(result['analysis']['pass'] and result['counter_delta']['period_xruns']==0
                        and all(result['counter_delta'][k]>0 for k in ('period_active','period_bytes','period_notifications'))
                        and (out/'after.txt').read_text().strip()=='closed'
                        and 'overrun' not in (out/'capture.log').read_text().lower())
    except Exception as error:result['error']=str(error)
    finally:
        for process in (player,reader):
            if process is not None and process.poll() is None:
                process.terminate()
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
        if helper is not None and helper.poll() is None:
            try:helper.wait(timeout=75)
            except subprocess.TimeoutExpired:result.update({'pass':False,'cleanup_error':'signal helper still active; inspect holds'})
        for log in logs:log.close()
        try:
            deadline=time.monotonic()+seconds+15
            while True:
                state=capture.remote('cat /proc/asound/H713HDMI/pcm0c/sub0/status',out/'final-status.txt')
                if state.strip()=='closed':break
                if time.monotonic()>=deadline:raise RuntimeError('remote capture did not close')
                time.sleep(1)
        except Exception as error:result.update({'pass':False,'cleanup_error':str(error)})
        for path in out.glob('signal-*.log'):
            lines=path.read_text().splitlines()
            if lines and lines[0].startswith('Logs: '):
                src=Path(lines[0].removeprefix('Logs: '))
                if src.exists():shutil.copytree(src,out/(path.stem+'-evidence'))
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'pass':result['pass'],'error':result.get('error')}),flush=True)
    return 0 if result['pass'] else 1


if __name__=='__main__':sys.exit(main())
