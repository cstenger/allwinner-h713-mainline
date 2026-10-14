#!/usr/bin/env python3
"""Bounded48k HDMI endurance capture streamed to the host, with marker drift.

Requires prepared managed audio and the canonical EDID SCP helper. Does not
load/unload audio or send DSP commands. Raw PCM is stored only on the host.
"""
import argparse
import importlib.util
import json
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('capture',HERE/'run-alsa-capture-test.py')
capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)
spec=importlib.util.spec_from_file_location('endurance',HERE/'audio-endurance-analysis.py')
analysis=importlib.util.module_from_spec(spec);spec.loader.exec_module(analysis)

CLOCK_SCRIPT="""import json,time
from pathlib import Path
before=time.clock_gettime(time.CLOCK_MONOTONIC_RAW)
text=Path('/proc/asound/H713HDMI/pcm0c/sub0/status').read_text()
after=time.clock_gettime(time.CLOCK_MONOTONIC_RAW)
fields={k.strip():v.strip() for k,v in (line.split(':',1) for line in text.splitlines() if ':' in line)}
assert fields.get('state')=='RUNNING',text
print(json.dumps({'before_raw':before,'after_raw':after,'hw_ptr':int(fields['hw_ptr']),'owner_pid':int(fields['owner_pid'])}))
"""


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--recorder',default='arecord')
    parser.add_argument('--seconds',type=int,default=3600,help='90–3600 seconds; default one hour')
    args=parser.parse_args()
    if not 90<=args.seconds<=3600:parser.error('--seconds must be90–3600')
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    needed=args.seconds*48000*8+256*1024*1024
    if shutil.disk_usage(out).free<needed:parser.error('insufficient host disk for source and capture')
    capture.remote('set -e; test "$(cat /sys/module/h713_hdmi_audio/parameters/graph_ready)" = Y; '
                   'test "$(cat /sys/module/h713_hdmi_audio/parameters/dsp_failed)" = N; '
                   'test "$(cat /proc/asound/H713HDMI/pcm0c/sub0/status)" = closed; '
                   'test ! -d /sys/module/h713_scp_probe; test ! -d /sys/module/h713_ddc_pins',out/'preflight.txt')
    analysis.make_source(out/'source.wav',args.seconds)
    player=reader=helper=None;logs=[]
    result={'pass':False,'seconds':args.seconds,'input_rate_hz':48000,'output_rate_hz':48000}
    samples=[]
    try:
        before=capture.read_counters(out/'counters-before.txt')
        hold=args.seconds+30
        command=[sys.executable,str(HERE/'run-detection-trial.py'),'--seconds',str(hold),'--stock-io']
        if hold>150:command.append('--audio-endurance')
        log=(out/'signal.log').open('w');logs.append(log)
        helper=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
        deadline=time.monotonic()+10
        while True:
            if helper.poll() is not None:raise RuntimeError('signal helper ended before ELD')
            try:card,device,eld=capture.rate_test.find_pcm();break
            except RuntimeError:
                if time.monotonic()>=deadline:raise RuntimeError('HDMI audio ELD timeout')
                time.sleep(.2)
        (out/'eld.txt').write_text(eld.read_text())
        raw=(out/'capture.raw').open('wb');logs.append(raw)
        log=(out/'capture.log').open('w');logs.append(log)
        reader=subprocess.Popen(capture.SSH+[
            f'timeout -k 3s -s INT {args.seconds+15}s '+shlex.quote(args.recorder)+
            f' -v -D hw:H713HDMI,0 -t raw -f S16_LE -r 48000 -c 2 --period-size=256 --buffer-size=16384 -d {args.seconds} -'],stdout=raw,stderr=log)
        start=time.monotonic();time.sleep(.7)
        log=(out/'playback.log').open('w');logs.append(log)
        player=subprocess.Popen(['aplay','--disable-resample','-v','-D',f'hw:{card},{device}',str(out/'source.wav')],stdout=log,stderr=subprocess.STDOUT)
        time.sleep(.3)
        params=Path(f'/proc/asound/card{card}/pcm{device}p/sub0/hw_params').read_text()
        capture.rate_test.check_hw_params(params,48000)
        (out/'host-hw-params.txt').write_text(params)
        next_sample=0.;owner=None
        with (out/'clock-samples.jsonl').open('w') as clock_log:
            while reader.poll() is None:
                elapsed=time.monotonic()-start
                if elapsed>args.seconds+20:raise RuntimeError('reader exceeded independent deadline')
                if helper.poll() is not None:raise RuntimeError('signal helper ended during capture')
                if player.poll() is not None and (player.returncode!=0 or elapsed<args.seconds-8):
                    raise RuntimeError('source playback failed or ended early')
                if elapsed>=next_sample and elapsed<args.seconds-5:
                    sample=json.loads(capture.remote('python3 -c '+shlex.quote(CLOCK_SCRIPT),out/'clock-latest.txt'))
                    if owner is None:owner=sample['owner_pid']
                    if sample['owner_pid']!=owner:raise RuntimeError('capture owner changed')
                    if samples and sample['hw_ptr']<=samples[-1]['hw_ptr']:raise RuntimeError('capture pointer stalled or reset')
                    samples.append(sample);clock_log.write(json.dumps(sample)+'\n');clock_log.flush()
                    next_sample=elapsed+30
                    progress={'elapsed_seconds':round(elapsed,1),'host_raw_bytes':(out/'capture.raw').stat().st_size,'owner_pid':owner}
                    (out/'progress.json').write_text(json.dumps(progress)+'\n')
                    print(json.dumps(progress),flush=True)
                time.sleep(.5)
        result['capture_returncode']=reader.wait(timeout=3)
        result['playback_returncode']=player.wait(timeout=10)
        result['signal_returncode']=helper.wait(timeout=hold+70)
        if any(result[k]!=0 for k in ('capture_returncode','playback_returncode','signal_returncode')):
            raise RuntimeError('capture, playback or signal helper failed')
        raw.flush()
        result['signal_analysis']=analysis.analyze_raw(out/'capture.raw',args.seconds)
        result['board_clock_analysis']=analysis.analyze_clock(samples)
        after=capture.read_counters(out/'counters-after.txt')
        result['counter_delta']={k:after[k]-v for k,v in before.items()}
        result['same_owner_pid']=owner
        capture.remote('set -e; test ! -d /sys/module/h713_scp_probe; test ! -d /sys/module/h713_ddc_pins; '
                       'test "$(cat /sys/module/h713_hdmi_audio/parameters/dsp_failed)" = N; '
                       'cat /proc/asound/H713HDMI/pcm0c/sub0/status',out/'after.txt')
        result['pass']=(result['signal_analysis']['pass'] and result['counter_delta']['period_xruns']==0
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
            try:helper.wait(timeout=args.seconds+100)
            except subprocess.TimeoutExpired:result.update({'pass':False,'cleanup_error':'signal helper still active; inspect retained holds'})
        for log in logs:log.close()
        try:
            deadline=time.monotonic()+args.seconds+20
            while True:
                state=capture.remote('cat /proc/asound/H713HDMI/pcm0c/sub0/status',out/'final-status.txt')
                if state.strip()=='closed':break
                if time.monotonic()>=deadline:raise RuntimeError('remote reader did not close')
                time.sleep(1)
        except Exception as error:result.update({'pass':False,'cleanup_error':str(error)})
        lines=(out/'signal.log').read_text().splitlines() if (out/'signal.log').exists() else []
        if lines and lines[0].startswith('Logs: '):
            src=Path(lines[0].removeprefix('Logs: '))
            if src.exists():shutil.copytree(src,out/'signal-evidence')
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'pass':result['pass'],'error':result.get('error')}),flush=True)
    return 0 if result['pass'] else 1


if __name__=='__main__':sys.exit(main())
