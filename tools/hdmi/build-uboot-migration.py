#!/usr/bin/env python3
"""Prepare a private offline-only DDR3 migration package from pinned retained bytes."""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess

ROOT=Path(__file__).resolve().parents[2]
CAPACITY=7818182656


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(value,reason):
    if not value:
        raise ValueError(reason)


def build(output):
    require(not output.exists(), 'output already exists')
    subprocess.run(['python3',str(ROOT/'tools/hdmi/check-uboot-migration-inputs.py')],check=True,capture_output=True)
    build=ROOT/'build/uboot-ddr3'
    inputs=(ROOT/'build/out/u-boot-ddr3.inputs').read_text()
    combined=(ROOT/'build/out/u-boot-sunxi-with-spl-ddr3.bin').read_bytes()
    require('board ddr3\n' in inputs and 'image '+sha(combined)+'\n' in inputs, 'build provenance mismatch')
    require('0003-env-mmc-preserve-configured-offset-width.patch' in inputs, 'width patch absent from provenance')
    patch_name='0003-env-mmc-preserve-configured-offset-width.patch'
    require('patch '+patch_name+' '+sha((ROOT/'patches/u-boot'/patch_name).read_bytes())+'\n' in inputs,
            'source patch changed after build')
    config=(build/'.config').read_bytes()
    require('config '+sha(config)+'\n' in inputs, 'config provenance mismatch')
    for setting in ['CONFIG_ENV_SIZE=0x10000','CONFIG_ENV_OFFSET=0x93d80000',
                    'CONFIG_ENV_MMC_EMMC_HW_PARTITION=0', 'CONFIG_ENV_IS_IN_MMC=y',
                    '# CONFIG_ENV_REDUNDANT is not set', '# CONFIG_ENV_MMC_USE_DT is not set',
                    '# CONFIG_PARTITION_TYPE_GUID is not set', '# CONFIG_ENV_MMC_USE_SW_PARTITION is not set',
                    '# CONFIG_ENV_OFFSET_RELATIVE_END is not set']:
        require(setting+'\n' in config.decode(), 'unexpected configuration: '+setting)
    source_dirs=[p for p in (ROOT/'build').glob('uboot-src-*')
                 if (p/'.h713-build-inputs').exists() and inputs.startswith((p/'.h713-build-inputs').read_text())]
    require(len(source_dirs)==1, 'prepared source identity ambiguous')
    tree=source_dirs[0]
    require('return defvalue;' in (tree/'env/mmc.c').read_text(), 'fallback fix absent')
    require('reset-trace' not in (tree/'arch/arm/mach-sunxi/h713_mips.c').read_text(), 'diagnostic trace source present')
    require('Reading from MMC(%d) at 0x%08x...' in (tree/'env/mmc.c').read_text(), 'selected-address UART evidence missing')
    require(sha((tree/'arch/arm/mach-sunxi/h713_mips.c').read_bytes()) ==
            '3c44fc5af23eaa55a698fbc1e5e509cb23cff76382c4d5425b1d178cc829b450', 'panel source changed')
    fit=combined[32768:]
    magic,total=struct.unpack('>II',fit[:8])
    require(magic==0xd00dfeed and len(fit)==total, 'combined proper FIT layout differs')
    oldbase=ROOT/'build/hdmi-reset-controls-2026-10-20'
    previous=json.loads((oldbase/'trial-package/manifest.json').read_text())
    oldconfig=(oldbase/'obj/.config').read_text()
    effective=lambda text:[line for line in text.splitlines() if line.startswith(('CONFIG_', '# CONFIG_'))
                           and not line.startswith('CONFIG_CLANG_VERSION=')]
    require(effective(oldconfig)==effective(config.decode()), 'effective config changed beyond compiler version')
    old=(oldbase/'trial-package/proper-controls.bin').read_bytes()
    region=(oldbase/'artifacts/proper-region-2MiB.bin').read_bytes()
    require(sha(region)==previous['before_region_sha256'], 'historical proper region differs')
    current=old+region[len(old):]
    require(sha(current)==previous['after_region_sha256'], 'current full proper region reconstruction failed')
    extent=max(len(old),((len(fit)+511)//512)*512)
    require(extent<=len(region), 'candidate exceeds retained proper-region backup')
    require(0x49ac00*512+extent <= 0x49ec00*512, 'candidate overlaps intended environment')
    after=fit.ljust(extent,b'\0')
    env=(ROOT/'build/hdmi-reset-baseline-2026-10-20/trial-package/active-environment-backup.bin').read_bytes()
    spl=(ROOT/'local/h713-lab/uboot-backup-20261016/spl-lba10.bin').read_bytes()
    rescue=(oldbase/'artifacts/rescue-region-2MiB.bin').read_bytes()
    require(sha(rescue[:1798*512])=='c882461d5ee69128c79d99b784fde668ee4d57ab09ae308738e3f9ea91fd1ce7', 'rescue prefix mismatch')
    rescue_magic,rescue_total=struct.unpack('>II',rescue[:8])
    require(rescue_magic==0xd00dfeed and 0<rescue_total<=len(rescue), 'rescue FIT size invalid')
    # These are unmistakable test markers, not a saved physical GPT or CID.
    marker=json.dumps({'fixture_only':True,'board':'HY200 QZ713DF_A1 DDR3',
                       'capacity':CAPACITY,'sector':512},sort_keys=True).encode().ljust(4096,b'\0')
    output.mkdir(parents=True,mode=0o700)
    def blob(name,data):
        path=output/name;path.write_bytes(data);path.chmod(0o600)
        return dict(file=name,bytes=len(data),sha256=sha(data))
    writes=[]
    for name,lba,before,new in [('environment',0x49ec00,bytes(65536),env),
                                ('proper',0x49ac00,current[:extent],after)]:
        writes.append(dict(name=name,offset=lba*512,before=blob(name+'-before.bin',before),
                           after=blob(name+'-after.bin',new)))
    protected=[]
    for name,offset,data in [('fixture-primary-marker',0,marker),
                             ('fixture-backup-marker',CAPACITY-4096,marker[::-1]),
                             ('spl',0x10*512,spl),('active-environment',0x32ec00*512,env),
                             ('rescue-full-region',0x4a0c00*512,rescue),
                             ('proper-region-tail',0x49ac00*512+extent,current[extent:])]:
        item=blob(name+'.bin',data);item.update(name=name,offset=offset);protected.append(item)
    # Independently extract the FIT components; do not assume the combined image preserves them.
    fit_path=output/'candidate.fit';fit_path.write_bytes(fit);fit_path.chmod(0o600)
    components={}
    for index,name,expected in [(1,'bl31.bin','5ea11b14cc59a85b3219b4969836948a1f99ab0381d620476e557f993c78636c'),
                                (2,'uboot.dtb','8361009b1b72345c6d03d0e7ad98b6930753aea5c387e848677bdc0e587f464e')]:
        path=output/name
        subprocess.run([str(build/'tools/dumpimage'),'-T','flat_dt','-p',str(index),'-o',str(path),str(fit_path)],check=True,capture_output=True)
        path.chmod(0o600);require(sha(path.read_bytes())==expected,'FIT component changed: '+name)
        components[name]=expected
    config_node=subprocess.run(['fdtget','-l',str(output/'uboot.dtb'),'/config'],capture_output=True)
    require(config_node.returncode!=0 and b'NOTFOUND' in config_node.stderr, 'unexpected DT /config node')
    manifest=dict(schema=1,offline_only=True,sector_bytes=512,capacity_bytes=CAPACITY,
                  writes=writes,protected=protected,candidate_fit_bytes=len(fit),
                  candidate_sectors=(len(fit)+511)//512,transaction_sectors=extent//512,
                  rollback_proper_sha256=sha(old),candidate_extent_sha256=sha(after),
                  fit_components=components,source_tree=tree.name,
                  config_sha256=sha(config),rescue_fit_bytes=rescue_total,
                  live_preflight_required=['model','CID','capacity','sector size','hardware partition',
                    'GPT ownership and hashes','boot ID','fresh proper and both environments',
                    'fresh SPL/rescue/full surrounding regions','filesystem and HDMI health'],
                  limitation='Retained historical inputs and synthetic fixture markers; block devices refused.')
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (output/'build.inputs').write_text(inputs)
    (output/'uboot.config').write_bytes(config)
    (output/'source-inputs.txt').write_bytes((tree/'.h713-build-inputs').read_bytes())
    (output/'mmc.c').write_bytes((tree/'env/mmc.c').read_bytes())
    (output/'compiler.txt').write_bytes(subprocess.check_output(['clang','--version']))
    (output/'config-difference.diff').write_text(''.join(difflib.unified_diff(oldconfig.splitlines(True),config.decode().splitlines(True),
                                                      fromfile='installed-diagnostic-config',tofile='candidate-production-config')))
    (output/'width-fix.patch').write_bytes((ROOT/'patches/u-boot'/patch_name).read_bytes())
    (output/'RECOVERY.txt').write_text(f'''OFFLINE PREPARATION: hardware use requires fresh identity/GPT/preimage checks,
explicit installation/recovery authorization and the operator sequence.
Do not execute these commands on a board from this historical package alone.

Private exact rollback payload: proper-before.bin
SHA-256: {sha(current[:extent])}
Bytes: {extent} (0x{extent:x}); sectors: {extent//512} (0x{extent//512:x})
This restores current diagnostic proper; it does not install an older rescue image.

After verified FEL rescue SPL/prompt and exclusive YMODEM ownership:
loady 0x42000000
Transfer proper-before.bin, then restore passive UART logging.
Verify filesize is {extent:x}; verify RAM hash equals the full SHA-256 above:
hash sha256 0x42000000 0x{extent:x}
Only with all live preconditions and approved recovery, select the independently
verified eMMC device's USER hardware partition (not a guessed SD device):
mmc dev <verified-eMMC-index> 0
mmc write 0x42000000 0x49ac00 0x{extent//512:x}
mmc read 0x43000000 0x49ac00 0x{extent//512:x}
cmp.b 0x42000000 0x43000000 0x{extent:x}
Verify protected SPL/rescue/old environment and full surrounding region.
Stop on any error; no automatic reset/retry.

Old active environment LBA 0x32ec00 must remain untouched.
Intended-slot rollback preimage environment-before.bin: {sha(bytes(65536))}
Restore that preimage only AFTER old proper is restored and verified, under the
approved rollback scope. No saveenv, environment edits or erasure of super.
The normal candidate should report Reading from MMC(1) at 0x93d80000 on the
bench eMMC boot; verify actual boot-device selection rather than assuming it.
''')
    for name in ['uboot-migration.py','rehearse-uboot-migration.py']:
        shutil.copyfile(ROOT/'tools/hdmi'/name,output/name)
    (output/'README.txt').write_text('''OFFLINE REHEARSAL ONLY — NOT AUTHORIZED OR EQUIPPED FOR BOARD INSTALLATION.
This private package includes raw environment/firmware; do not commit it.
The engine accepts regular host images only. CID/GPT/boot identity are not live-pinned.
Generate a new package from fresh read-only backups before deployment review.
Writes stage the environment first, then proper. Rollback restores proper first.
Never flash the combined SPL+proper output, clear the old environment in super,
or run historical 1798/1867-sector recovery commands for this generation.
Run: python3 rehearse-uboot-migration.py --package . --work /new/host/work/path
See docs/uboot-environment-migration-2026-10-30.md for live acceptance gates.
''')
    for path in output.iterdir():path.chmod(0o600)
    (output/'SHA256SUMS').write_text(''.join(sha(p.read_bytes())+'  '+p.name+'\n' for p in sorted(output.iterdir()) if p.is_file()))
    print(json.dumps({k:manifest[k] for k in ['offline_only','candidate_fit_bytes','candidate_sectors','transaction_sectors','candidate_extent_sha256','fit_components']},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path)
    build(p.parse_args().output.resolve())
