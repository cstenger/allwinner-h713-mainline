#!/usr/bin/env python3
"""Install the firmware-log quieting unit and its mips-shell action; no service operations.

At the stock firmware log level 5 the 2 MiB log fills a few hundred CPU_COMM
calls after boot and is printed synchronously, stalling CPU_COMM until a
CALL_ACK times out and sends are quarantined. h713-mips-elog-level.service runs
`mips-shell.py --elog-level 2` once after the HDMI startup.

One transaction, matching the release overlay layout:
  usr/lib/h713-hdmi/mips-shell.py                    replaced (pinned old -> new)
  usr/lib/h713-hdmi/h713-mips-elog-level.service     added
  usr/lib/h713-hdmi/SHA256SUMS                       one line replaced, one added
  etc/systemd/system/h713-mips-elog-level.service    added
  etc/systemd/system/multi-user.target.wants/...     symlink added
Pins the installed shell and manifest, refuses existing new paths, verifies
the whole bundle generation, backs up and reads back. The unit takes effect
on the next boot. Preview by default; --apply installs; --rollback BACKUP
restores exactly.
"""
import argparse, fcntl, hashlib, importlib.util, json, os, tempfile, uuid
from pathlib import Path

spec = importlib.util.spec_from_file_location('guard_io', Path(__file__).with_name('sync-shutdown-guard.py'))
io = importlib.util.module_from_spec(spec); spec.loader.exec_module(io)
SHELL, UNIT, SUMS = 'mips-shell.py', 'h713-mips-elog-level.service', 'SHA256SUMS'
OLD_SHELL = '5d0dd84e3b76947ad1c024f4da53535fd276231767b36a328cf9066f8d4c585f'
NEW_SHELL = 'd7e505bb84278f36b952fb524b8a86a85422a46f6accbcc49c16373060fd9c06'
NEW_UNIT = '31b07edd92def47d24068e638f409c8832a02e33362ea2816a24675164786b56'
OLD_MANIFEST = '5652cf77c3c330aea498e86583012641dde6ac752c5f9ac25f1d0cf00a7d9fc7'  # after kernel 0205 FIT install
SYSTEMD = 'etc/systemd/system'
WANTS = SYSTEMD + '/multi-user.target.wants/' + UNIT
LINK_TARGET = '../' + UNIT
PREFIX = 'elog-level-'
SCHEMA = 'h713-elog-level-install-v1'
ATTRS = {'mode': 0o644, 'uid': 0, 'gid': 0}


def sha(data): return hashlib.sha256(data).hexdigest()
def bundle_path(root, name): return io.path(root, io.BACKEND + '/' + name)
def new_paths(root):
    return [bundle_path(root, UNIT), io.path(root, SYSTEMD + '/' + UNIT), root / WANTS]


def identity(root, boot):
    io.identity(root)
    if (root / 'proc/sys/kernel/random/boot_id').read_text().strip() != boot:
        raise RuntimeError('boot ID changed')
    if not io.path(root, SYSTEMD + '/multi-user.target.wants').is_dir():
        raise RuntimeError('multi-user.target.wants missing')


def new_manifest(before):
    entries = io.table(before)
    shell = [k for k in entries if str(Path(k)) == SHELL]
    if len(shell) != 1 or entries[shell[0]] != OLD_SHELL:
        raise RuntimeError('missing or wrong mips-shell manifest entry')
    if any(str(Path(k)) == UNIT for k in entries):
        raise RuntimeError('unit already listed in the manifest')
    lines = before.decode().splitlines(keepends=True)
    line = OLD_SHELL + '  ' + shell[0]
    hits = [i for i, v in enumerate(lines) if v.rstrip('\r\n') == line]
    if len(hits) != 1 or not before.endswith(b'\n'):
        raise RuntimeError('ambiguous or unterminated manifest')
    lines[hits[0]] = lines[hits[0]].replace(OLD_SHELL, NEW_SHELL, 1)
    prefix = './' if shell[0].startswith('./') else ''
    lines.append(NEW_UNIT + '  ' + prefix + UNIT + '\n')
    return ''.join(lines).encode()


