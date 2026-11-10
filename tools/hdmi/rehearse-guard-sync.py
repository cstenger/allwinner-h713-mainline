#!/usr/bin/env python3
"""Reconstruct the audited backend locally and rehearse its guard-only delta.

Uses host-retained files, never the board. Raw/vendor data stays in temporary
host files and is deleted after the rehearsal; output is hashes/results only.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('guard_sync', ROOT/'tools/hdmi/sync-shutdown-guard.py')
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)


def snapshot(root):
    return {str(p.relative_to(root)): (p.stat().st_mode & 0o777, p.read_bytes() if p.is_file() else None)
            for p in sorted(root.rglob('*'))}


def rehearse(bundle):
    inventory = json.loads((ROOT/'docs/production-audit/2026-10-28/board-inventory.json').read_text())
    files = inventory['files']
    manifest = files['/usr/lib/h713-hdmi/SHA256SUMS']['text'].encode()
    before_manifest = u.digest(manifest)
    retained = ROOT/'build/hdmi-reset-baseline-2026-10-20/artifacts/installed'
    with tempfile.TemporaryDirectory(prefix='h713-audited-guard-') as temp:
        root = Path(temp)
        backend = root/u.BACKEND
        backend.mkdir(parents=True)
        (root/u.STATE).mkdir(parents=True)
        (root/'proc/device-tree').mkdir(parents=True)
        (root/'proc/device-tree/model').write_text('HY200 QZ713DF_A1 (Allwinner H713)\0')
        restored = []
        for name, expected in u.table(manifest).items():
            record = files['/usr/lib/h713-hdmi/'+name]
            candidates = []
            if 'text' in record:
                candidates.append(record['text'].encode())
            for p in (retained/name, ROOT/'build/production-audit-2026-10-28'/name):
                if p.is_file():candidates.append(p.read_bytes())
            matches = [data for data in candidates if u.digest(data) == expected]
            if not matches:
                raise RuntimeError('retained input missing or changed: '+name)
            p = backend/name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(matches[0])
            p.chmod(int(record['mode'],8))
            restored.append(name)
        (backend/'SHA256SUMS').write_bytes(manifest)
        (backend/'SHA256SUMS').chmod(0o644)
        hook = root/u.TARGETS[1]
        hook.parent.mkdir(parents=True)
        hook.write_bytes((backend/u.GUARD).read_bytes())
        hook.chmod(0o755)
        original = snapshot(root)
        preview = u.install(root,bundle)
        assert preview['phase']=='would-install' and snapshot(root)==original
        result = u.install(root,bundle,dry_run=False)
        after = snapshot(root)
        changed = [p for p,v in original.items() if after[p]!=v]
        assert set(changed)==set(u.TARGETS), changed
        assert u.install(root,bundle,dry_run=False)['phase']=='already-current'
        backup = Path(result['backup'])
        before_rollback = snapshot(root)
        assert u.rollback(root,backup)['phase']=='would-rollback' and snapshot(root)==before_rollback
        u.rollback(root,backup,dry_run=False)
        rolled_back = snapshot(root)
        assert all(rolled_back[p]==v for p,v in original.items())
        return {'scope':'offline exact audited-generation fixture; no board access',
                'audited_backend_files_verified':len(restored), 'before_manifest':before_manifest,
                'after_manifest':json.loads((bundle/'manifest.json').read_text())['after_manifest'],
                'changed_existing_files':changed, 'preview':'PASS: no writes',
                'install':'PASS: only two guards and manifest change', 'idempotence':'PASS',
                'rollback_preview':'PASS: no writes', 'rollback':'PASS: original bytes and modes restored',
                'qualification':'Fixture ownership uses host user; target ownership preserved by installer but not live-verified.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('bundle',type=Path)
    print(json.dumps(rehearse(p.parse_args().bundle.resolve()),indent=2))
