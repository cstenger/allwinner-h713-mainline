# Host sequencer for one arm: one call per action, stop on first error/terminal.
import json,pathlib,subprocess,sys,importlib.util
R=pathlib.Path(__file__).resolve().parent;ROOT=R.parents[2]
s=importlib.util.spec_from_file_location('h',ROOT/'tools/hdmi/dsp-teardown-a.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
host=[sys.executable,str(ROOT/'tools/hdmi/dsp-teardown-a-host.py'),'--run',str(R)]
def call(*a):
    r=subprocess.run(host+list(a),capture_output=True,text=True)
    print('>>',' '.join(a),'rc',r.returncode,'\n',r.stdout[-700:],r.stderr[-400:],flush=True)
    if r.returncode:raise SystemExit('STOP: '+' '.join(a)+' failed; no retry')
start=int(sys.argv[1])
if start==1:call('snapshot')
for n in range(start,38):
    prev=n-1;ack=h.STAGES.get(prev)
    call('step',str(n),*( [ack] if ack else []))
    st=json.loads((R/('step-%02d.json'%n)).read_text())['state']
    if n in h.STAGES or st['terminal']:call('snapshot')
    if st['terminal']:print('TERMINAL at step',n);break
