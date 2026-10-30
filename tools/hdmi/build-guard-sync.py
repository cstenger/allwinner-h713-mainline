#!/usr/bin/env python3
"""Package a guard-only delta pinned to the October 28 read-only audit."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
OLD = '9140e3104042cd291496f3c238d1c3ef151184d362f32752c7179f9b25483db7'
NEW = '96f37655b33bf78d95b33fa4f431721be5a7506c73c12dcd4df58032cad27113'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def build(out):
    audit = ROOT / 'docs/production-audit/2026-10-28/board-inventory.json'
    r = json.loads(audit.read_text())
    files = r['files']
    guard = (ROOT / 'tools/hdmi/h713-hdmi-hold-guard').read_bytes()
    if sha(guard) != NEW:
        raise RuntimeError('candidate guard differs from reviewed generation')
    for name in ('/usr/lib/h713-hdmi/h713-hdmi-hold-guard', '/usr/lib/systemd/system-shutdown/h713-hdmi-hold-guard'):
        if files[name]['sha256'] != OLD:
            raise RuntimeError('unexpected audited guard')
    old = files['/usr/lib/h713-hdmi/SHA256SUMS']['text'].encode()
    new = old.replace((OLD + '  h713-hdmi-hold-guard').encode(), (NEW + '  h713-hdmi-hold-guard').encode())
    if sha(old) != files['/usr/lib/h713-hdmi/SHA256SUMS']['sha256'] or old == new:
        raise RuntimeError('audited manifest inconsistent')
    manifest = {'schema': 'h713-shutdown-guard-sync-v1', 'before_guard': OLD, 'after_guard': NEW,
                'before_manifest': sha(old), 'after_manifest': sha(new),
                'audit_source_commit': r['source_commit'], 'audit_sha256': sha(audit.read_bytes()),
                'board': 'HY200 QZ713DF_A1 (Allwinner H713)',
                'scope': 'two guard copies and backend SHA256SUMS; backup state only; no hardware/service operations'}
    out.mkdir(parents=True, exist_ok=False)
    for name in ('h713-hdmi-hold-guard', 'sync-shutdown-guard.py'):
        shutil.copyfile(ROOT / 'tools/hdmi' / name, out / name)
        (out / name).chmod(0o755)
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    (out / 'SHA256SUMS').write_text(''.join(sha(p.read_bytes())+'  '+p.name+'\n' for p in sorted(out.iterdir())))
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    print(json.dumps(build(parser.parse_args().output), indent=2))
