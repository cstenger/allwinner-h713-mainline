#!/usr/bin/env python3
"""Classify Phase B (clock round trip, then demod reset) separately from loss of access."""
import argparse,hashlib,json
from pathlib import Path

PAIRS=4
STEPS=39
CHECKPOINT=(6,15,27,39)
BOUNDARY=(None,'phase_a_prefix','clock_round_trip','clock_and_demod_reset_round_trip')
DMA_WORDS=(5,6,11)
# h713-hdmi-tvfe.c functional_words order and stock values.
TV_NAMES=('adc','tvfe-1296','i2h','cip-tsx','cip-mcx','cip-tsp','tsa-tsp','cip27','cip-mts0','audio-cpu','audio-umac','audio-ihb','tsa432','mpg0','mpg1')
TV_STOCK=(0x80000017,0x80000000,0x81000005,0x80000002,0x80000005,0x80000003,0x80000003,0x8000000b,0x80000117,0x80000002,0x80000002,0x81000002,0x80000002,0x8000020b,0x8000020b)
ROUTED=0x00011111

def pair(p):
    return [v&0xffff for v in p['raw']] if p.get('outcome')==[1,1] and p.get('phase')==[5,5] and p.get('sent')==[1,1] else None

def canonical(record):
    return hashlib.sha256((json.dumps(record,sort_keys=True)+'\n').encode()).hexdigest()

def dma_consistent(ctx):
    d=ctx.get('dma');c=ctx.get('census')
    if not isinstance(d,int) or not c or d&0xf or d>>32:return False
    return c[5]==(d>>4)&0xffffff and c[6]==((d+0x10000-1)>>4)&0xffffff and c[11]&0xf0==(d>>28)<<4

def gates_turned_off(tv):
    """Words whose saved value clears a gate that stock sets: the effective clock-off edge."""
    return [n for n,s,v in zip(TV_NAMES,TV_STOCK,tv.get('saved',[])) if s&0x80000000 and not v&0x80000000]

def context_ok(s):
    c=s.get('ctx',{});t=s.get('tv',{})
    if not c.get('census') or c.get('census_stage')!=3 or c.get('census_flags')!=31 or c.get('at_saved')!=[0,0] or not dma_consistent(c):return False
    if c.get('gate')!=1 or c.get('tvtop_last')!=ROUTED or any(x[2] for x in c.get('audio_clocks',[[0,0,1]])):return False
    if not t.get('census') or list(t['census'][:15])!=list(TV_STOCK) or t['census'][15]!=(t.get('bus_saved',-1)|0x10001) or t.get('state')!=0:return False
    return len(t.get('saved',[]))==15 and c.get('spdi_writes')==3 and c.get('bridge_writes')==9

def counters(step):
    """Expected (tv offs, ons, resets, tv writes, ihb writes, AudioTop writes) after a terminal step."""
    rounds=0 if step<27 else 1 if step<39 else 2
    writes=(0,32,65)[rounds]
    return {'offs':rounds,'ons':rounds,'resets':1 if rounds==2 else 0,'writes':writes,'ihb':2*rounds,'at':1+2*rounds}

def arm2_ok(s):
    t,c=s['tv'],s['ctx'];want=counters(s['step'])
    if (t['offs'],t['ons'],t['resets'],t['writes'])!=(want['offs'],want['ons'],want['resets'],want['writes']):return False
    if c['ihb'][2]!=want['ihb'] or c['at_writes']!=want['at']:return False
    if want['offs'] and (t['off_clocks'] is None or t['off_clocks'][:15]!=t['saved'] or t['off_clocks'][15]!=t['bus_saved']|0x10000):return False
    if want['resets'] and (t['off_reset'] is None or t['off_reset'][:15]!=t['saved'] or t['off_reset'][15]!=t['bus_saved'] or t['reset_status_after']!=1):return False
    return True

def sham_ok(s):
    t,c=s['tv'],s['ctx']
    return (t['offs'],t['ons'],t['resets'],t['writes'])==(0,0,0,32) and t['off_clocks'] is None and t['off_reset'] is None and c['ihb'][2]==4 and c['at_writes']==5 and c['gate_closes']==c['gate_opens']==2 and not any(p[2] for p in t['parents'])

