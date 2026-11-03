#!/usr/bin/env python3
"""Sparse regular-file rehearsal, including short writes and recovery interruptions."""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile


def module(path):
    spec=importlib.util.spec_from_file_location('migration',path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


def fixture(engine,package,path):
    m,_=engine.load_package(package)
    with path.open('xb') as f:
        f.truncate(m['capacity_bytes'])
        for item in m['protected']:
            f.seek(item['offset']);f.write(engine.payload(package,item))
        for item in m['writes']:
            f.seek(item['offset']);f.write(item['before_data'])
        # Distinct bytes in otherwise unobserved gaps catch overbroad writes.
        for offset in [65536,0x49ac00*512-4096,0x49ec00*512-4096,0x49ec00*512+65536,0x4a0c00*512-4096]:
            reserved=[(i['offset'],i['offset']+i['bytes']) for i in m['protected']+m['writes']]
            if any(offset<end and offset+4096>start for start,end in reserved):continue
            f.seek(offset);f.write(b'UNRELATED HOST FIXTURE DATA'.ljust(4096,b'\x5a'))
        f.flush();os.fsync(f.fileno())
    return m


def data_extents(fd,size):
    offset=0
    while offset<size:
        try:
            start=os.lseek(fd,offset,os.SEEK_DATA)
        except OSError as e:
            if e.errno==6:break
            raise
        end=os.lseek(fd,start,os.SEEK_HOLE)
        yield start,min(end,size)
        offset=end


def same_outside(left,right,excluded=()):
    a=os.open(left,os.O_RDONLY);b=os.open(right,os.O_RDONLY)
    try:
        size=os.fstat(a).st_size
        assert os.fstat(b).st_size==size,'comparison size differs'
        # Union of allocated ranges verifies every potentially nonzero byte.
        for start,end in list(data_extents(a,size))+list(data_extents(b,size)):
            spans=[(start,end)]
            for lo,hi in excluded:
                spans=[part for x,y in spans for part in [(x,min(y,lo)),(max(x,hi),y)] if part[0]<part[1]]
            for x,y in spans:
                for offset in range(x,y,1024*1024):
                    n=min(1024*1024,y-offset)
                    assert os.pread(a,n,offset)==os.pread(b,n,offset),'unexpected bytes outside transaction'
    finally:
        os.close(a);os.close(b)


def rejects(function,kind=(ValueError,OSError)):
    try:function()
    except kind as error:return error
    raise AssertionError('unsafe operation accepted')


def run(package,work,engine_path=None,verbose=True):
    engine=module(engine_path or package/'uboot-migration.py')
    work.mkdir(parents=True,exist_ok=False)
    reference=work/'reference.img';m=fixture(engine,package,reference)
    spans=[(i['offset'],i['offset']+i['bytes']) for i in m['writes']]
    tests=[];counter=0
    def case(name):
        nonlocal counter
        counter+=1
        folder=work/str(counter);folder.mkdir()
        image=folder/'disk.img';fixture(engine,package,image)
        journal=folder/'journal.json'
        return image,journal
    def done(name):
        tests.append(name)
        if verbose:print('PASS',name)
    image,journal=case('normal')
    assert engine.operate(package,image,journal,'preview')['state']=='before'
    assert not journal.exists()
    assert engine.operate(package,image,journal,'install')['state']=='installed'
    assert engine.operate(package,image,journal,'preview')['state']=='after'
    same_outside(image,reference,spans)
    before_mtime=image.stat().st_mtime_ns
    assert engine.operate(package,image,journal,'install')['state']=='no-op'
    assert image.stat().st_mtime_ns==before_mtime
    assert engine.operate(package,image,journal,'rollback')['state']=='rolled-back'
    same_outside(image,reference)
    assert engine.operate(package,image,journal,'rollback')['state']=='no-op'
    done('install, read-only preview, install no-op, exact rollback and rollback no-op')
    for fault in ['prepared','environment-short','environment-readback','environment-done',
                  'proper-short','proper-readback','proper-done']:
        image,journal=case(fault)
        error=rejects(lambda:engine.operate(package,image,journal,'install',fault), (ValueError,InterruptedError))
        if fault.endswith('-short'):assert 'short write' in str(error)
        if fault.endswith('-readback'):assert 'readback mismatch' in str(error)
        # In every environment interruption, no proper bytes may have changed.
        if fault.startswith('environment') or fault=='prepared':
            proper=next(i for i in m['writes'] if i['name']=='proper')
            with image.open('rb') as f:
                f.seek(proper['offset']);assert f.read(proper['bytes'])==proper['before_data'],'proper written before environment verified'
        same_outside(image,reference,spans)
        engine.operate(package,image,journal,'rollback')
        same_outside(image,reference)
        done('interruption/short-write/readback recovery: '+fault)
    for fault in ['rollback-proper-short','rollback-proper-done',
                  'rollback-environment-short','rollback-environment-done']:
        image,journal=case(fault);engine.operate(package,image,journal,'install')
        rejects(lambda:engine.operate(package,image,journal,'rollback',fault),(ValueError,InterruptedError))
        if fault.startswith('rollback-environment'):
            proper=next(i for i in m['writes'] if i['name']=='proper')
            with image.open('rb') as f:
                f.seek(proper['offset']);assert f.read(proper['bytes'])==proper['before_data'],'environment restored before old proper'
        engine.operate(package,image,journal,'rollback');same_outside(image,reference)
        done('resumable rollback: '+fault)
    for item in m['protected']:
        image,journal=case(item['name'])
        with image.open('r+b') as f:
            f.seek(item['offset']);f.write(bytes([engine.read_at(f.fileno(),item['offset'],1)[0]^1]))
        snapshot=work/f'changed-{counter}.img';fixture(engine,package,snapshot)
        with snapshot.open('r+b') as f:
            f.seek(item['offset']);f.write(bytes([engine.read_at(f.fileno(),item['offset'],1)[0]^1]))
        rejects(lambda:engine.operate(package,image,journal,'install'))
        assert not journal.exists();same_outside(image,snapshot)
        done('refuse protected drift: '+item['name'])
    for item in m['writes']:
        image,journal=case(item['name'])
        with image.open('r+b') as f:
            f.seek(item['offset']);f.write(b'WRONG PREIMAGE')
        rejects(lambda:engine.operate(package,image,journal,'install'))
        assert not journal.exists()
        done('refuse unknown preimage: '+item['name'])
    image,journal=case('capacity')
    with image.open('r+b') as f:f.truncate(m['capacity_bytes']-512)
    error=rejects(lambda:engine.operate(package,image,journal,'install'));assert not journal.exists()
    assert 'capacity mismatch' in str(error)
    done('refuse wrong capacity')
    image,journal=case('locked')
    with image.open('r+b') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        rejects(lambda:engine.operate(package,image,journal,'install'),(BlockingIOError,))
    assert not journal.exists();same_outside(image,reference)
    done('refuse concurrent image transaction')
    image,journal=case('journal')
    rejects(lambda:engine.operate(package,image,journal,'rollback'))
    rejects(lambda:engine.operate(package,image,journal,'install','prepared'),(InterruptedError,))
    state=json.loads(journal.read_text());state['package']='wrong';journal.write_text(json.dumps(state))
    rejects(lambda:engine.operate(package,image,journal,'rollback'));same_outside(image,reference)
    done('refuse absent/wrong-package recovery journal')
    image,journal=case('wrong image journal')
    rejects(lambda:engine.operate(package,image,journal,'install','prepared'),(InterruptedError,))
    other=work/'other.img';fixture(engine,package,other)
    rejects(lambda:engine.operate(package,other,journal,'rollback'));same_outside(other,reference)
    done('refuse journal for another image inode')
    image,journal=case('unjournaled changes')
    rejects(lambda:engine.operate(package,image,journal,'install','environment-done'),(InterruptedError,))
    proper=next(i for i in m['writes'] if i['name']=='proper')
    with image.open('r+b') as f:f.seek(proper['offset']);f.write(b'WRONG')
    rejects(lambda:engine.operate(package,image,journal,'rollback'))
    done('refuse rollback bytes outside durable intent')
    link=work/'link.img';link.symlink_to(reference)
    rejects(lambda:engine.operate(package,link,work/'link.json','install'))
    error=rejects(lambda:engine.operate(package,Path('/dev/null'),work/'device.json','preview'))
    assert 'only regular host image' in str(error)
    done('refuse symlink and device inputs')
    result=subprocess.run(['python3',str(engine_path or package/'uboot-migration.py')],capture_output=True)
    assert result.returncode!=0
    done('no implicit action or target')
    # Payload and manifest failures are tested without altering the original package.
    broken=work/'broken';broken.mkdir()
    for file in package.iterdir():
        if file.is_file():os.link(file,broken/file.name)
    name=m['writes'][0]['after']['file']
    (broken/name).unlink();(broken/name).write_bytes(b'corrupt')
    image,journal=case('payload')
    error=rejects(lambda:engine.operate(broken,image,journal,'install'));same_outside(image,reference)
    assert 'payload identity mismatch' in str(error)
    done('refuse corrupt payload')
    (broken/name).unlink();os.link(package/name,broken/name)
    manifest=json.loads((package/'manifest.json').read_text())
    manifest['writes'][1]['offset']=manifest['writes'][0]['offset']
    (broken/'manifest.json').unlink();(broken/'manifest.json').write_text(json.dumps(manifest))
    error=rejects(lambda:engine.operate(broken,image,journal,'install'));same_outside(image,reference)
    assert 'overlapping ranges' in str(error)
    done('refuse overlapping transaction ranges')
    result=dict(result='PASS',cases=len(tests),tests=tests,regular_sparse_images_only=True,
                hardware_writes_or_resets_tested=False,live_snapshot_package=bool(m.get('finalized')),
                storage_fixture='fresh captured GPT/boot bytes' if m.get('finalized') else 'historical inputs and synthetic markers',
                capacity_bytes=m['capacity_bytes'])
    (work/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def mutations(package,work):
    source=(package/'uboot-migration.py').read_text()
    variants={
        'proper before environment':("for item in m['writes']:\n                name", "for item in reversed(m['writes']):\n                name"),
        'short writes accepted':("require(written == len(data), 'short write; rollback required')",'pass'),
        'readback ignored':("require(read_at(fd, start, len(data)) == data, 'readback mismatch; rollback required')",'pass'),
        'protected ranges unchecked':('verify_protected(fd, m)','None'),
        'capacity unchecked':("require(info.st_size == m['capacity_bytes'], 'image capacity mismatch')",'pass'),
        'preimage unchecked':("require(before, 'preimage mismatch; use reviewed rollback for interruption')",'pass'),
        'payload unchecked':("require(len(data) == item['bytes'] and sha(data) == item['sha256'], 'payload identity mismatch')",'pass'),
        'journal identity unchecked':("require(state['package'] == package_id and state['image'] == identity, 'journal identity mismatch')",'pass'),
        'write intent unchecked':("require(current[item['name']] == item['before_data'], 'unexpected bytes outside journaled write intent')",'pass'),
        'device guard removed':("require(stat.S_ISREG(info.st_mode), 'only regular host image files are supported; hardware disabled')",'pass'),
        'overlap unchecked':("require(all(end <= a or start >= b for a,b in spans), 'overlapping ranges')",'pass'),
        'rollback order reversed':("for item in reversed(m['writes']):", "for item in m['writes']:")
        ,'image lock removed':('fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)','None')
        ,'intent not recorded':("state['phase'] = name + '-intent'; save_state(journal, state)","save_state(journal, state)")
    }
    work.mkdir(parents=True,exist_ok=False)
    caught=[]
    for index,(name,(before,after)) in enumerate(variants.items()):
        assert before in source,name
        mutant=work/f'mutant-{index}.py';mutant.write_text(source.replace(before,after))
        try:run(package,work/f'case-{index}',mutant,False)
        except (AssertionError,ValueError,OSError,InterruptedError):
            caught.append(name);print('CAUGHT',name)
        else:raise AssertionError('mutation survived: '+name)
    return dict(result='PASS',caught=caught,count=len(caught))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package',required=True,type=Path);p.add_argument('--work',required=True,type=Path)
    p.add_argument('--mutations',action='store_true');a=p.parse_args()
    result=mutations(a.package,a.work) if a.mutations else run(a.package,a.work)
    print(json.dumps(result,indent=2))
