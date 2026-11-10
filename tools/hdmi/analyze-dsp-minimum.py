#!/usr/bin/env python3
"""Report completed access separately from patch retention; compare stock prefixes."""
import argparse
import json
from pathlib import Path


def baseline_valid(b):
    return bool(b.get('boot_id')) and b.get('hdmi_handoff') is True and \
        b.get('tv_domains_both_on') is True and \
        all(b.get('units', {}).get(u) == 'active' for u in ('capture', 'signal', 'speaker')) and \
        any('DSP versions 0000/0000' in line for line in b.get('dsp_journal', [])) and \
        any('pinned 724-pair DSP patch verified versions 1/1' in line for line in b.get('dsp_journal', []))


def analyze(record):
    s=record['state'];b=record['baseline'];proof=record.get('arm_proof',{})
    out={'classification':'inconclusive','level':s.get('level'),'versions':None,
         'completed_access':False,'patch_retained':None,'minimum_among_all_bit_combinations':'not tested',
         'reset_erasure':'not measured'}
    level=s.get('level')
    valid=record.get('preflight_valid') is True and baseline_valid(b) and \
        record.get('warm_boot_id') not in (None,'',b['boot_id']) and \
        s.get('schema')=='h713-dsp-minimum-v1' and s.get('step')==58 and s.get('hold')==1 and \
        all(s.get(k)==0 for k in ('violated','failed','claimed')) and level in (1,2,3) and \
        s.get('ctl_before')==s.get('cfg_before')==0 and s.get('setup_mask')==(1<<level)-1 and \
        proof.get('verified') is True and proof.get('arm')=='one-logo' and proof.get('level')==level and \
        proof.get('cold_boot_id')==b['boot_id'] and proof.get('warm_boot_id')==record['warm_boot_id'] and \
        bool(proof.get('fit_sha256')) and s.get('setup_readback')==[0x700, 0x001a5e00 if level>=2 else 0xffffffff, 0x011a5e00 if level>=3 else 0xffffffff]
    if not valid:return out
    pairs=s.get('pairs')
    if not isinstance(pairs,list) or len(pairs)!=1:return out
    pair=pairs[0]
    if not isinstance(pair,dict):return out
    if s.get('timeout')==1:
        # Require exact protocol-phase evidence before treating a trial as a qualified timeout.
        phase,sent,outcome=s.get('phase'),s.get('sent'),pair.get('outcome')
        if outcome==[2,3] and phase in ([1,6],[4,6]) and sent==([0,0] if phase[0]==1 else [1,0]):
            out['classification']='initial_busy_timeout' if phase[0]==1 else 'command_sent_done_timeout'
        elif outcome==[1,2] and phase in ([5,1],[5,4]) and sent==([1,0] if phase[1]==1 else [1,1]):
            out['classification']='device1_busy_timeout' if phase[1]==1 else 'device1_done_timeout'
        return out
    raw=pair.get('raw')
    if s.get('timeout')!=0 or pair.get('outcome')!=[1,1] or s.get('phase')!=[5,5] or s.get('sent')!=[1,1] or \
            not isinstance(raw,list) or len(raw)!=2 or not all(isinstance(v,int) and 0<=v<=0xffffffff for v in raw):
        return out
    versions=[v&0xffff for v in raw]
    out.update(classification='completed_version_pair',completed_access=True,versions=versions,
               patch_retained=True if versions==[1,1] else False if versions==[0,0] else None)
    return out


def compare(records):
    results=[analyze(r) for r in records]
    out={'classification':'inconclusive','lowest_completed_stock_prefix':None,'trials':results}
    levels=[r['state'].get('level') for r in records]
    if not records or len(set(levels))!=len(levels):return out
    proofs=[r.get('arm_proof',{}) for r in records]
    if any(not p.get('fit_sha256') for p in proofs) or len({p['fit_sha256'] for p in proofs})!=1:return out
    if len({r['baseline']['boot_id'] for r in records})!=len(records) or \
            len({r.get('warm_boot_id') for r in records})!=len(records):return out
    context=('demod_before','display_reset_before','tvcap_reset_before','route_writes','routes_before','tv_before')
    if any(any(k not in r['state'] for k in context) for r in records):return out
    if len({json.dumps({k:r['state'][k] for k in context},sort_keys=True) for r in records})!=1:return out
    completed=[r['level'] for r in results if r['completed_access']]
    if not completed:return out
    best=min(completed);by_level={r['level']:r for r in results}
    if all(i in by_level and by_level[i]['classification'] in ('command_sent_done_timeout','device1_done_timeout')
           for i in range(1,best)):
        out.update(classification='lowest_completed_stock_prefix_identified',lowest_completed_stock_prefix=best)
    else:
        out.update(classification='completed_prefix_with_lower_levels_unresolved')
    return out


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('records',nargs='+',type=Path);args=p.parse_args()
    records=[json.loads(p.read_text()) for p in args.records]
    print(json.dumps(analyze(records[0]) if len(records)==1 else compare(records),indent=2))
if __name__=='__main__':main()