def analyze(r):
    s=r.get('state',{});p=r.get('proof',{});b=r.get('baseline',{})
    out={'classification':'inconclusive','versions':[pair(x) for x in s.get('pairs',[])],'reset_erasure':'demod reset only; no CPU/MIPS reset measured'}
    if s.get('schema')!='h713-teardown-b-v1' or s.get('steps')!=STEPS or not r.get('preflight_valid') or not p.get('verified') or p.get('boot_id')!=r.get('boot_id') or p.get('arm')!=s.get('arm') or s.get('failed') or s.get('claimed') or not s.get('terminal'):
        return out
    j=b.get('dsp_journal',[])
    if not any('DSP versions 0000/0000' in l for l in j) or not any('pinned 724-pair DSP patch verified versions 1/1' in l for l in j) or b.get('boot_id')!=r['boot_id'] or not b.get('tv_domains_both_on') or b.get('reads',{}).get('mips_status')!='00000001':return out
    v=out['versions']
    if len(v)!=PAIRS or not context_ok(s):return out
    out['gates_turned_off']=gates_turned_off(s['tv']);out['parents']=s['tv']['parents']
    if any(0x80ff0000 in x.get('raw',[]) for x in s['pairs']):
        out['classification']='ambiguous_command_echo';return out
    if s.get('timeout'):
        out['classification']='access_timeout';return out
    if v[0]!=[1,1]:
        out['classification']='patched_positive_control_not_observed';return out
    if s['step'] not in CHECKPOINT:return out
    last=CHECKPOINT.index(s['step'])
    if v[last] is None or any(x!=[1,1] for x in v[:last]) or any(x is not None for x in v[last+1:]):return out
    if s.get('graph_remaining')!=0 or s.get('ctl')!=0x700 or s.get('cfg')!=0 or s.get('requests')!=2*(last+1):return out
    if last>=1 and v[1]!=[1,1]:
        out['classification']='version_change_after_phase_a_prefix';return out
    if s['arm']==1:
        out['classification']='sham_positive_control_passed' if last==PAIRS-1 and sham_ok(s) else 'sham_changed_or_incomplete'
    elif s['arm']==2:
        if not arm2_ok(s):return out
        if last>=2 and not out['gates_turned_off']:
            out['classification']='inconclusive_null_clock_edge';return out
        if v[last]!=[1,1]:out['classification']='version_change_after_'+BOUNDARY[last]
        elif last==PAIRS-1:out['classification']='tested_phase_b_boundaries_preserved_patch'
    return out

def compare(sham,arm):
    a,b=analyze(sham),analyze(arm)
    out={'classification':'unmatched_or_unqualified','sham':a,'arm':b}
    ss,bs=sham.get('state',{}),arm.get('state',{})
    if ss.get('arm')!=1 or bs.get('arm')!=2 or a['classification']!='sham_positive_control_passed' or sham.get('boot_id')==arm.get('boot_id'):return out
    if ss.get('plan')!=bs.get('plan') or len(ss.get('graph_saved',[]))!=22 or ss['graph_saved']!=bs.get('graph_saved'):return out
    if sham.get('baseline',{}).get('reads')!=arm.get('baseline',{}).get('reads'):return out
    sc,bc=ss.get('ctx',{}),bs.get('ctx',{})
    for key in ('saved','saved_route','at_saved','census_stage','census_flags','audio_clocks'):
        if sc.get(key)!=bc.get(key):return out
    if sc.get('ihb',[None])[:2]!=bc.get('ihb',[0])[:2]:return out
    if not dma_consistent(sc) or not dma_consistent(bc):return out
    if [x for i,x in enumerate(sc['census']) if i not in DMA_WORDS]!=[x for i,x in enumerate(bc['census']) if i not in DMA_WORDS]:return out
    if sc['census'][11]&~0xf0!=bc['census'][11]&~0xf0:return out
    st,bt=ss.get('tv',{}),bs.get('tv',{})
    for key in ('saved','bus_saved','census'):
        if st.get(key)!=bt.get(key):return out
    if [x[0] for x in st.get('parents',[])]!=[x[0] for x in bt.get('parents',[])]:return out
    for key in ('manifest_sha256','cold_script_sha256','module_sha256'):
        if not sham.get('proof',{}).get(key) or sham['proof'][key]!=arm.get('proof',{}).get(key):return out
    if arm['proof'].get('sham_record_sha256')!=canonical(sham):return out
    if b['classification'].startswith('inconclusive'):return out
    out['classification']='matched_'+b['classification'];return out

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('records',nargs='+',type=Path);a=p.parse_args();r=[json.loads(f.read_text()) for f in a.records]
    if len(r) not in (1,2):p.error('one record or sham followed by Phase B arm')
    print(json.dumps(analyze(r[0]) if len(r)==1 else compare(*r),indent=2))
if __name__=='__main__':main()
