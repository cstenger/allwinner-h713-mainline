#!/usr/bin/env python3
"""Offline delta bundle: shared U-Boot script + Linux health acknowledgement."""
import argparse,hashlib,importlib.util,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'build/hdmi-reset-baseline-2026-10-20/artifacts/installed'
FIT_SHA='0877293b3a71b9ccd28c0f0ef9725752a86dffd243851a5213eb023cd3a51c70'
CMD_SHA='298fb56d6525e4984d75fd2a0dbe998dd6dba7e813393dd798a4a32371de99fb'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def build(out):
    if out.exists():raise FileExistsError(out)
    spec=importlib.util.spec_from_file_location('startup',ROOT/'tools/hdmi/build-startup.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    m.check_kernel()
    if sha(m.FIT)!=FIT_SHA or sha(OLD/'h713-hdmi.cmd')!=CMD_SHA:raise RuntimeError('validated input changed')
    out.mkdir(parents=True)
    for name in ('h713-hdmi-health-ack.py','h713-hdmi-health-ack.service','check-startup.sh','install-shared-startup.py'):
        shutil.copyfile(ROOT/'tools/hdmi'/name,out/name)
    text=m.script();(out/'h713-hdmi.cmd').write_text(text);(out/'h713-hdmi.scr').write_bytes(m.legacy_image(text.encode()))
    manifest={'schema':'h713-shared-startup-update-v1','fit_sha256':FIT_SHA,
              'previous':{n:sha(OLD/n) for n in ('h713-hdmi.scr','h713-hdmi.cmd')},
              'candidate':{n:sha(out/n) for n in ('h713-hdmi.scr','h713-hdmi.cmd')},
              'gp6':{'cold':'00000000','launch':'48444d49','healthy':'48444f4b','unknown':'logo-only'},
              'preboot':m.PREBOOT,'bootcmd':m.BOOTCMD,'requires_policy_and_install_approval':True}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (out/'SHA256SUMS').write_text(''.join(sha(p)+'  '+p.name+'\n' for p in sorted(out.iterdir()) if p.is_file()))
    return manifest
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args();print(json.dumps(build(a.output.resolve()),indent=2))
