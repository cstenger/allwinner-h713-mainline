#!/usr/bin/env python3
"""Classify Phase A teardown version changes separately from loss of access."""
import argparse,hashlib,json
from pathlib import Path

PAIRS=6
STEPS=37
# Terminal checkpoint step for each pair, and what preceded that pair in arm 2.
CHECKPOINT=(6,12,18,24,30,37)
BOUNDARY=(None,'common_graph_restore','spdi_restore','bridge_restore','audiotop_config_restore','audiotop_control_cycle')
DMA_WORDS=(5,6,11)

def pair(p):
    return [v&0xffff for v in p['raw']] if p.get('outcome')==[1,1] and p.get('phase')==[5,5] and p.get('sent')==[1,1] else None

def canonical(record):
    return hashlib.sha256((json.dumps(record,sort_keys=True)+'\n').encode()).hexdigest()

def dma_consistent(ctx):
    d=ctx.get('dma');c=ctx.get('census')
    if not isinstance(d,int) or not c or d&0xf or d>>32:return False
    return c[5]==(d>>4)&0xffffff and c[6]==((d+0x10000-1)>>4)&0xffffff and c[11]&0xf0==(d>>28)<<4

def context_ok(s):
    c=s.get('ctx',{})
    return bool(c.get('census')) and c.get('census_stage')==3 and c.get('census_flags')==31 and c.get('at_saved')==[0,0] and dma_consistent(c) and len(c.get('saved',[]))==12

def arm2_writes_ok(s):
    c=s['ctx'];step=s['step'];sv=c['saved']
    want_spdi=step>=13;want_bridge=step>=19
    if c['spdi_applied']!=want_spdi or c['bridge_applied']!=want_bridge:return False
    if c['spdi_writes']!=(3 if want_spdi else 0) or c['bridge_writes']!=(9 if want_bridge else 0):return False
    if c['at_writes']!=(3 if step>=32 else 2 if step>=31 else 1 if step>=25 else 0):return False
    if want_spdi and (c['after_spdi'][:3]!=sv[:3] or c['after_spdi'][3:]!=c['census'][3:]):return False
    if want_bridge and (c['after_bridge'][:3]!=sv[:3] or c['after_bridge'][3:]!=sv[3:]):return False
    return True

def analyze(r):
    s=r.get('state',{});p=r.get('proof',{});b=r.get('baseline',{})
    out={'classification':'inconclusive','versions':[pair(x) for x in s.get('pairs',[])],'reset_erasure':'not measured'}
    if s.get('schema')!='h713-teardown-a-v1' or s.get('steps')!=STEPS or not r.get('preflight_valid') or not p.get('verified') or p.get('boot_id')!=r.get('boot_id') or p.get('arm')!=s.get('arm') or s.get('failed') or s.get('claimed') or not s.get('terminal'):
        return out
    j=b.get('dsp_journal',[])
    if not any('DSP versions 0000/0000' in l for l in j) or not any('pinned 724-pair DSP patch verified versions 1/1' in l for l in j) or b.get('boot_id')!=r['boot_id'] or not b.get('tv_domains_both_on') or b.get('reads',{}).get('mips_status')!='00000001':return out
    v=out['versions']
    if len(v)!=PAIRS or not context_ok(s):return out
    if any(0x80ff0000 in x.get('raw',[]) for x in s['pairs']):
        out['classification']='ambiguous_command_echo';return out
    if s.get('timeout'):
        out['classification']='access_timeout';return out
    if v[0]!=[1,1]:
        out['classification']='patched_positive_control_not_observed';return out
    if s['step'] not in CHECKPOINT:return out
    last=CHECKPOINT.index(s['step'])
    if v[last] is None or any(x!=[1,1] for x in v[:last]) or any(x is not None for x in v[last+1:]):return out
    if s.get('graph_remaining')!=0:return out
    if last>=1 and v[1]!=[1,1]:
        out['classification']='version_change_after_common_graph_restore';return out
    c=s['ctx']
    if s['arm']==1:
        sham_ok=last==PAIRS-1 and v==[[1,1]]*PAIRS and s['ctl']==0x700 and s['cfg']==0x011a5e00 and c['spdi_writes']==c['bridge_writes']==c['at_writes']==0 and not c['spdi_applied'] and not c['bridge_applied'] and c['after_spdi']==c['census'] and c['after_bridge']==c['census'] and s.get('requests')==12
        out['classification']='sham_positive_control_passed' if sham_ok else 'sham_changed_or_incomplete'
    elif s['arm']==2:
        cfg=0 if s['step']>=30 else 0x011a5e00
        if s['ctl']!=0x700 or s['cfg']!=cfg or not arm2_writes_ok(s) or s.get('requests')!=2*(last+1):return out
        if v[last]!=[1,1]:out['classification']='version_change_after_'+BOUNDARY[last]
        elif last==PAIRS-1:out['classification']='tested_teardown_boundaries_preserved_patch'
    return out

def compare(sham,arm):
    a,b=analyze(sham),analyze(arm)
    out={'classification':'unmatched_or_unqualified','sham':a,'arm':b}
    ss,bs=sham.get('state',{}),arm.get('state',{})
    if ss.get('arm')!=1 or bs.get('arm')!=2 or a['classification']!='sham_positive_control_passed' or sham.get('boot_id')==arm.get('boot_id'):return out
    if ss.get('plan')!=bs.get('plan') or len(ss.get('graph_saved',[]))!=22 or ss['graph_saved']!=bs.get('graph_saved'):return out
    if sham.get('baseline',{}).get('reads')!=arm.get('baseline',{}).get('reads'):return out
    sc,bc=ss.get('ctx',{}),bs.get('ctx',{})
    for key in ('saved','saved_route','at_saved','census_stage','census_flags'):
        if sc.get(key)!=bc.get(key):return out
    # Allocator addresses may differ; everything else in the census must match.
    if not dma_consistent(sc) or not dma_consistent(bc):return out
    if [x for i,x in enumerate(sc['census']) if i not in DMA_WORDS]!=[x for i,x in enumerate(bc['census']) if i not in DMA_WORDS]:return out
    if sc['census'][11]&~0xf0!=bc['census'][11]&~0xf0:return out
    for key in ('manifest_sha256','cold_script_sha256','module_sha256'):
        if not sham.get('proof',{}).get(key) or sham['proof'][key]!=arm.get('proof',{}).get(key):return out
    if arm['proof'].get('sham_record_sha256')!=canonical(sham):return out
    if b['classification']=='inconclusive':return out
    out['classification']='matched_'+b['classification'];return out

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('records',nargs='+',type=Path);a=p.parse_args();r=[json.loads(f.read_text()) for f in a.records]
    if len(r) not in (1,2):p.error('one record or sham followed by teardown arm')
    print(json.dumps(analyze(r[0]) if len(r)==1 else compare(*r),indent=2))
if __name__=='__main__':main()
