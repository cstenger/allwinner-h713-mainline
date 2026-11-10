#!/usr/bin/env python3
"""Guarded shared-startup/health-unit update; no service start or RTC access.

Run from its dedicated bundle. --dry-run validates without mutations.
--install backs up the old script/manifest and activates the FAT script last.
--rollback BACKUP restores only a verified transaction's files.
"""
import argparse,hashlib,json,os,shutil,subprocess,time,uuid
from pathlib import Path

HEALTH='usr/lib/h713-hdmi-health'
UNIT='etc/systemd/system/h713-hdmi-health-ack.service'
BACKEND='usr/lib/h713-hdmi'
STATE='var/lib/h713-hdmi-startup'
FAT='mnt/boot'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def sums(path):
    result={}
    for line in path.read_text().splitlines():
        digest,name=line.split('  ',1)
        if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):raise RuntimeError('bad checksum')
        if name in result or Path(name).is_absolute() or '..' in Path(name).parts:raise RuntimeError('unsafe manifest path')
        result[name]=digest
    return result

def verify(directory):
    table=sums(directory/'SHA256SUMS')
    for name,digest in table.items():
        if sha(directory/name)!=digest:raise RuntimeError('checksum mismatch: '+name)
    return table

def sync_directory(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)

def atomic(path,data):
    tmp=path.with_name(path.name+'.shared-new')
    with tmp.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    if tmp.read_bytes()!=data:raise RuntimeError('staging mismatch')
    os.replace(tmp,path)
    sync_directory(path.parent)

def inspect(root,bundle):
    root=Path(root);bundle=Path(bundle);verify(bundle)
    m=json.loads((bundle/'manifest.json').read_text())
    if m['schema']!='h713-shared-startup-update-v1':raise RuntimeError('unknown update schema')
    i=root/BACKEND;fat=root/FAT;state=root/STATE
    table=verify(i)
    for name in ('h713-hdmi.scr','h713-hdmi.cmd'):
        if name not in table:raise RuntimeError('startup file missing from installed manifest')
        if sha(i/name)!=m['previous'][name]:raise RuntimeError('unexpected installed '+name)
        if sha(bundle/name)!=m['candidate'][name]:raise RuntimeError('candidate mismatch')
    if (fat/'h713-hdmi.scr').read_bytes()!=(i/'h713-hdmi.scr').read_bytes():raise RuntimeError('FAT/installed script differ')
    if sha(fat/'h713-kernel.fit')!=m['fit_sha256']:raise RuntimeError('kernel changed')
    pin=(state/'kernel.sha256').read_text().split()
    if len(pin)!=2 or pin[0]!=m['fit_sha256'] or pin[1]!='/mnt/boot/h713-kernel.fit':raise RuntimeError('kernel pin differs')
    if os.path.lexists(root/HEALTH) or os.path.lexists(root/UNIT):raise RuntimeError('health integration already exists; refusing overwrite')
    if (root/HEALTH).with_name('.h713-hdmi-health.new').exists():raise RuntimeError('unfinished health staging; inspect before retry')
    for path in (fat/'h713-hdmi.scr',i/'h713-hdmi.scr',i/'h713-hdmi.cmd',i/'SHA256SUMS'):
        if path.is_symlink():raise RuntimeError('unexpected symlink: '+str(path))
        if path.with_name(path.name+'.shared-new').exists():raise RuntimeError('unfinished staged file; inspect before retry')
    if any((state).glob('shared-*/INCOMPLETE')):raise RuntimeError('incomplete prior update; rollback before retry')
    return m,table

def install(root,bundle,control,dry_run=False):
    root=Path(root);bundle=Path(bundle);m,table=inspect(root,bundle)
    if dry_run:return {'dry_run':True,'would_install':m['candidate'],'starts_services':False,'rtc_writes':False}
    backup=root/STATE/('shared-'+time.strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]);backup.mkdir()
    (backup/'INCOMPLETE').write_text('Do not reboot until install or rollback completes.\n')
    for name in ('h713-hdmi.scr','h713-hdmi.cmd','SHA256SUMS'):shutil.copyfile(root/BACKEND/name,backup/name)
    shutil.copyfile(root/FAT/'h713-hdmi.scr',backup/'boot-script')
    record={'manifest':m,'old_sha256':{p.name:sha(p) for p in backup.iterdir() if p.name!='INCOMPLETE'}}
    (backup/'record.json').write_text(json.dumps(record,indent=2)+'\n')
    for p in backup.iterdir():
        with p.open('rb') as f:os.fsync(f.fileno())
    sync_directory(backup);sync_directory(backup.parent)
    try:
        staged=(root/HEALTH).with_name('.h713-hdmi-health.new')
        shutil.copytree(bundle,staged);verify(staged)
        for path in staged.rglob('*'):
            if path.is_file():
                with path.open('rb') as f:os.fsync(f.fileno())
        sync_directory(staged);os.replace(staged,root/HEALTH);sync_directory((root/HEALTH).parent)
        atomic(root/UNIT,(bundle/'h713-hdmi-health-ack.service').read_bytes())
        control(['daemon-reload']);control(['enable','h713-hdmi-health-ack.service'])  # never --now
        wants=(root/UNIT).parent/'multi-user.target.wants'
        if wants.exists():sync_directory(wants)
        sync_directory((root/UNIT).parent)
        for name in ('h713-hdmi.scr','h713-hdmi.cmd'):
            atomic(root/BACKEND/name,(bundle/name).read_bytes());table[name]=sha(bundle/name)
        data=''.join(v+'  '+k+'\n' for k,v in table.items()).encode()
        atomic(root/BACKEND/'SHA256SUMS',data);verify(root/BACKEND)
        # Activation LAST: health unit enabled, installed copy and manifest verified.
        atomic(root/FAT/'h713-hdmi.scr',(bundle/'h713-hdmi.scr').read_bytes())
        if sha(root/FAT/'h713-hdmi.scr')!=m['candidate']['h713-hdmi.scr']:raise RuntimeError('FAT verification failed')
        (backup/'INCOMPLETE').unlink();(backup/'COMMITTED').write_text('shared startup installed; not started\n')
        return {'installed':True,'backup':str(backup),'starts_services':False,'rtc_writes':False}
    except BaseException:
        # Keep a visible transaction marker. Caller must inspect/rollback; never reboot automatically.
        raise

