#!/usr/bin/env python3
"""RAM-only matched-arm boot; validates captured reset/logo evidence and hook."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
from console import open_port, write_slow, drain

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('retention_runner',HERE/'run-dsp-retention-boot.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
loader=r.loader
loader.REMOTE_FIT='/root/hdmi-dsp-boundary-2026-10-22/kernel.fit'
loader.BOOTARGS+=' h713_dsp_boundary=1'


def arm_proof(arm,ack,baseline,catch,logo=None):
    analysis_spec=importlib.util.spec_from_file_location('boundary_analyzer',HERE.parent/'hdmi/analyze-dsp-boundary.py')
    analysis=importlib.util.module_from_spec(analysis_spec);analysis_spec.loader.exec_module(analysis)
    b=json.loads(baseline.read_text())
    if not analysis.baseline_valid(b):raise ValueError('fresh patched cold baseline required')
    raw=catch.read_bytes()
    if raw.count(b'U-Boot SPL ')!=1 or not re.search(rb'(?m)^H713 RESET v1 stage=proper_preboot gp6=48444d49 gp7=00000000 .*mips_status=00000000\r?$',raw):
        raise ValueError('one captured warm reset with retained GP6 and parked MIPS required')
    if not re.search(rb'=>\s*$',raw):raise ValueError('catch must stop at U-Boot')
    out={'schema':'h713-dsp-boundary-arm-v1','arm':arm,'cold_boot_id':b['boot_id'],
         'baseline_sha256':hashlib.sha256(baseline.read_bytes()).hexdigest(),
         'warm_catch_sha256':hashlib.sha256(raw).hexdigest(),'verified':False,'warm_boot_id':None}
    if arm=='no-logo':
        if ack!='no-warm-logo-executed' or logo is not None or b'stage=post_logo' in raw:
            raise ValueError('no-logo arm forbids a logo; explicit no-logo acknowledgment required')
    else:
        if ack!='one-reviewed-warm-logo' or logo is None:raise ValueError('single-logo evidence required')
        log=logo.read_bytes()
        if len(re.findall(rb'(?m)^H713_DSP_BOUNDARY_LOGO_OK\r?$',log))!=1 or \
                len(re.findall(rb'(?m)^H713 RESET v1 stage=post_logo .*mips_status=00000000\r?$',log))!=1 or \
                b'U-Boot SPL ' in log:
            raise ValueError('exactly one completed warm logo with parked MIPS required')
        out['logo_sha256']=hashlib.sha256(log).hexdigest()
    return out


def validate(prepared):
    m=json.loads((prepared/'manifest.json').read_text())
    if m.get('purpose')!='bench DSP boundary attribution; not installed' or 'h713_dsp_boundary=1' not in m.get('requires',[]):
        raise ValueError('built boundary candidate required')
    r.guard_bytes=(prepared/'bundle/h713-hdmi-hold-guard').read_bytes()
    if hashlib.sha256(r.guard_bytes).hexdigest()!=m['bundle']['h713-hdmi-hold-guard']:
        raise ValueError('guard changed')
    return r.original_validate(prepared)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True);p.add_argument('--prepared',required=True,type=Path)
    p.add_argument('--expected-bootcmd',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--arm',required=True,choices=('no-logo','one-logo'))
    p.add_argument('--arm-ack',required=True,choices=('no-warm-logo-executed','one-reviewed-warm-logo'))
    p.add_argument('--baseline',required=True,type=Path);p.add_argument('--warm-catch',required=True,type=Path)
    p.add_argument('--logo-log',type=Path)
    args=p.parse_args()
    proof=arm_proof(args.arm,args.arm_ack,args.baseline,args.warm_catch,args.logo_log)
    fit=validate(args.prepared)
    proof['fit_sha256']=hashlib.sha256(fit).hexdigest()
    args.output.mkdir(parents=True,exist_ok=False)
    fd=open_port(args.port)
    try:
        with (args.output/'serial.log').open('xb',buffering=0) as raw:
            write_slow(fd,b'\n');initial=drain(fd,1,echo=False);raw.write(initial)
            if not re.search(rb'=>\s*$',initial):raise RuntimeError('U-Boot prompt required; no retry')
            before,final=r.original_boot(loader.Console(fd,raw),args.expected_bootcmd.read_text().rstrip('\n'),fit,
                                         before_load=r.check_installed_guard)
            (args.output/'preboot.json').write_text(json.dumps({'before':before,'final':final,'bootargs':loader.BOOTARGS,
                'fit_sha256':proof['fit_sha256'],'arm':args.arm},indent=2)+'\n')
            (args.output/'arm-intent.json').write_text(json.dumps(proof,indent=2)+'\n')
            write_slow(fd,b'bootm 0x50000000\n');loader.capture(fd,raw,60)
    finally:os.close(fd)
    print('Capture ended. Bind arm intent to the verified fresh Linux boot before any observer step.')
if __name__=='__main__':main()
