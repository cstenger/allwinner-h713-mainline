#!/usr/bin/env python3
"""Boot the isolated cold Phase A teardown bench via a RAM script; never installs or resets."""
import argparse,hashlib,importlib.util,json,os
from pathlib import Path
import re,subprocess,sys,zlib
sys.path.insert(0,str(Path(__file__).resolve().parent))
from console import open_port,write_slow,drain
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('trace_runner',HERE/'run-tvfe-boot-trace.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
ROOT=HERE.parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def intent(prepared,cold,arm,sham=None):
    m=json.loads((prepared/'manifest.json').read_text());raw=cold.read_bytes()
    assert raw.count(b'U-Boot SPL ')==1
    assert re.search(rb'(?m)^H713 RESET v1 stage=proper_preboot gp6=00000000 gp7=00000000 .*mips_status=00000000\r?$',raw)
    assert raw.rstrip().endswith(b'=>') and b'stage=pre_workspace' not in raw
    assert arm in (1,2) and sha(prepared/'cold-teardown.scr')==m['cold_script_sha256']
    out={'schema':'h713-teardown-a-arm-v1','arm':arm,'verified':False,'boot_id':None,'manifest_sha256':sha(prepared/'manifest.json'),'module_sha256':m['bundle']['h713-hdmi-audio.ko'],'cold_script_sha256':m['cold_script_sha256'],'cold_catch_sha256':hashlib.sha256(raw).hexdigest()}
    if arm==2:
        assert sham is not None
        analysis_spec=importlib.util.spec_from_file_location('teardown_analysis',ROOT/'tools/hdmi/analyze-dsp-teardown-a.py');a=importlib.util.module_from_spec(analysis_spec);analysis_spec.loader.exec_module(a)
        record=json.loads(sham.read_text());assert a.analyze(record)['classification']=='sham_positive_control_passed' and record['state']['schema']=='h713-teardown-a-v1'
        assert record['proof']['manifest_sha256']==out['manifest_sha256'] and record['proof']['module_sha256']==out['module_sha256'] and record['proof']['cold_script_sha256']==out['cold_script_sha256']
        out['sham_record_sha256']=a.canonical(record)
    else:assert sham is None
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',required=True,type=Path);p.add_argument('--cold-catch',required=True,type=Path);p.add_argument('--arm',required=True,type=int,choices=(1,2));p.add_argument('--sham-record',type=Path);p.add_argument('--port',required=True);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    proof=intent(a.prepared,a.cold_catch,a.arm,a.sham_record)
    m=json.loads((a.prepared/'manifest.json').read_text());fit=ROOT/'build/out/h713-kernel.fit'
    assert sha(fit)==m['production_fit_sha256']
    a.output.mkdir(parents=True,exist_ok=False)
    (a.output/'arm-intent.json').write_text(json.dumps(proof,indent=2)+'\n')
    if a.sham_record:(a.output/'sham-record.json').write_bytes(a.sham_record.read_bytes())
    fd=open_port(a.port)
    try:
        with (a.output/'preboot-uart.log').open('xb',buffering=0) as raw:
            write_slow(fd,b'\n');initial=drain(fd,1,echo=False);raw.write(initial)
            assert re.search(rb'=>\s*$',initial)
            con=r.Console(fd,raw)
            assert r.warm.parse_bootcmd(con.run('printenv bootcmd'))=='if fatload mmc 1:2 0x52000000 h713-hdmi.scr; then source 0x52000000; else echo HDMI startup script missing - use h713_hdmi_previous_bootcmd for recovery; fi'
            for addr in (0x07090118,0x0306101c):assert r.warm.parse_md(con.run('md.l 0x%08x 1'%addr),addr)==0
            con.checked('fatload mmc 1:2 0x50000000 h713-kernel.fit')
            con.checked('itest ${filesize} == %x'%fit.stat().st_size)
            match=re.search(rb'==>\s*([0-9a-fA-F]{8})\b',con.run('crc32 0x50000000 %x'%fit.stat().st_size))
            assert match and int(match.group(1),16)==zlib.crc32(fit.read_bytes())
    finally:os.close(fd)
    # Transfer is software-only; the reviewed sender checks RAM CRC before return.
    result=subprocess.run([sys.executable,str(HERE/'ymodem-send.py'),str(a.prepared/'cold-teardown.scr'),'0x52000000','--port',a.port],capture_output=True,text=True,timeout=60)
    (a.output/'script-transfer.log').write_text(result.stdout+result.stderr);result.check_returncode()
    fd=open_port(a.port)
    try:
        with (a.output/'serial.log').open('xb',buffering=0) as raw:
            write_slow(fd,b'\n');initial=drain(fd,1,echo=False);raw.write(initial);assert re.search(rb'=>\s*$',initial)
            (a.output/'launch-attempted').write_text('One cold startup source command; no retry permitted.\n')
            write_slow(fd,b'source 0x52000000\n');r.capture(fd,raw,90)
    finally:os.close(fd)
    print('Capture ended; verify source3/handoff/kernel and stage the exact bundle before initialize. Do not launch again.')
if __name__=='__main__':main()
