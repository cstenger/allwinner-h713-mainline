#!/usr/bin/env python3
"""Prepare a separate bench U-Boot tree; never install or change normal sources."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def digest(path):
    hasher = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(block)
    return hasher.hexdigest()


def tree_digest(root):
    hasher = hashlib.sha256()
    for path in sorted(root.rglob('*')):
        name = str(path.relative_to(root))
        if path.is_symlink():
            value = 'symlink:' + str(path.readlink())
        elif path.is_file():
            value = digest(path)
        else:
            continue
        hasher.update((name + '\0' + value + '\n').encode())
    return hasher.hexdigest()


def prepare(base, output, include_spl=False, include_domains=False):
    base, output = base.resolve(), output.resolve()
    if output == base or base in output.parents:
        raise ValueError('output must be outside the prepared base tree')
    versions = (ROOT / 'config/versions.env').read_text()
    pin = re.search(r'^UBOOT_SOURCE_COMMIT=([0-9a-f]{40})$', versions, re.M)[1]
    inputs = (base / '.h713-build-inputs').read_text()
    if inputs.splitlines()[0] != 'source ' + pin:
        raise ValueError('base must be the normal prepared U-Boot source pin')
    patches = [HERE / 'reset-trace/0001-proper-reset-observation.patch']
    if include_spl:
        patches.append(HERE / 'reset-trace/0002-optional-spl-reset-observation.patch')
    if include_domains:
        patches.append(HERE / 'reset-trace/0003-proper-domain-controls.patch')
    base_digest = tree_digest(base)
    manifest = {
        'schema': 1, 'purpose': 'bench reset observation; not installed',
        'source_pin': pin, 'normal_inputs': inputs,
        'base_tree_sha256': base_digest, 'optional_spl_probe': include_spl,
        'optional_domain_controls': include_domains,
        'patches': {p.name: digest(p) for p in patches},
    }
    output.mkdir(parents=True, exist_ok=False)
    source = output / 'src'
    shutil.copytree(base, source, symlinks=True)
    if tree_digest(source) != base_digest:
        raise RuntimeError('base changed during copy; discard incomplete output')
    for patch in patches:
        subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(patch)],
                       cwd=source, check=True)
    identity = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:12]
    (source / '.scmversion').write_text(f'-g{pin[:12]}-reset-trace-{identity}\n')
    manifest['instrumented_tree_sha256'] = tree_digest(source)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base', type=Path, help='normal tools/build/build.sh uboot-tree output')
    parser.add_argument('output', type=Path, help='new bench directory, outside the base')
    parser.add_argument('--include-spl', action='store_true',
                        help='also prepare optional pre/post-DRAM SPL probes; no installation')
    parser.add_argument('--include-domains', action='store_true',
                        help='proper-only CCU/SCP control reads; no DSP/receiver access')
    args = parser.parse_args()
    print(prepare(args.base, args.output, args.include_spl, args.include_domains))


if __name__ == '__main__':
    main()
