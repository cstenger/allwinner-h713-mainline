import json,pathlib,subprocess,sys
p=pathlib.Path(__file__).resolve().parent
args=sys.argv[1:]
assert args and args[0] in ('snapshot','step')
name='snapshot' if args[0]=='snapshot' else 'step-'+args[args.index('--number')+1].zfill(2)
b='/root/hdmi-dsp-owner-boundary-2026-10-22/boundary'
cmd=['ssh','-F','/dev/null','-o','BatchMode=yes','-o','ConnectTimeout=5','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=1','root@192.168.4.1','python3 '+b+'/dsp-owner-boundary.py --bundle '+b+' '+' '.join(args)]
try:r=subprocess.run(cmd,capture_output=True,text=True,timeout=20)
except subprocess.TimeoutExpired as e:
    decode=lambda v:v.decode(errors='replace') if isinstance(v,bytes) else (v or '')
    with (p/(name+'-uncertain.log')).open('x') as f:f.write(decode(e.stdout)+decode(e.stderr)+'\nHOST DEADLINE: uncertain, no retry\n')
    raise SystemExit('HOST DEADLINE: uncertain, no retry')
if r.returncode:
    with (p/(name+'-error.log')).open('x') as f:f.write(r.stdout+r.stderr)
    print(r.stdout+r.stderr);raise SystemExit(r.returncode)
if args[0]=='step':
    event,end=json.JSONDecoder().raw_decode(r.stdout);assert event['event']=='before-step';record=json.loads(r.stdout[end:])
else:
    record=json.loads(r.stdout);name='snapshot-'+str(record['state']['step']).zfill(2)
with (p/(name+'.json')).open('x') as f:f.write(json.dumps(record,indent=2)+'\n')
s=record['state'];print(json.dumps({'state':{k:s[k] for k in ('arm','step','failed','timeout','claimed','terminal','ctl','cfg','graph_remaining')},'pairs_seen':[{'pair':i,**x} for i,x in enumerate(s['pairs']) if any(x['phase'])],'preflight_valid':record['preflight_valid'],'analysis':record['analysis']}))
if args[0]=='snapshot':print('\n'.join(l for l in record['journal'].splitlines() if 'H713 OWNER' in l)[-1100:])
