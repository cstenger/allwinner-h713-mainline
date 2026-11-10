#!/usr/bin/env python3
"""Guarded U-Boot migration. Live access requires a finalized package and explicit mode."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(value, reason):
    if not value:
        raise ValueError(reason)


def payload(base, item):
    name = item['file']
    require(Path(name).name == name, 'payload path must be a basename')
    path = base / name
    require(not path.is_symlink() and path.is_file(), 'regular payload required')
    data = path.read_bytes()
    require(len(data) == item['bytes'] and sha(data) == item['sha256'], 'payload identity mismatch')
    return data


def load_package(base):
    raw = (base / 'manifest.json').read_bytes()
    m = json.loads(raw)
    require(m['schema'] == 1 and (m['offline_only'] is True or m.get('finalized') is True), 'supported migration package required')
    for name,digest in m.get('tool_hashes',{}).items():
        require(Path(name).name==name and sha((base/name).read_bytes())==digest,'packaged tool identity mismatch')
    require(m['sector_bytes'] == 512, 'unsupported sector size')
    require([x['name'] for x in m['writes']] == ['environment', 'proper'], 'environment must be staged first')
    regions = []
    for item in m['writes']:
        for key in ['before', 'after']:
            item[key + '_data'] = payload(base, item[key])
        require(len(item['before_data']) == len(item['after_data']), 'extent size mismatch')
        item['bytes'] = len(item['before_data'])
        require(item['bytes'] > 0 and item['bytes'] % 512 == 0, 'unaligned write size')
        regions.append(item)
    for item in m['protected']:
        require(item['bytes'] > 0, 'empty protected range')
        regions.append(item)
    spans = []
    for item in regions:
        start = item['offset']; end = start + item['bytes']
        require(start >= 0 and start % 512 == 0 and end <= m['capacity_bytes'], 'range outside image')
        require(all(end <= a or start >= b for a,b in spans), 'overlapping ranges')
        spans.append((start, end))
    return m, sha(raw)


def read_at(fd, start, size):
    if stat.S_ISBLK(os.fstat(fd).st_mode):
        require(start%512==0 and size%512==0,'unaligned direct block read')
        result=subprocess.run(['dd','if=/dev/mmcblk0','iflag=direct','bs=512',
                               'skip='+str(start//512),'count='+str(size//512),'status=none'],
                              capture_output=True,check=True,timeout=30)
        data=result.stdout
    else:
        data = os.pread(fd, size, start)
    require(len(data) == size, 'short read')
    return data


def verify_protected(fd, manifest):
    for item in manifest['protected']:
        require(sha(read_at(fd, item['offset'], item['bytes'])) == item['sha256'],
                'protected range changed: ' + item['name'])


def save_state(path, state):
    # Journal intent is durable before the first byte of the corresponding write.
    descriptor, name = tempfile.mkstemp(prefix=path.name+'.', suffix='.tmp', dir=path.parent)
    temporary = Path(name)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(state, stream, indent=2); stream.write('\n')
        stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def write_verified(fd, item, data, fault=None):
    start = item['offset']
    if fault == 'short':
        # Rehearsal only: emulate storage reporting a short write.
        written = os.pwrite(fd, data[:max(1, len(data)//2)], start)
    else:
        written = os.pwrite(fd, data, start)
    require(written == len(data), 'short write; rollback required')
    os.fsync(fd)
    if fault == 'readback':
        os.pwrite(fd, bytes([data[0] ^ 0xff]), start); os.fsync(fd)
    require(read_at(fd, start, len(data)) == data, 'readback mismatch; rollback required')


def operate(base, image, journal, action, fault=None, board=False, expected_boot_id=None):
    m, package_id = load_package(base)
    require(not board or fault is None, 'hardware fault injection is disabled')
    flags = os.O_RDONLY if action == 'preview' else os.O_RDWR
    # O_NONBLOCK avoids hanging if a FIFO is passed; fstat refuses all devices.
    fd = os.open(image, flags | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if board:
            require(str(image)=='/dev/mmcblk0' and stat.S_ISBLK(info.st_mode), 'live mode requires eMMC user block device')
            spec=importlib.util.spec_from_file_location('migration_live',base/'uboot-migration-live.py')
            live=importlib.util.module_from_spec(spec);spec.loader.exec_module(live)
            live.check_board(m,expected_boot_id,fd)
            image_size=m['capacity_bytes']
        else:
            require(stat.S_ISREG(info.st_mode), 'only regular host image files are supported; hardware disabled')
            require(info.st_size == m['capacity_bytes'], 'image capacity mismatch')
            image_size=info.st_size
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        verify_protected(fd, m)
        identity = [info.st_dev, info.st_ino, image_size]
        state = None
        if journal.exists():
            require(not journal.is_symlink(), 'journal symlink refused')
            state = json.loads(journal.read_text())
            require(state['package'] == package_id and state['image'] == identity, 'journal identity mismatch')
            require(state['phase'] in ['prepared','environment-intent','environment-done',
                                      'proper-intent','installed','rollback-proper-intent',
                                      'rollback-environment-intent','rolled-back'], 'invalid journal phase')
        current = {i['name']:read_at(fd, i['offset'], i['bytes']) for i in m['writes']}
        before = all(current[i['name']] == i['before_data'] for i in m['writes'])
        after = all(current[i['name']] == i['after_data'] for i in m['writes'])
        if action == 'preview':
            require(before or after or state is not None, 'unknown generation; no transaction journal')
            return {'action': action, 'state': 'before' if before else 'after' if after else 'interrupted',
                    'journal_phase': state['phase'] if state else None, 'hardware_enabled': board}
        if action == 'install':
            if after:
                require(state is not None and state['phase'] == 'installed', 'unrecorded installed state')
                return {'action': action, 'state': 'no-op'}
            require(before, 'preimage mismatch; use reviewed rollback for interruption')
            require(state is None or state['phase'] == 'rolled-back', 'unfinished transaction; rollback first')
            journal.parent.mkdir(parents=True, exist_ok=True)
            state = dict(package=package_id, image=identity, phase='prepared')
            save_state(journal, state)
            if fault == 'prepared':
                raise InterruptedError('simulated loss after preparation')
            for item in m['writes']:
                name = item['name']
                if board:live.check_board(m,expected_boot_id,fd)
                state['phase'] = name + '-intent'; save_state(journal, state)
                write_verified(fd, item, item['after_data'],
                               'short' if fault == name+'-short' else 'readback' if fault == name+'-readback' else None)
                verify_protected(fd, m)
                if board:live.check_board(m,expected_boot_id,fd)
                state['phase'] = 'installed' if name == 'proper' else name + '-done'
                save_state(journal, state)
                if fault == name+'-done':
                    raise InterruptedError('simulated loss after ' + name)
            return {'action': action, 'state': 'installed'}
        require(action == 'rollback', 'unknown action')
        require(state is not None, 'rollback requires a bound journal')
        # Refuse arbitrary changes outside the ranges whose write intent was durable.
        phase = state['phase']
        allowed = {
            'prepared': set(), 'environment-intent': {'environment'},
            'environment-done': {'environment'}, 'proper-intent': {'environment','proper'},
            'installed': {'environment','proper'}, 'rollback-proper-intent': {'environment','proper'},
            'rollback-environment-intent': {'environment'}, 'rolled-back': set(),
        }[phase]
        for item in m['writes']:
            if item['name'] not in allowed:
                require(current[item['name']] == item['before_data'], 'unexpected bytes outside journaled write intent')
        if before:
            state['phase']='rolled-back'; save_state(journal,state)
            return {'action': action, 'state': 'no-op'}
        # Restore the old reader before removing its new environment copy.
        for item in reversed(m['writes']):
            name = item['name']
            if current[name] == item['before_data']:
                continue
            if board:live.check_board(m,expected_boot_id,fd)
            state['phase']='rollback-'+name+'-intent'; save_state(journal,state)
            write_verified(fd,item,item['before_data'],
                           'short' if fault == 'rollback-'+name+'-short' else None)
            verify_protected(fd,m)
            if fault == 'rollback-'+name+'-done':
                raise InterruptedError('simulated loss during rollback')
        state['phase']='rolled-back'; save_state(journal,state)
        require(all(read_at(fd,i['offset'],i['bytes']) == i['before_data'] for i in m['writes']), 'rollback readback mismatch')
        return {'action': action, 'state': 'rolled-back'}
    finally:
        os.close(fd)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['preview','install','rollback'])
    p.add_argument('--package',type=Path,required=True)
    target=p.add_mutually_exclusive_group(required=True)
    target.add_argument('--image',type=Path)
    target.add_argument('--device',type=Path,choices=[Path('/dev/mmcblk0')])
    p.add_argument('--journal',type=Path,required=True)
    p.add_argument('--expected-boot-id')
    p.add_argument('--confirm-write',help='full package manifest SHA-256, required for any live write action')
    a=p.parse_args()
    if a.device:
        require(a.expected_boot_id is not None,'live mode requires explicit expected boot ID')
        if a.action!='preview':require(a.confirm_write==sha((a.package/'manifest.json').read_bytes()),'explicit package-bound write confirmation required')
    print(json.dumps(operate(a.package,a.device or a.image,a.journal,a.action,board=a.device is not None,
                             expected_boot_id=a.expected_boot_id),indent=2))


if __name__=='__main__':
    main()