def rollback(root,backup,control,dry_run=False):
    root=Path(root);backup=Path(backup)
    if backup.parent.resolve()!=(root/STATE).resolve() or not backup.name.startswith('shared-'):raise RuntimeError('invalid backup path')
    record=json.loads((backup/'record.json').read_text());m=record['manifest']
    for name,digest in record['old_sha256'].items():
        if name not in ('h713-hdmi.scr','h713-hdmi.cmd','SHA256SUMS','boot-script') or sha(backup/name)!=digest:raise RuntimeError('backup verification failed')
    if set(record['old_sha256'])!={'h713-hdmi.scr','h713-hdmi.cmd','SHA256SUMS','boot-script'}:raise RuntimeError('incomplete backup')
    for name in ('h713-hdmi.scr','h713-hdmi.cmd'):
        if sha(root/BACKEND/name) not in (m['previous'][name],m['candidate'][name]):raise RuntimeError('foreign installed startup file')
    for name,digest in sums(backup/'SHA256SUMS').items():
        if name not in ('h713-hdmi.scr','h713-hdmi.cmd') and sha(root/BACKEND/name)!=digest:raise RuntimeError('unrelated backend file changed')
    if sha(root/FAT/'h713-hdmi.scr') not in (m['previous']['h713-hdmi.scr'],m['candidate']['h713-hdmi.scr']):raise RuntimeError('foreign boot script')
    if (root/HEALTH).exists():
        verify(root/HEALTH)
        if json.loads((root/HEALTH/'manifest.json').read_text())!=m:raise RuntimeError('foreign health generation')
    if (root/UNIT).exists() and (root/UNIT).read_bytes()!=(root/HEALTH/'h713-hdmi-health-ack.service').read_bytes():raise RuntimeError('foreign health unit')
    if dry_run:return {'dry_run':True,'would_restore':str(backup)}
    if (root/UNIT).exists():control(['disable','--now','h713-hdmi-health-ack.service']) # no ExecStop/RTC access
    for name in ('h713-hdmi.scr','h713-hdmi.cmd','SHA256SUMS'):
        # Remove only our unused staging file, if a previous transaction was interrupted.
        tmp=(root/BACKEND/name).with_name(name+'.shared-new')
        if tmp.exists():tmp.unlink()
        atomic(root/BACKEND/name,(backup/name).read_bytes())
    tmp=(root/FAT/'h713-hdmi.scr').with_name('h713-hdmi.scr.shared-new')
    if tmp.exists():tmp.unlink()
    atomic(root/FAT/'h713-hdmi.scr',(backup/'boot-script').read_bytes())
    (root/UNIT).with_name((root/UNIT).name+'.shared-new').unlink(missing_ok=True)
    (root/UNIT).unlink(missing_ok=True)
    if (root/HEALTH).exists():shutil.rmtree(root/HEALTH)
    staged=(root/HEALTH).with_name('.h713-hdmi-health.new')
    if staged.exists():shutil.rmtree(staged)
    control(['daemon-reload']);verify(root/BACKEND)
    (backup/'INCOMPLETE').unlink(missing_ok=True);(backup/'ROLLED_BACK').write_text('restored; cold cycle required\n')
    return {'rolled_back':True,'cold_cycle_required':True}

def main():
    parser=argparse.ArgumentParser(description=__doc__);group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--dry-run',action='store_true');group.add_argument('--install',action='store_true');group.add_argument('--rollback',type=Path)
    a=parser.parse_args();root=Path('/');bundle=Path(__file__).resolve().parent
    if os.geteuid()!=0 or os.uname().release!='6.18.38':raise RuntimeError('root/production kernel required')
    if b'HY200 QZ713DF_A1' not in Path('/proc/device-tree/model').read_bytes():raise RuntimeError('wrong board')
    # Do not mount in dry-run. Operator must explicitly mount the recorded boot FAT first.
    source=subprocess.run(['findmnt','-n','-o','SOURCE','/mnt/boot'],capture_output=True,text=True,check=True).stdout.strip()
    if source!='/dev/mmcblk0p2':raise RuntimeError('boot FAT not mounted from expected partition')
    def control(args):subprocess.run(['systemctl']+args,check=True,timeout=30)
    result=rollback(root,a.rollback,control) if a.rollback else install(root,bundle,control,a.dry_run)
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
