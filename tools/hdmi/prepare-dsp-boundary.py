#!/usr/bin/env python3
"""Build isolated boundary observer and matched-arm FIT. Never installs or boots."""
import argparse
import gzip
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec=importlib.util.spec_from_file_location('retention_prepare',HERE/'prepare-dsp-retention.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
sha=old.sha
REL=old.REL
DISABLED=('/soc/display@5600000','/soc/cpu-comm@3003000')

def prepare(base,output):
    base,output=base.resolve(),output.resolve()
    if output.exists():raise FileExistsError(output)
    if base==output or base in output.parents or output in base.parents:raise ValueError('separate output required')
    m=json.loads((base/'manifest.json').read_text())
    if not m.get('built') or not m.get('symvers_unchanged') or \
        sha(base/'artifacts/kernel.fit')!='538224b413efa5bd7d92a4196c8a7327a223eebec32dc4fe124dbabc7b35c553' or \
        sha(base/'kernel'/REL)!='25641dfbdbafbe2e1b467f3024aa1e385980f58462946af2c7e2fed7bfbd8cf0':
        raise ValueError('exact tested retention candidate-v2 required')
    output.mkdir(parents=True)
    subprocess.run(['cp','-a','--reflink=auto',str(base/'kernel'),str(output/'kernel')],check=True)
    observer=output/'kernel'/Path(REL).parent/'h713-retention-observer.inc'
    shutil.copyfile(HERE/'dsp-boundary/observer.inc',observer)
    bundle=output/'bundle';bundle.mkdir()
    for name in ('dsp-boundary.py','analyze-dsp-boundary.py'):
        shutil.copyfile(HERE/name,bundle/name)
    shutil.copyfile(base/'bundle/h713-hdmi-hold-guard',bundle/'h713-hdmi-hold-guard')
    m.update(purpose='bench DSP boundary attribution; not installed',built=False,
        retention_base=str(base),base=m['base'],
        observer_sha256=sha(observer),disabled_nodes=DISABLED,dt_marker='424e4431',
        requires=m['requires']+['h713_dsp_boundary=1'],
        assets={p.name:sha(p) for p in (HERE/'dsp-boundary').iterdir() if p.is_file()},
        bundle={p.name:sha(p) for p in bundle.iterdir()})
    m.pop('artifacts',None)
    (output/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')

def build(output,jobs):
    m=json.loads((output/'manifest.json').read_text());kernel=output/'kernel'
    cmd=['make','-C',str(kernel),'ARCH=arm64','LLVM=1','-j'+str(jobs),'Image','modules']
    with (output/'build.log').open('w') as log:subprocess.run(cmd,check=True,stdout=log,stderr=subprocess.STDOUT)
    a=output/'artifacts';a.mkdir()
    (a/'Image.gz').write_bytes(gzip.compress((kernel/'arch/arm64/boot/Image').read_bytes(),mtime=0))
    base=Path(m['base']);shutil.copyfile(base/'artifacts/board.dtb',a/'board.dtb')
    assert sha(a/'board.dtb')=='4c4fe0c55fd0d3498af8e10d5f850321e5b56121a06ceee31ea22a204aae4940'
    for node in DISABLED:subprocess.run(['fdtput','-t','s',str(a/'board.dtb'),node,'status','disabled'],check=True)
    subprocess.run(['fdtput','-t','x',str(a/'board.dtb'),'/chosen','h713,dsp-boundary-v1','424e4431'],check=True)
    its=(base/'artifacts/kernel.its').read_text().replace(str(base/'artifacts'),str(a)).replace('H713 bench TVFE boot trace v1','H713 bench DSP boundary v1')
    (a/'kernel.its').write_text(its)
    subprocess.run([str(base/'uboot-obj/tools/mkimage'),'-f',str(a/'kernel.its'),str(a/'kernel.fit')],check=True,capture_output=True)
    shutil.copyfile(a/'kernel.fit',output/'bundle/kernel.fit')
    m.update(built=True,build_command=cmd,
        kernel_release=(kernel/'include/config/kernel.release').read_text().strip(),
        kernel_uts_version=(kernel/'include/generated/utsversion.h').read_text().split('"')[1],
        symvers_unchanged=sha(kernel/'Module.symvers')==m['baseline']['kernel_symvers'],
        artifacts={p.name:{'size':p.stat().st_size,'sha256':sha(p)} for p in a.iterdir()},
        bundle={p.name:sha(p) for p in (output/'bundle').iterdir() if p.name!='manifest.json'})
    if not m['symvers_unchanged']:raise RuntimeError('exported symbols changed; no adoption')
    for path in (output/'manifest.json',output/'bundle/manifest.json'):path.write_text(json.dumps(m,indent=2)+'\n')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--build',action='store_true');p.add_argument('--jobs',type=int,default=12)
    args=p.parse_args()
    if args.jobs<1:p.error('positive job count required')
    prepare(args.base,args.output)
    if args.build:build(args.output.resolve(),args.jobs)
    print(args.output.resolve()/'manifest.json')
if __name__=='__main__':main()
