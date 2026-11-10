#!/usr/bin/env python3
"""Prepare exact Wi-Fi startup delta from rootfs builder and accepted file backup."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tarfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('installer', Path(__file__).with_name('install-parallel-startup.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def block(text, destination, delimiter='EOF'):
    marker = 'cat > "'+destination+'" <<'
    matches = [line for line in text.splitlines(keepends=True) if line.lstrip().startswith(marker)]
    if len(matches) != 1:
        raise RuntimeError('ambiguous source block: '+destination)
    return text.split(matches[0], 1)[1].split('\n'+delimiter+'\n', 1)[0].encode()+b'\n'


def payloads():
    source = (ROOT/'tools/rootfs/customize.sh').read_text()
    return [block(source, '$R/etc/modules-load.d/aic8800.conf'),
            block(source, '$systemd_dir/h713-hotspot.service'),
            block(source, '$systemd_dir/h713-bt-attach.service'),
            block(source, '$R/etc/modprobe.d/h713-aic8800-startup.conf'),
            block(source, '$systemd_dir/'+m.OWNER)]


def build(before_archive, output):
    with tarfile.open(before_archive) as archive:
        before = {v.name: archive.extractfile(v).read() for v in archive.getmembers() if v.isfile()}
    if set(before) != set(m.TARGETS[:3]) or tuple(m.digest(before[n]) for n in m.TARGETS[:3]) != m.BEFORE[:3]:
        raise RuntimeError('backup differs from accepted RC')
    output.mkdir(parents=True, exist_ok=False)
    data = payloads()
    for name, content in zip(m.TARGETS[:-1], data):
        path = output/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    manifest = dict(schema='h713-parallel-wifi-v1', targets=list(m.TARGETS),
                    before=[dict(sha256=h) if h else None for h in m.BEFORE],
                    after=[dict(sha256=m.digest(v)) for v in data]+[dict(symlink='../'+m.OWNER)])
    (output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    for name, source in (('install-parallel-startup.py', ROOT/'tools/wifi/install-parallel-startup.py'),
                         ('sync-shutdown-guard.py', ROOT/'tools/hdmi/sync-shutdown-guard.py'),
                         ('install-parallel-capture.py', ROOT/'tools/hdmi/install-parallel-capture.py')):
        shutil.copyfile(source, output/name)
    return hashlib.sha256((output/'manifest.json').read_bytes()).hexdigest()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before_archive', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(build(args.before_archive, args.output))
