#!/usr/bin/env python3
from pathlib import Path
import gzip,hashlib,json,shutil,subprocess,tempfile
p=Path('build/hdmi-dsp-boundary-2026-10-22/candidate').resolve()
m=json.loads((p/'manifest.json').read_text());sha=lambda q:hashlib.sha256(q.read_bytes()).hexdigest()
assert m['built'] and m['symvers_unchanged']
for name,info in m['artifacts'].items():assert sha(p/'artifacts'/name)==info['sha256']
for name,h in m['bundle'].items():assert sha(p/'bundle'/name)==h
assert sha(p/'kernel/Module.symvers')==m['baseline']['kernel_symvers']
assert sha(p/'kernel/drivers/pmdomain/sunxi/h713-retention-observer.inc')==m['observer_sha256']==sha(Path('tools/hdmi/dsp-boundary/observer.inc'))
assert not any(x in (p/'build.log').read_text().lower() for x in ('warning:','error:'))
base=Path(m['base']);dump=base/'uboot-obj/tools/dumpimage'
with tempfile.TemporaryDirectory() as t:
    t=Path(t)
    for index,name in enumerate(('Image.gz','board.dtb')):
        out=t/name
        subprocess.run([str(dump),'-T','flat_dt','-p',str(index),'-o',str(out),str(p/'artifacts/kernel.fit')],check=True,capture_output=True)
        assert out.read_bytes()==(p/'artifacts'/name).read_bytes()
    assert gzip.decompress((t/'Image.gz').read_bytes())==(p/'kernel/arch/arm64/boot/Image').read_bytes()
    original=base/'artifacts/board.dtb'
    assert sha(original)=='4c4fe0c55fd0d3498af8e10d5f850321e5b56121a06ceee31ea22a204aae4940'
    reference=t/'expected.dtb';shutil.copyfile(original,reference)
    for node in m['disabled_nodes']:
        subprocess.run(['fdtput','-t','s',str(reference),node,'status','disabled'],check=True)
        assert subprocess.check_output(['fdtget',str(t/'board.dtb'),node,'status'],text=True).strip()=='disabled'
    subprocess.run(['fdtput','-t','x',str(reference),'/chosen','h713,dsp-boundary-v1','424e4431'],check=True)
    assert reference.read_bytes()==(t/'board.dtb').read_bytes()
result={'fit':m['artifacts']['kernel.fit'],'kernel_version':m['kernel_uts_version'],
        'fit_image_and_dtb_extracted_match':True,'decompressed_Image_matches':True,
        'dtb_only_changes_two_disabled_nodes_and_marker':True,'symvers_unchanged':True,
        'observer_matches_source':True,'bundle_hashes_valid':True,'build_no_warnings_or_errors':True}
print(json.dumps(result,indent=2))