def create(p, data):
    if p.exists() or p.is_symlink():
        raise RuntimeError('target exists: ' + str(p))
    fd, temp = tempfile.mkstemp(prefix='.' + p.name + '.elog-', dir=p.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            if os.geteuid() == 0:
                os.fchown(f.fileno(), 0, 0)
            os.fchmod(f.fileno(), 0o644)
            f.flush(); os.fsync(f.fileno())
        if Path(temp).read_bytes() != data:
            raise RuntimeError('staging readback failed')
        os.link(temp, p)          # fails rather than replacing a racing file
        io.fsync_dir(p.parent)
    finally:
        Path(temp).unlink(missing_ok=True)


def preview(root, bundle, boot):
    identity(root, boot)
    shell, sums = bundle_path(root, SHELL), bundle_path(root, SUMS)
    for p in (shell, sums):
        if io.metadata(p) != ATTRS:
            raise RuntimeError('unexpected file metadata: ' + p.name)
    before = [shell.read_bytes(), sums.read_bytes()]
    if sha(before[0]) != OLD_SHELL or sha(before[1]) != OLD_MANIFEST:
        raise RuntimeError('unexpected installed mips-shell/manifest')
    io.verify_generation(root, before[1])
    for p in new_paths(root):
        if p.exists() or p.is_symlink():
            raise RuntimeError('target exists: ' + str(p))
    new_shell = io.path(bundle, io.BACKEND + '/' + SHELL).read_bytes()
    unit = io.path(bundle, io.BACKEND + '/' + UNIT).read_bytes()
    if sha(new_shell) != NEW_SHELL or sha(unit) != NEW_UNIT:
        raise RuntimeError('payload checksum mismatch')
    return before, new_shell, unit, new_manifest(before[1])


def install(root, bundle, boot, apply=False):
    identity(root, boot)
    fd = os.open(io.path(root, io.STATE), os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if list((root / io.STATE).glob(PREFIX + '*/INCOMPLETE')):
            raise RuntimeError('incomplete elog-level transaction; inspect or roll back first')
        before, new_shell, unit, manifest = preview(root, bundle, boot)
        after = {'shell': sha(new_shell), 'unit': sha(unit), 'manifest': sha(manifest)}
        if not apply:
            return {'phase': 'would-install', 'before': list(map(sha, before)), 'after': after,
                    'adds': [str(p.relative_to(root)) for p in new_paths(root)]}
        backup = root / io.STATE / (PREFIX + uuid.uuid4().hex); backup.mkdir(mode=0o700)
        record = {'schema': SCHEMA, 'boot_id': boot, 'before': list(map(sha, before)), 'after': after}
        io.save(backup / '0', before[0]); io.save(backup / '1', before[1])
        io.save(backup / 'record.json', (json.dumps(record, indent=2) + '\n').encode())
        io.save(backup / 'INCOMPLETE', b'Inspect or roll back before another update or shutdown.\n')
        io.fsync_dir(backup); io.fsync_dir(backup.parent)
        identity(root, boot)
        create(bundle_path(root, UNIT), unit)
        io.atomic(bundle_path(root, SHELL), new_shell, ATTRS, OLD_SHELL)
        io.atomic(bundle_path(root, SUMS), manifest, ATTRS, OLD_MANIFEST)
        io.verify_generation(root, manifest)
        create(io.path(root, SYSTEMD + '/' + UNIT), unit)
        os.symlink(LINK_TARGET, root / WANTS); io.fsync_dir((root / WANTS).parent)
        if (os.readlink(root / WANTS) != LINK_TARGET
                or io.path(root, SYSTEMD + '/' + UNIT).read_bytes() != unit):
            raise RuntimeError('installation readback failed')
        io.save(backup / 'COMMITTED', b'elog-level unit installed; takes effect next boot\n')
        (backup / 'INCOMPLETE').unlink(); io.fsync_dir(backup)
        return {'phase': 'installed', 'backup': str(backup), 'record': record, 'services_changed': False}
    finally:
        os.close(fd)


def rollback(root, backup, boot, apply=False):
    identity(root, boot)
    if backup.parent != root / io.STATE or not backup.name.startswith(PREFIX) or backup.is_symlink():
        raise RuntimeError('invalid rollback location')
    fd = os.open(io.path(root, io.STATE), os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        rel = str(backup.relative_to(root))
        record = json.loads(io.path(root, rel + '/record.json').read_text())
        if record['schema'] != SCHEMA or record['before'] != [OLD_SHELL, OLD_MANIFEST]:
            raise RuntimeError('invalid rollback scope')
        before = [io.path(root, rel + '/0').read_bytes(), io.path(root, rel + '/1').read_bytes()]
        if list(map(sha, before)) != record['before']:
            raise RuntimeError('rollback data corrupted')
        shell, sums = bundle_path(root, SHELL), bundle_path(root, SUMS)
        now = [sha(shell.read_bytes()), sha(sums.read_bytes())]
        if now[0] not in (OLD_SHELL, NEW_SHELL) or now[1] not in (OLD_MANIFEST, record['after']['manifest']):
            raise RuntimeError('foreign target change; refusing rollback')
        for p in new_paths(root)[:2]:
            if p.exists() and sha(p.read_bytes()) != NEW_UNIT:
                raise RuntimeError('foreign unit change; refusing rollback')
        link = root / WANTS
        if link.is_symlink() and os.readlink(link) != LINK_TARGET:
            raise RuntimeError('foreign wants link; refusing rollback')
        if not apply:
            return {'phase': 'would-rollback', 'backup': str(backup)}
        identity(root, boot)
        if link.is_symlink(): link.unlink(); io.fsync_dir(link.parent)
        unit = io.path(root, SYSTEMD + '/' + UNIT)
        if unit.exists(): unit.unlink(); io.fsync_dir(unit.parent)
        io.atomic(sums, before[1], ATTRS, now[1])
        io.atomic(shell, before[0], ATTRS, now[0])
        bundled = bundle_path(root, UNIT)
        if bundled.exists(): bundled.unlink(); io.fsync_dir(bundled.parent)
        io.verify_generation(root, before[1])
        io.save(backup / 'ROLLED_BACK', b'shell, manifest and unit restored\n')
        (backup / 'INCOMPLETE').unlink(missing_ok=True); io.fsync_dir(backup)
        return {'phase': 'rolled-back', 'backup': str(backup), 'services_changed': False}
    finally:
        os.close(fd)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--root', type=Path, default=Path('/'))
    p.add_argument('--bundle', type=Path, default=Path(__file__).resolve().parent)
    p.add_argument('--boot-id', required=True)
    p.add_argument('--rollback', type=Path)
    p.add_argument('--apply', action='store_true')
    a = p.parse_args(); root = a.root.resolve()
    if a.rollback:
        result = rollback(root, a.rollback.absolute(), a.boot_id, a.apply)
    else:
        result = install(root, a.bundle.resolve(), a.boot_id, a.apply)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
