#!/usr/bin/env python3
"""Export only the locked proprietary assets, never an installed software bundle."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[2]


LOCKS={'ddr3':'config/production-vendor.json','v2':'config/production-vendor-v2.json'}


def export(boot,wifi,dsp,output,board='ddr3'):
    if output.exists():raise ValueError('output must be new')
    pins=json.loads((ROOT/LOCKS[board]).read_text())['files']
    if boot is None and any(name.startswith('boot/') for name in pins):
        raise ValueError('this board locks boot assets; --boot-directory is required')
    sources={}
    for name,pin in pins.items():
        category,relative=name.split('/',1)
        source=boot/relative if category=='boot' else wifi/relative if category=='wifi' else dsp
        data=source.read_bytes()
        if hashlib.sha256(data).hexdigest()!=pin['sha256']:raise ValueError('firmware pin mismatch: '+name)
        if 'bytes' in pin and len(data)!=pin['bytes']:raise ValueError('firmware size mismatch: '+name)
        sources[name]=data
    output.mkdir(parents=True,mode=0o700)
    for name,data in sources.items():
        dest=output/name;dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(data);dest.chmod(0o600)
    print(json.dumps(dict(status='PASS',files=len(sources),output=str(output)),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--board',choices=sorted(LOCKS),default='ddr3',
                   help='which vendor lock to export (v2 needs no boot assets)')
    p.add_argument('--boot-directory',type=Path)
    p.add_argument('--wifi-directory',required=True,type=Path)
    p.add_argument('--dsp',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();export(a.boot_directory,a.wifi_directory,a.dsp,a.output,a.board)
