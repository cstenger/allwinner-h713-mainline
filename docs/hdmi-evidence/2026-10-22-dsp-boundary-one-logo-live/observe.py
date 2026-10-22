import json,pathlib,subprocess,sys
p=pathlib.Path(__file__).resolve().parent
args=sys.argv[1:]
assert args and args[0] in ('snapshot','step')
name='snapshot' if args[0]=='snapshot' else 'step-'+args[args.index('--number')+1].zfill(2)
base='/root/hdmi-dsp-boundary-2026-10-22'
cmd=['ssh','-F','/dev/null','-o','BatchMode=yes','-o','ConnectTimeout=5','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=1','root@192.168.4.1','python3 '+base+'/dsp-boundary.py --bundle '+base+' --baseline '+base+'/cold-census.json '+' '.join(args)]
try:
    r=subprocess.run(cmd,capture_output=True,text=True,timeout=20)
except subprocess.TimeoutExpired as e:
    decode=lambda v:v.decode('utf-8','replace') if isinstance(v,bytes) else (v or '')
    with (p/(name+'.log')).open('x') as f:
        f.write(decode(e.stdout)+decode(e.stderr)+'\nHOST DEADLINE: operation uncertain; no retry\n')
    print('HOST DEADLINE: operation uncertain; no retry')
    raise SystemExit(124)
if args[0]=='snapshot' and r.returncode==0:
    record=json.loads(r.stdout);name='snapshot-'+str(record['state']['step']).zfill(2)
with (p/(name+'.log')).open('x') as f:f.write(r.stdout+r.stderr)
if r.returncode:
    print(r.stdout+r.stderr);raise SystemExit(r.returncode)
start=r.stdout.find('{',r.stdout.find('\n')+1) if args[0]=='step' else 0
record=json.loads(r.stdout[start:])
state=record['state']
keys=('step','hold','violated','failed','timeout','claimed','last','demod_before','display_reset_before','tvcap_reset_before','route_writes','pairs')
print(json.dumps({'state':{k:state[k] for k in keys},'preflight_valid':record['preflight_valid'],'analysis':record['analysis']}))
if args[0]=='snapshot':
    print('\n'.join(l for l in record['journal'].splitlines() if 'RETENTION' in l or 'TVFE command' in l)[-1400:])
