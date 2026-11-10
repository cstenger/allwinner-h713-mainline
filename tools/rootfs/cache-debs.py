#!/usr/bin/env python3
"""mmdebstrap hook for an explicit, checksummed package download cache."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

mode,cache,root=sys.argv[1:]
cache=Path(cache);root=Path(root)/'var/cache/apt/archives'
cache.mkdir(parents=True,exist_ok=True);root.mkdir(parents=True,exist_ok=True)
ledger=cache/'SHA256.json'
pins=json.loads(ledger.read_text()) if ledger.exists() else {}
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
if mode=='seed':
    for name,expected in pins.items():
        if Path(name).name!=name or not name.endswith('.deb'):raise ValueError('unsafe cache entry')
        source=cache/name
        if source.is_symlink() or digest(source)!=expected:raise ValueError('package cache corruption: '+name)
        shutil.copyfile(source,root/name)
elif mode=='save':
    for source in root.glob('*.deb'):
        if not source.is_file() or source.is_symlink():raise ValueError('unsafe downloaded package')
        value=digest(source)
        if source.name in pins and pins[source.name]!=value:raise ValueError('package bytes changed: '+source.name)
        shutil.copyfile(source,cache/source.name);pins[source.name]=value
    temporary=ledger.with_suffix('.new');temporary.write_text(json.dumps(pins,sort_keys=True,indent=2)+'\n');temporary.replace(ledger)
else:raise ValueError('unknown cache mode')
