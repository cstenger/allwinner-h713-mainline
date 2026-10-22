#!/usr/bin/env python3
"""Classify observed version changes separately from loss of access."""
import argparse,json
from pathlib import Path

def pair(p):
    return [v&0xffff for v in p['raw']] if p.get('outcome')==[1,1] and p.get('phase')==[5,5] and p.get('sent')==[1,1] else None

def analyze(r):
    s=r.get('state',{});p=r.get('proof',{});b=r.get('baseline',{})
    out={'classification':'inconclusive','versions':[pair(x) for x in s.get('pairs',[])], 'reset_erasure':'not measured'}
    if s.get('schema')!='h713-owner-boundary-v1' or not r.get('preflight_valid') or not p.get('verified') or p.get('boot_id')!=r.get('boot_id') or p.get('arm')!=s.get('arm') or s.get('failed') or s.get('claimed') or not s.get('terminal'):
        return out
    if not any('DSP versions 0000/0000' in l for l in b.get('dsp_journal',[])) or not any('pinned 724-pair DSP patch verified versions 1/1' in l for l in b.get('dsp_journal',[])) or b.get('boot_id')!=r['boot_id'] or not b.get('tv_domains_both_on') or b.get('reads',{}).get('mips_status')!='00000001':return out
    v=out['versions']
    if len(v)!=4:return out
    if any(0x80ff0000 in x.get('raw',[]) for x in s.get('pairs',[])):
        out['classification']='ambiguous_command_echo';return out
    if s.get('timeout'):
        out['classification']='access_timeout';return out
    if v[0]!=[1,1]:
        out['classification']='patched_positive_control_not_observed';return out
    if s['arm']==1:
        if s['step']==25 and v==[[1,1]]*4 and s.get('graph_remaining')==22 and s['ctl']==0x700 and s['cfg']==0x011a5e00:out['classification']='sham_positive_control_passed'
        else:out['classification']='sham_changed_or_incomplete'
    elif s['arm']==2 and s['ctl']==0x700 and s.get('graph_remaining')==0:
        if s['step']==12 and s['cfg']==0x011a5e00 and v[1] is not None and v[1]!=[1,1]:out['classification']='version_change_after_graph_restore'
        elif v[1]==[1,1] and s['cfg']==0:
            if s['step']==18 and v[2] is not None and v[2]!=[1,1]:out['classification']='version_change_after_config_clear'
            elif s['step']==25 and v[2]==[1,1] and v[3] is not None:
                out['classification']='version_change_after_control_off_on' if v[3]!=[1,1] else 'tested_shutdown_boundaries_preserved_patch'

    return out

def compare(sham,boundary):
    a,b=analyze(sham),analyze(boundary)
    out={'classification':'unmatched_or_unqualified','sham':a,'boundary':b}
    if sham.get('state',{}).get('arm')!=1 or boundary.get('state',{}).get('arm')!=2 or a['classification']!='sham_positive_control_passed' or sham.get('boot_id')==boundary.get('boot_id'):return out
    if len(sham.get('state',{}).get('graph_saved',[]))!=22 or sham['state']['graph_saved']!=boundary.get('state',{}).get('graph_saved'):return out
    if sham.get('baseline',{}).get('reads')!=boundary.get('baseline',{}).get('reads'):return out
    for key in ('manifest_sha256','cold_script_sha256','module_sha256'):
        if not sham.get('proof',{}).get(key) or sham['proof'][key]!=boundary.get('proof',{}).get(key):return out
    if boundary['proof'].get('sham_record_sha256')!=__import__('hashlib').sha256((json.dumps(sham,sort_keys=True)+'\n').encode()).hexdigest():return out
    out['classification']='matched_'+b['classification'];return out

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('records',nargs='+',type=Path);a=p.parse_args();r=[json.loads(f.read_text()) for f in a.records]
    if len(r) not in (1,2):p.error('one record or sham followed by boundary')
    print(json.dumps(analyze(r[0]) if len(r)==1 else compare(*r),indent=2))
if __name__=='__main__':main()
