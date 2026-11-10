#!/usr/bin/env python3
"""Bind host loader intent to one idle exact-kernel boot; no MMIO or step writes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

REMOTE='/root/hdmi-dsp-minimum-2026-10-22'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--intent',required=True,type=Path);p.add_argument('--prepared',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args()
    if args.output.exists():raise FileExistsError(args.output)
    intent=json.loads(args.intent.read_text());m=json.loads((args.prepared/'manifest.json').read_text())
    if intent.get('schema')!='h713-dsp-minimum-arm-v1' or intent.get('verified') or intent.get('warm_boot_id') or \
            intent.get('fit_sha256')!=m['artifacts']['kernel.fit']['sha256'] or \
            m.get('purpose')!='bench DSP minimum AudioTop; not installed' or intent.get('level') not in (1,2,3) or intent.get('arm')!='one-logo':
        raise ValueError('unbound exact-candidate loader intent required')
    # Pass serialized data on stdin as code literals, never through shell interpolation.
    script='''import hashlib,json,os,subprocess
from pathlib import Path
b=Path(%r)
intent=json.loads(%r)
m=json.loads(%r)
assert json.loads((b/'manifest.json').read_text())==m
assert os.uname().release==m['kernel_release'] and os.uname().version==m['kernel_uts_version']
for n,h in m['bundle'].items():assert hashlib.sha256((b/n).read_bytes()).hexdigest()==h,n
assert hashlib.sha256((b/'cold-census.json').read_bytes()).hexdigest()==intent['baseline_sha256']
assert json.loads((b/'cold-census.json').read_text())['boot_id']==intent['cold_boot_id']
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert boot!=intent['cold_boot_id']
assert all(t in Path('/proc/cmdline').read_text().split() for t in m['requires'])
assert not Path('/proc/device-tree/chosen/h713,hdmi-boot-v1').exists()
assert Path('/proc/device-tree/chosen/h713,dsp-minimum-v1').read_bytes()==bytes.fromhex('4d494e31')
for node in ('display@5600000','cpu-comm@3003000'):
 assert Path('/proc/device-tree/soc',node,'status').read_bytes().rstrip(b'\\0')==b'disabled'
s=json.loads(Path('/sys/kernel/h713_dsp_retention/state').read_text())
assert s['schema']=='h713-dsp-minimum-v1' and s['step']==s['attempted']==0 and s['hold']==1
assert s['violated']==s['failed']==s['timeout']==s['claimed']==0
assert s['level']==intent['level'] and s['setup_mask']==0
cmdline=Path('/proc/cmdline').read_text().split()
assert cmdline.count('h713_dsp_at_level='+str(intent['level']))==1
assert sum(t.startswith('h713_dsp_at_level=') for t in cmdline)==1
journal=subprocess.check_output(['journalctl','_BOOT_ID='+boot.replace('-',''),'_TRANSPORT=kernel','--no-pager','-o','cat'],text=True)
assert 'H713 RETENTION eligible=1' in journal and 'H713 RETENTION applied=1' in journal
assert 'H713 TVFE command domain=TVFE' not in journal and 'H713 RETENTION violated:' not in journal
assert hashlib.sha256(Path('/usr/lib/systemd/system-shutdown/h713-hdmi-hold-guard').read_bytes()).hexdigest()==m['bundle']['h713-hdmi-hold-guard']
for unit in ('capture','signal','speaker'):
 assert subprocess.run(['systemctl','is-active','h713-hdmi-'+unit+'.service'],capture_output=True,text=True).stdout.strip()=='inactive'
intent.update(verified=True,warm_boot_id=boot)
with (b/'arm-proof.json').open('x') as f:f.write(json.dumps(intent,indent=2)+'\\n')
print(json.dumps(intent,indent=2))
''' % (REMOTE,json.dumps(intent),json.dumps(m))
    cmd=['ssh','-F','/dev/null','-o','BatchMode=yes','-o','ConnectTimeout=5','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=1','root@192.168.4.1','python3 -']
    result=subprocess.run(cmd,input=script,capture_output=True,text=True)
    args.output.write_text(result.stdout+result.stderr)
    if result.returncode:raise SystemExit(result.returncode)
    print(result.stdout)
if __name__=='__main__':main()
