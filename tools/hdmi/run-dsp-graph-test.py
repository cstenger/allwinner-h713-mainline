#!/usr/bin/env python3
"""Repeat saved/read-back DSP graph cycles on an already prepared, idle board.

No module loading, patching, timeout retries or failure-latch resets.
"""
import argparse
import json
import shlex
import subprocess
from pathlib import Path

SSH = ['ssh','-F','/dev/null','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
       '-o','ConnectTimeout=5','-o','ServerAliveInterval=2','-o','ServerAliveCountMax=1','root@192.168.4.1']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--cycles', type=int, choices=range(1,101), default=20, metavar='1..100')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    script = '''import json, subprocess
from pathlib import Path
base=Path('/sys/module/h713_hdmi_dsp_probe/parameters')
assert (base/'stock_completion').read_text().strip() == 'Y'
assert (base/'stock_graph').read_text().strip() == 'N'
assert (base/'graph_chain').read_text().strip() == 'Y'
assert (base/'stock_patch').read_text().strip() == 'Y'
assert Path('/sys/module/h713_hdmi_audio/parameters/graph_ready').read_text().strip() == 'N'
assert Path('/proc/asound/H713HDMI/pcm0c/sub0/status').read_text().strip() == 'closed'
completed=0
initial=int((base/'stock_read_count').read_text())
try:
    for index in range(CYCLES):
        (base/'stock_graph').write_text('1')
        (base/'stock_graph').write_text('0')
        completed+=1
        print(json.dumps(dict(cycle=completed, stock_read_count=int((base/'stock_read_count').read_text()))), flush=True)
    final=int((base/'stock_read_count').read_text())
    assert final-initial == CYCLES*68, (initial,final)
finally:
    # Read-only evidence even after a timeout. Never restore/retry in finally.
    print(json.dumps(dict(completed_cycles=completed)), flush=True)
    subprocess.run(['dmesg'], check=False)
'''.replace('CYCLES', str(args.cycles))
    bound = args.cycles*4+10
    command = f'timeout {bound}s python3 -u -c '+shlex.quote(script)
    result = {'pass':False, 'requested_cycles':args.cycles}
    try:
        with (args.output/'cycles.log').open('w') as log:
            process = subprocess.run(SSH+[command],stdout=log,stderr=subprocess.STDOUT,timeout=bound+10)
        result.update(returncode=process.returncode, **{'pass':process.returncode == 0})
    except subprocess.TimeoutExpired:
        result['error']='host timeout; inspect board before any further DSP command'
    (args.output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
    return 0 if result['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
