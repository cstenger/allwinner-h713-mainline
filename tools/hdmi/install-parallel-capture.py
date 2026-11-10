#!/usr/bin/env python3
"""Install only the two parallel-start unit pairs and backend manifest."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import uuid

spec=importlib.util.spec_from_file_location('guard_io',Path(__file__).with_name('sync-shutdown-guard.py'))
io=importlib.util.module_from_spec(spec);spec.loader.exec_module(io)
BACKEND=io.BACKEND
TARGETS=('etc/systemd/system/h713-hdmi-prepare.service',BACKEND+'/h713-hdmi-prepare.service',
         BACKEND+'/h713-hdmi-capture.service','etc/systemd/system/h713-hdmi-capture.service',
         BACKEND+'/SHA256SUMS')
CAPTURE_OLD='a0690a5218831fefa5a1f9980e47edd0e2ec3e9b6dfca3e54e87fc5acd4ff36d'
CAPTURE_NEW='41c45dee2ca8b14cf32f409f31743081a64b9b7566a3076860ca39124820eea5'
PREPARE_NEW='64d4ecd6f4ec570a89d7cd87bb98820e99b05f8ae358d3ef89522a0ee3993b28'
SCRIPTS={'mips-shell.py':'53320e85a66d48c7f9eb93b070770205f9012eb278f959992be4782b6ecfb6c7',
         'h713-hdmi-session.py':'e8b0a1c327778d25eb7e1fcdcf5465aa04985bfd8ea20c47c2dd5048ebcb5739'}
PREFIX='parallel-capture-'
ATTRS={'mode':0o644,'uid':0,'gid':0}


def sha(data):return hashlib.sha256(data).hexdigest() if data is not None else None


def identity(root,boot):
    io.identity(root)
    if (root/'proc/sys/kernel/random/boot_id').read_text().strip()!=boot:
        raise RuntimeError('boot ID changed')
    for name,want in SCRIPTS.items():
        if sha(io.path(root,BACKEND+'/'+name).read_bytes())!=want:raise RuntimeError('stage-1 script changed: '+name)
    for name in ('h713-hdmi-capture.service','h713-hdmi-prepare.service'):
        for parent in ('etc/systemd/system','run/systemd/system'):
            dropin=root/parent/(name+'.d')
            if dropin.exists() or dropin.is_symlink():raise RuntimeError('unreviewed unit drop-in: '+str(dropin))
        for path in (root/'etc/systemd/system/multi-user.target.wants/h713-hdmi-prepare.service',
                     root/'run/systemd/system/multi-user.target.wants/h713-hdmi-prepare.service'):
            if path.exists() or path.is_symlink():raise RuntimeError('prepare must not be independently enabled')


def current(root):
    result=[]
    for name in TARGETS:
        path=io.path(root,name)
        if path.exists():
            if io.metadata(path)!=ATTRS:raise RuntimeError('unexpected file metadata: '+name)
            result.append(path.read_bytes())
        else:result.append(None)
    return result


def next_manifest(data):
    entries=io.table(data)
    names={str(Path(name)):name for name in entries}
    if len(names)!=len(entries) or 'h713-hdmi-prepare.service' in names:
        raise RuntimeError('ambiguous/preexisting prepare manifest entry')
    name=names.get('h713-hdmi-capture.service')
    if not name or entries[name]!=CAPTURE_OLD:raise RuntimeError('capture manifest differs')
    lines=data.decode().splitlines(keepends=True)
    matches=[i for i,line in enumerate(lines) if line.rstrip('\r\n')==CAPTURE_OLD+'  '+name]
    if len(matches)!=1:raise RuntimeError('capture manifest entry ambiguous')
    index=matches[0];lines[index]=lines[index].replace(CAPTURE_OLD,CAPTURE_NEW,1)
    result=''.join(lines)
    if not result.endswith('\n'):result+='\n'
    return (result+PREPARE_NEW+'  ./h713-hdmi-prepare.service\n').encode()


def atomic(path,data,before):
    if before is not None:
        return io.atomic(path,data,ATTRS,before)
    fd,temp=tempfile.mkstemp(prefix='.parallel-capture-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data);os.fchmod(stream.fileno(),0o644)
            if os.geteuid()==0:os.fchown(stream.fileno(),0,0)
            stream.flush();os.fsync(stream.fileno())
        if Path(temp).read_bytes()!=data:raise RuntimeError('new unit readback failed')
        os.link(temp,path)  # no overwrite if a competing file appeared
        io.fsync_dir(path.parent)
    finally:Path(temp).unlink(missing_ok=True)


def install(root,bundle,boot,manifest,apply=False):
    identity(root,boot);fd=os.open(io.path(root,io.STATE),os.O_RDONLY|os.O_DIRECTORY)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if list((root/io.STATE).glob('*/INCOMPLETE')):raise RuntimeError('incomplete transaction exists')
        before=current(root)
        if list(map(sha,before))!=[None,None,CAPTURE_OLD,CAPTURE_OLD,manifest]:
            raise RuntimeError('unit files/manifest differ from stage-1 baseline')
        io.verify_generation(root,before[4])
        after=[io.path(bundle,name).read_bytes() for name in TARGETS[:4]]+[next_manifest(before[4])]
        if list(map(sha,after[:4]))!=[PREPARE_NEW,PREPARE_NEW,CAPTURE_NEW,CAPTURE_NEW]:
            raise RuntimeError('unexpected unit payload')
        record={'schema':'h713-parallel-capture-install-v1','targets':list(TARGETS),
                'before':list(map(sha,before)),'after':list(map(sha,after)),'boot_id':boot}
        if not apply:return {'phase':'would-install','record':record}
        backup=root/io.STATE/(PREFIX+uuid.uuid4().hex);backup.mkdir(mode=0o700)
        for i,data in enumerate(before):
            if data is not None:io.save(backup/str(i),data)
        io.save(backup/'record.json',(json.dumps(record,indent=2)+'\n').encode())
        io.save(backup/'INCOMPLETE',b'Inspect or rollback before reload/shutdown.\n')
        io.fsync_dir(backup);io.fsync_dir(backup.parent)
        for i,name in enumerate(TARGETS):
            identity(root,boot);atomic(io.path(root,name),after[i],record['before'][i])
        if current(root)!=after:raise RuntimeError('installation readback failed')
        io.verify_generation(root,after[4])
        io.save(backup/'COMMITTED',b'parallel units installed; daemon-reload still required\n')
        (backup/'INCOMPLETE').unlink();io.fsync_dir(backup)
        return {'phase':'installed','backup':str(backup),'record':record,'services_restarted':False}
    finally:os.close(fd)


def rollback(root,backup,boot,apply=False):
    identity(root,boot)
    if backup.parent!=root/io.STATE or not backup.name.startswith(PREFIX) or backup.is_symlink():
        raise RuntimeError('invalid rollback location')
    fd=os.open(io.path(root,io.STATE),os.O_RDONLY|os.O_DIRECTORY)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        relative=str(backup.relative_to(root))
        record=json.loads(io.path(root,relative+'/record.json').read_text())
        if (record['schema']!='h713-parallel-capture-install-v1' or record['targets']!=list(TARGETS)
                or record['before'][:4]!=[None,None,CAPTURE_OLD,CAPTURE_OLD]
                or record['after'][:4]!=[PREPARE_NEW,PREPARE_NEW,CAPTURE_NEW,CAPTURE_NEW]):
            raise RuntimeError('rollback scope differs')
        before=[None,None]+[io.path(root,relative+'/'+str(i)).read_bytes() for i in range(2,5)]
        if list(map(sha,before))!=record['before'] or sha(next_manifest(before[4]))!=record['after'][4]:
            raise RuntimeError('rollback backup corrupted')
        now=current(root)
        if any(sha(data) not in (record['before'][i],record['after'][i]) for i,data in enumerate(now)):
            raise RuntimeError('foreign unit changes; refusing rollback')
        for name,digest in io.table(before[4]).items():
            if str(Path(name))!='h713-hdmi-capture.service' and sha(io.path(root,BACKEND+'/'+name).read_bytes())!=digest:
                raise RuntimeError('unrelated backend changed')
        if not apply:return {'phase':'would-rollback','backup':str(backup)}
        for i in (2,3,0,1,4):
            identity(root,boot);path=io.path(root,TARGETS[i])
            if before[i] is None:
                if path.exists():
                    if sha(path.read_bytes())!=record['after'][i]:raise RuntimeError('new unit changed')
                    path.unlink();io.fsync_dir(path.parent)
            else:io.atomic(path,before[i],ATTRS,sha(now[i]))
        io.verify_generation(root,before[4])
        if not (backup/'ROLLED_BACK').exists():io.save(backup/'ROLLED_BACK',b'original units restored; daemon-reload required\n')
        (backup/'INCOMPLETE').unlink(missing_ok=True);io.fsync_dir(backup)
        return {'phase':'rolled-back','backup':str(backup),'services_restarted':False}
    finally:os.close(fd)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('/'));parser.add_argument('--bundle',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--boot-id',required=True);parser.add_argument('--before-manifest-sha')
    parser.add_argument('--rollback',type=Path);parser.add_argument('--apply',action='store_true')
    args=parser.parse_args();root=args.root.resolve()
    if args.rollback:result=rollback(root,args.rollback.absolute(),args.boot_id,args.apply)
    else:
        if not args.before_manifest_sha:parser.error('--before-manifest-sha is required')
        result=install(root,args.bundle.resolve(),args.boot_id,args.before_manifest_sha,args.apply)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
