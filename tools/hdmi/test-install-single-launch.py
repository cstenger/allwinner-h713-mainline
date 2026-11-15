#!/usr/bin/env python3
"""Host tests for install-single-launch.py script-state logic (no board access).

Covers the proper-only bundle mode added for U-Boot 0006: identical baseline
and candidate scripts must read as 'baseline' in every copy (the old FAT
lookup let the candidate key win), the script phase must be refused, and the
normal two-script classification must be unchanged.
"""
import hashlib, importlib.util, json, tempfile, types
from pathlib import Path

spec = importlib.util.spec_from_file_location('isl', Path(__file__).with_name('install-single-launch.py'))
isl = importlib.util.module_from_spec(spec); spec.loader.exec_module(isl)
sha = lambda b: hashlib.sha256(b).hexdigest()


def setup(root, cmd, scr, fat_scr=None):
    bundles = (root / 'b1', root / 'b2')
    for b in bundles:
        b.mkdir()
        (b / 'h713-hdmi.cmd').write_bytes(cmd); (b / 'h713-hdmi.scr').write_bytes(scr)
        (b / 'SHA256SUMS').write_text('%s  h713-hdmi.cmd\n%s  h713-hdmi.scr\n' % (sha(cmd), sha(scr)))
    fat = root / 'fat'; fat.mkdir(); (fat / 'h713-hdmi.scr').write_bytes(fat_scr if fat_scr is not None else scr)
    isl.BUNDLES = bundles; isl.FAT = fat
    isl.subprocess = types.SimpleNamespace(run=lambda *a, **k: types.SimpleNamespace(stdout='/dev/mmcblk0p2\n'))


def manifest(base, cand):
    return {'script': {'baseline': {'h713-hdmi.cmd': sha(base[0]), 'h713-hdmi.scr': sha(base[1])},
                       'candidate': {'h713-hdmi.cmd': sha(cand[0]), 'h713-hdmi.scr': sha(cand[1])}}}


def refused(fn):
    try: fn()
    except (SystemExit, RuntimeError): return True
    return False


def main():
    A, B = (b'cmd-a', b'scr-a'), (b'cmd-b', b'scr-b')
    with tempfile.TemporaryDirectory() as t:
        setup(Path(t), *A); assert isl.script_state(manifest(A, A)) == 'baseline'   # proper-only
    with tempfile.TemporaryDirectory() as t:
        setup(Path(t), *A); assert isl.script_state(manifest(A, B)) == 'baseline'
    with tempfile.TemporaryDirectory() as t:
        setup(Path(t), *B); assert isl.script_state(manifest(A, B)) == 'candidate'
    with tempfile.TemporaryDirectory() as t:
        setup(Path(t), *A, fat_scr=B[1]); assert refused(lambda: isl.script_state(manifest(A, B)))
    with tempfile.TemporaryDirectory() as t:
        setup(Path(t), *A, fat_scr=b'other'); assert refused(lambda: isl.script_state(manifest(A, A)))
    # Script phase refused for a proper-only bundle, before any write.
    m = dict(manifest(A, A), proper={'baseline': 'x', 'candidate': 'y'})
    isl.load_bundle = lambda d: m
    isl.os = types.SimpleNamespace(open=lambda *a: 99, close=lambda fd: None, O_RDONLY=0, O_RDWR=2,
                                   O_NOFOLLOW=0, O_CLOEXEC=0)
    isl.fcntl = types.SimpleNamespace(flock=lambda *a: None, LOCK_EX=0, LOCK_NB=0)
    isl.identity = lambda fd, boot: None
    isl.proper_state = lambda fd, m: 'candidate'
    isl.script_state = lambda m: 'baseline'
    with tempfile.TemporaryDirectory() as t:
        (Path(t) / 'u-boot-proper.itb').write_bytes(b'')
        assert refused(lambda: isl.run(Path(t), 'script', 'boot'))
    print('PASS proper-only reads baseline; two-script classification unchanged; mismatch/foreign refused; script phase refused')


if __name__ == '__main__':
    main()
