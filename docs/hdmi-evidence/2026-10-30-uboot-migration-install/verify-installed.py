#!/usr/bin/env python3
"""Independent read-only post-install verification; run via python3 -B - stdin."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import struct
import time
import zlib


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def verify(package,expected_boot_id):
    started=time.monotonic()
    engine=load('h713_migration',package/'uboot-migration.py')
    live=load('h713_migration_live',package/'uboot-migration-live.py')
    manifest,identity=engine.load_package(package)
    journal=json.loads((package/'transaction.json').read_text())
    completion=json.loads((package/'install-exit.json').read_text())
    engine.require(completion['exit_code']==0,'installer did not exit successfully')
    engine.require(journal['phase']=='installed' and journal['package']==identity,'transaction not committed for this package')
    engine.require(completion['manifest_sha256']==identity and completion['expected_boot_id']==expected_boot_id,'completion identity differs')
    fd=os.open('/dev/mmcblk0',os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        state=live.check_board(manifest,expected_boot_id,fd)
        info=os.fstat(fd)
        engine.require(journal['image']==[info.st_dev,info.st_ino,manifest['capacity_bytes']],'journal device identity differs')
        writes=[]
        for item in manifest['writes']:
            data=engine.read_at(fd,item['offset'],item['bytes'])
            engine.require(data==item['after_data'],'installed write region mismatch: '+item['name'])
            row=dict(name=item['name'],offset=item['offset'],bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),matches=True,direct_read=True)
            if item['name']=='environment':
                row['crc_valid']=struct.unpack('<I',data[:4])[0]==zlib.crc32(data[4:])
                engine.require(row['crc_valid'],'migrated environment CRC invalid')
            if item['name']=='proper':
                magic,size=struct.unpack('>II',data[:8])
                engine.require(magic==0xd00dfeed and size==manifest['candidate_fit_bytes'],'candidate FIT header mismatch')
                row['fit_bytes']=size
            writes.append(row)
        protected=[];keep={}
        keep_names={'disk-prefix-including-GPT-and-SPL','disk-suffix-including-backup-GPT',
                    'active-environment','rescue-full-region','proper-region-tail',
                    'intended-environment-prefix','intended-environment-suffix'}
        for item in manifest['protected']:
            data=engine.read_at(fd,item['offset'],item['bytes'])
            actual=hashlib.sha256(data).hexdigest()
            engine.require(actual==item['sha256'],'protected range mismatch: '+item['name'])
            protected.append(dict(name=item['name'],offset=item['offset'],bytes=len(data),sha256=actual,unchanged=True,direct_read=True))
            if item['name'] in keep_names:keep[item['name']]=data
        proper=next(i for i in manifest['writes'] if i['name']=='proper')
        environment=next(i for i in manifest['writes'] if i['name']=='environment')
        expected_proper=proper['after_data']+keep['proper-region-tail']
        actual_proper=engine.read_at(fd,proper['offset'],len(expected_proper))
        engine.require(actual_proper==expected_proper,'full surrounding proper region differs')
        expected_env=keep['intended-environment-prefix']+environment['after_data']+keep['intended-environment-suffix']
        actual_env=engine.read_at(fd,environment['offset']-65536,len(expected_env))
        engine.require(actual_env==expected_env,'full surrounding environment region differs')
        bundles=[]
        for directory in ['/usr/lib/h713-hdmi','/usr/lib/h713-hdmi-health','/usr/lib/h713-hdmi-video','/usr/lib/h713-hdmi-speaker']:
            root=Path(directory);count=0
            for line in (root/'SHA256SUMS').read_text().splitlines():
                expected,name=line.split('  ',1)
                engine.require(not Path(name).is_absolute() and '..' not in Path(name).parts,'unsafe bundle entry')
                engine.require(hashlib.sha256((root/name).read_bytes()).hexdigest()==expected,'installed bundle mismatch: '+name)
                count+=1
            bundles.append(dict(path=str(root/'SHA256SUMS'),entries=count,all_match=True))
        engine.require(Path('/proc/sys/kernel/random/boot_id').read_text().strip()==expected_boot_id,'boot changed during verification')
        prefix=keep['disk-prefix-including-GPT-and-SPL'];rescue=keep['rescue-full-region']
        rescue_magic,rescue_size=struct.unpack('>II',rescue[:8]);engine.require(rescue_magic==0xd00dfeed,'rescue FIT magic differs')
        old_env=keep['active-environment']
        return dict(result='PASS independently verified installed migration',boot_id=expected_boot_id,
                    manifest_sha256=identity,journal_phase=journal['phase'],installer_exit_code=completion['exit_code'],
                    writes=writes,protected=protected,
                    surrounding_proper_region_sha256=hashlib.sha256(actual_proper).hexdigest(),
                    surrounding_environment_region_sha256=hashlib.sha256(actual_env).hexdigest(),
                    spl_sha256=hashlib.sha256(prefix[0x10*512:0x10*512+32768]).hexdigest(),
                    rescue_fit_bytes=rescue_size,rescue_fit_sha256=hashlib.sha256(rescue[:rescue_size]).hexdigest(),
                    old_environment_crc_valid=struct.unpack('<I',old_env[:4])[0]==zlib.crc32(old_env[4:]),
                    old_and_new_environment_identical=old_env==environment['after_data'],
                    bundle_checks=bundles,live_state=state,services_and_start_identities_unchanged=True,
                    runtime_counters_and_signal_unchanged=True,latches_unchanged=True,calibration_unchanged=True,
                    verification_storage_writes=False,reboot=False,monotonic_duration_seconds=time.monotonic()-started)
    finally:os.close(fd)
