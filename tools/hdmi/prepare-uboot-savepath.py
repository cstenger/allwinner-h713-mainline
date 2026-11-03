#!/usr/bin/env python3
"""Build a private preparation packet from read-only backups; never contact hardware."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import secrets
import shutil
import struct
import tarfile
import zlib

ROOT=Path(__file__).resolve().parents[2]


def require(value,message):
    if not value:raise ValueError(message)


def sha(data):return hashlib.sha256(data).hexdigest()


def build(capture,output):
    require(not output.exists(),'output already exists')
    spec=importlib.util.spec_from_file_location('savepath',ROOT/'tools/hdmi/check-uboot-savepath.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
    prior=ROOT/'local/recovery/2026-10-30-uboot-migration-install/package'
    for line in (prior/'SHA256SUMS').read_text().splitlines():
        digest,name=line.split('  ',1);require(Path(name).name==name and sha((prior/name).read_bytes())==digest,'prior package checksum mismatch')
    m=json.loads((prior/'manifest.json').read_text())
    expected=json.loads((ROOT/'docs/hdmi-evidence/2026-10-31-uboot-warm-validation/RUN-RESULT.json').read_text())['postboot_id']
    with tarfile.open(capture) as t:
        members=t.getmembers();require(all(p.isfile() and Path(p.name).name==p.name for p in members),'unsafe capture member')
        require(len(members)==len({p.name for p in members}),'duplicate capture member')
        files={p.name:t.extractfile(p).read() for p in members}
    x=json.loads(files['inventory.json'])
    require(x['identity']['boot_id']==x['ending_boot_id']==x['session']['boot_id']==expected and x['session']['phase']=='ready','expected healthy warm boot changed')
    for key in ['model','cid','capacity_bytes','logical_sector_bytes','device','type','dev_number','linux_hardware_partition']:
        require(x['identity'][key]==m['live_identity'][key],'board identity mismatch: '+key)
    for name,item in x['ranges'].items():require(len(files[name])==item['bytes'] and sha(files[name])==item['sha256'],'capture hash mismatch: '+name)
    for region in m['writes']+m['protected']:
        size=region.get('bytes',region.get('after',{}).get('bytes'));digest=region.get('sha256',region.get('after',{}).get('sha256'))
        captures=[(name,item) for name,item in x['ranges'].items() if item['offset']<=region['offset'] and region['offset']+size<=item['offset']+item['bytes']]
        require(bool(captures),'uncaptured protected/write region')
        name,item=captures[0];start=region['offset']-item['offset'];require(sha(files[name][start:start+size])==digest,'installed storage drift: '+region['name'])
    require(len(x['bundle_checks'])==4 and all(b['all_match'] for b in x['bundle_checks']),'installed bundle mismatch')
    require(all(item==m['file_pins'][name] for name,item in x['files'].items()),'installed file drift')
    require(x['latches']['gp6_gp7_hex']=='4b4f444800000000','unhealthy startup/reboot latch state')
    require(x['runtime']['/sys/module/h713_hdmi_audio/parameters/period_xruns']=='0' and x['runtime']['/sys/module/h713_hdmi_v4l2/parameters/frames_rejected']=='0','runtime errors')
    require(x['filesystem']['returncode']==0 and x['services']['returncode']==0,'health collection failed')
    fs=dict(line.split(':',1) for line in x['filesystem']['stdout'].splitlines() if ':' in line)
    require(fs.get('Filesystem state','').strip()=='clean' and int(fs.get('FS Error count',fs.get('Error count','0')).strip())==0,'filesystem errors')
    require('EXT4-fs error' not in x['kernel_log']['stdout'],'ext4 error in current boot')
    require(not x['reserved_partition_holders'] and not x['reserved_partition_mounts'],'reserved partition is in use')
    config=(prior/'uboot.config').read_bytes();require(sha(config)==m['config_sha256'],'config identity mismatch')
    for setting in ['CONFIG_ENV_SIZE=0x10000','CONFIG_ENV_OFFSET=0x93d80000','CONFIG_ENV_MMC_EMMC_HW_PARTITION=0',
                    'CONFIG_ENV_IS_IN_MMC=y','CONFIG_CMD_SAVEENV=y','CONFIG_CMD_CRC32=y','CONFIG_CMD_MEMORY=y','CONFIG_CMD_MMC=y','CONFIG_CMD_GPIO=y',
                    '# CONFIG_ENV_REDUNDANT is not set','# CONFIG_CMD_HASH is not set','# CONFIG_CMD_NVEDIT_INFO is not set',
                    '# CONFIG_CMD_NVEDIT_LOAD is not set','# CONFIG_VERSION_VARIABLE is not set']:
        require(setting+'\n' in config.decode(),'unexpected config: '+setting)
    original=files['intended-environment-surrounding-192KiB.bin'][65536:131072]
    values=v.decode(original);require(v.PROBE not in values,'probe already present')
    require(original==files['active-environment-64KiB.bin'],'old environment no longer matches baseline')
    require(all(b'\n' not in value and b'\r' not in value for value in values.values()),'multiline values need a different RAM-capture protocol')
    nonce='savepath_20261031_'+secrets.token_hex(8)
    probe=dict(values);probe[v.PROBE]=nonce.encode();model=v.encode(probe)
    v.check(original,model,'probe',nonce);v.check(original,v.encode(values),'cleanup',nonce)
    output.mkdir(parents=True,mode=0o700)
    def blob(name,data):
        (output/name).write_bytes(data);(output/name).chmod(0o600)
        return dict(file=name,bytes=len(data),sha256=sha(data))
    backup=blob('environment-before.bin',original)
    protected=[]
    for item in m['protected']:
        # Copy from the fresh collection, not the older package's fixture bytes.
        name,region=next((name,meta) for name,meta in x['ranges'].items() if meta['offset']<=item['offset'] and item['offset']+item['bytes']<=meta['offset']+meta['bytes'])
        start=item['offset']-region['offset'];data=files[name][start:start+item['bytes']]
        p=blob('protected-'+item['name']+'.bin',data);p.update(name=item['name'],offset=item['offset']);protected.append(p)
    proper=files['proper-region-2MiB.bin'][:m['transaction_sectors']*512]
    p=blob('protected-proper.bin',proper);p.update(name='installed-proper',offset=0x49ac00*512);protected.append(p)
    blob('model-probe-NOT-FOR-INSTALL.bin',model);blob('model-cleanup-NOT-FOR-INSTALL.bin',v.encode(values))
    for name in ['mmc.c','uboot.config','build.inputs','width-fix.patch']:shutil.copyfile(prior/name,output/name)
    tree=ROOT/'build'/m['source_tree'];require((tree/'env/mmc.c').read_bytes()==(prior/'mmc.c').read_bytes(),'prepared MMC source drift')
    for src,dst in [('env/common.c','env-common.c'),('board/sunxi/board.c','sunxi-board.c'),('cmd/nvedit.c','nvedit.c')]:shutil.copyfile(tree/src,output/dst)
    for name in ['check-uboot-savepath.py','test-uboot-save-path.py','test-uboot-savepath-checks.py','rehearse-uboot-migration.py']:
        shutil.copyfile(ROOT/'tools/hdmi'/name,output/name)
    manifest=dict(schema='h713-savepath-preparation-v1',preparation_only=True,hardware_actions_authorized=False,
                  identity=x['identity'],nonce=nonce,probe_key=v.PROBE.decode(),
                  write_region=dict(offset=0x49ec00*512,lba='0x49ec00',sectors=128,bytes=65536,before=backup),
                  protected=protected,installed_proper_sha256=sha(proper),config_sha256=sha(config),
                  baseline_entries=len(values),capture_sha256=sha(capture.read_bytes()),
                  current_env_crc32_whole=f'{zlib.crc32(original):08x}',
                  command_constraints=['No hash/env info/env load commands: disabled in installed config',
                    'Do not use env export: it changes filesize before save',
                    'Do not use GP7 stop: it changes bootdelay in RAM',
                    'Only normal initialization fdtcontroladdr drift is permitted from the captured RAM map'],
                  proposed_warm_reboots=2,proposed_native_env_saves=2,
                  source_hashes={n:sha((output/n).read_bytes()) for n in ['mmc.c','env-common.c','sunxi-board.c','nvedit.c']})
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (output/'inventory-private.json').write_bytes(files['inventory.json'])
    (output/'ENV-ONLY-RECOVERY.txt').write_text(f'''PREPARATION ONLY. No recovery write is currently authorized.
Restore only intended environment, keeping the migrated proper installed.
Exact fresh environment-before.bin: {backup['bytes']} bytes, SHA-256 {backup['sha256']}
Whole-image CRC32: {zlib.crc32(original):08x}. Do not restore the earlier zero-filled migration preimage.
Do not run migration rollback: that also restores the old diagnostic proper.
After explicit recovery approval and identity/protected-storage preflight:
select verified eMMC user device, transfer this exact backup to RAM at 0x42000000
with exclusive UART/YMODEM ownership. Check filesize=10000 and source archive SHA-256
on the host; current proper has crc32 but no hash command. Check RAM transfer:
crc32 0x42000000 0x10000
Only after full expected CRC32 matches and all approval/identity checks pass:
mmc dev 1 0
mmc write 0x42000000 0x49ec00 0x80
mmc read 0x43000000 0x49ec00 0x80
cmp.b 0x42000000 0x43000000 0x10000
No automatic reset/retry. CRC32 is transport integrity, not cryptographic proof;
use host SHA-256, exact cmp and independent Linux storage/protected-range checks.
Never write old environment in super (0x32ec00), GPT/SPL, proper, rescue or FAT.
If unable to reach Linux/new proper, use the preserved FEL/rescue entry first,
verify its actual command capabilities, then apply the same bounded env-only recovery.
Keep PB5 lamp/fan policy safe while held at a prompt; no prolonged PB5-low hold.
''')
    (output/'README.txt').write_text('''PRIVATE PREPARATION PACKET. No reboot, native env save or hardware write performed.
Model blobs are synthetic semantic fixtures, not installable payloads. Use only
environment-before.bin for an explicitly approved env-only recovery.
Source tests execute copied U-Boot routines with fake MMC on regular host files.
The later hardware protocol uses two native env saves: temporary nonce then
cleanup, with two controlled warm entries and complete RAM/disk/protected checks.
See repository docs/uboot-savepath-validation-2026-10-31.md before any hardware action.
''')
    for p in output.iterdir():p.chmod(0o600)
    (output/'SHA256SUMS').write_text(''.join(sha(p.read_bytes())+'  '+p.name+'\n' for p in sorted(output.iterdir()) if p.is_file()))
    print(json.dumps(dict(status='PASS read-only backups validated and save-path packet prepared',boot_id=x['identity']['boot_id'],
                         cid_sha256=sha(x['identity']['cid'].encode()),environment_sha256=backup['sha256'],baseline_entries=len(values),
                         protected_regions=len(protected),write_lba='0x49ec00',write_sectors=128,nonce=nonce,hardware_write=False),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--capture',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();build(a.capture,a.output)
