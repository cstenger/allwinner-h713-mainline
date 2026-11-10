#!/usr/bin/env python3
"""Turn verified release boot files into a deterministic 32 MiB FAT image.

Writes a new regular file only. Never opens a board, block device or mount.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(release,output):
    meta=json.loads((release/'release.json').read_text())
    epoch=meta['source_date_epoch']
    pins={name:sha for sha,name in (line.split('  ',1) for line in (release/'SHA256SUMS').read_text().splitlines())}
    if digest(release/'release.json')!=pins['release.json'] or digest(release/'boot.tar')!=pins['boot.tar']:
        raise ValueError('release identity changed')
    if output.exists() or output.is_symlink():raise ValueError('output must be new')
    env=dict(os.environ,SOURCE_DATE_EPOCH=str(epoch),TZ='UTC',LC_ALL='C.UTF-8')
    env['MTOOLSRC']='/dev/null'
    env.pop('MTOOLS_DATE_STRING',None)
    with tempfile.TemporaryDirectory() as temporary:
        tree=Path(temporary)
        with tarfile.open(release/'boot.tar') as archive:
            members=archive.getmembers()
            if {m.name for m in members}!=set(meta['boot_files']):raise ValueError('boot archive manifest mismatch')
            for member in members:
                name=Path(member.name)
                if name.is_absolute() or '..' in name.parts or not member.isfile() or member.size>32*1024*1024:
                    raise ValueError('unsafe boot archive')
                data=archive.extractfile(member).read();pin=meta['boot_files'][member.name]
                if hashlib.sha256(data).hexdigest()!=pin['sha256'] or len(data)!=pin['bytes']:
                    raise ValueError('boot asset changed: '+member.name)
                path=tree/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
                path.chmod(0o644);os.utime(path,(epoch,epoch))
        with output.open('xb') as f:f.truncate(32*1024*1024)
        subprocess.run(['mformat','-i',str(output),'-v','H713BOOT','-N','0x71300001',
                        '-h','64','-s','32','-T','65536','::'],env=env,check=True)
        for directory in sorted(p for p in tree.rglob('*') if p.is_dir()):
            subprocess.run(['mmd','-i',str(output),'::/'+str(directory.relative_to(tree))],env=env,check=True)
        for file in sorted(p for p in tree.rglob('*') if p.is_file()):
            subprocess.run(['mcopy','-m','-i',str(output),str(file),'::/'+str(file.relative_to(tree))],env=env,check=True)
    result=dict(schema='h713-boot-filesystem-v1',image_sha256=digest(output),bytes=output.stat().st_size,
                boot_tar_sha256=pins['boot.tar'],epoch=epoch,hardware_written=False)
    output.with_suffix(output.suffix+'.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--release',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();print(json.dumps(build(a.release.resolve(),a.output.resolve()),indent=2))
