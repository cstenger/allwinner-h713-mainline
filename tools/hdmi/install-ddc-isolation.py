#!/usr/bin/env python3
"""Guarded disk-only install of the DDC/HPD isolation diagnostic."""
import argparse
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location('ddc_isolation_transaction',
                                            Path(__file__).with_name('install-source-power.py'))
transaction = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transaction)
transaction.TARGETS = ('usr/lib/h713-hdmi/h713-hdmi-signal.ko',
                       'usr/lib/h713-hdmi/h713-hdmi-readvertise.py',
                       'usr/lib/h713-hdmi/SHA256SUMS')
transaction.BACKUP_PREFIX = 'ddc-isolation-'

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path('/'))
    p.add_argument('--package', type=Path, required=True)
    p.add_argument('--boot', required=True)
    p.add_argument('--manifest-sha', required=True)
    p.add_argument('--apply', action='store_true')
    p.add_argument('--rollback', type=Path)
    a = p.parse_args()
    print(json.dumps(transaction.install(a.root, a.package, a.boot, a.manifest_sha,
                                         a.apply, a.rollback), indent=2))
