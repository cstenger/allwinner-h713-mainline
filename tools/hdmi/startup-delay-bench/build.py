#!/usr/bin/env python3
"""Build a private boot-delay experiment; never connects to or installs on a board."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
BASE = REPO / 'tools/hdmi/h713-hdmi-signal.py'
BASE_SHA = '2b6ac46d09e8af00a551bfe879bb46066c5a5106c82cf1a89bd148410c271445'
PINS = REPO / 'local/recovery/2026-10-30-uboot-migration-install/package/manifest.json'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def transform(source, digest):
    replacements = [
        ('import argparse\n', 'import argparse\nfrom hdmi_delay_bench import prepare as prepare_delay_bench\n'),
        ('    args=parser.parse_args()\n',
         "    parser.add_argument('--bench-delay-ms',type=int,choices=(0,2000))\n"
         "    parser.add_argument('--bench-manifest',type=Path)\n"
         '    args=parser.parse_args()\n'
         f"    delay_bench=prepare_delay_bench(args,{digest!r})\n"),
        ("        require(GRAPH.read_text().strip()=='Y','capture backend not ready')\n",
         "        require(GRAPH.read_text().strip()=='Y','capture backend not ready')\n"
         '        if delay_bench is not None:delay_bench.wait()\n'),
    ]
    for before, after in replacements:
        if source.count(before) != 1:
            raise RuntimeError('production source changed: ambiguous insertion')
        source = source.replace(before, after)
    return source


def verify_ast(original, candidate):
    """Remove exactly the added hooks; every original AST node must remain."""
    tree = ast.parse(candidate)
    tree.body = [n for n in tree.body if not
                 (isinstance(n, ast.ImportFrom) and n.module == 'hdmi_delay_bench')]
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    main.body = [n for n in main.body if not (
        isinstance(n, ast.Expr) and isinstance(n.value, ast.Call) and
        isinstance(n.value.func, ast.Attribute) and n.value.func.attr == 'add_argument' and
        n.value.args and isinstance(n.value.args[0], ast.Constant) and
        n.value.args[0].value in ('--bench-delay-ms', '--bench-manifest')) and not (
        isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'delay_bench' for t in n.targets))]
    start = next(n for n in main.body if isinstance(n, ast.If))
    start.body = [n for n in start.body if not (isinstance(n, ast.If) and
                  isinstance(n.test, ast.Compare) and isinstance(n.test.left, ast.Name) and
                  n.test.left.id == 'delay_bench')]
    if ast.dump(tree) != ast.dump(ast.parse(original)):
        raise RuntimeError('candidate changes production behavior outside approved hooks')
    return {'original_ast_preserved_after_removing_hooks': True,
            'stop_branch_unchanged': True, 'production_sha256': sha(original.encode())}


def build(out):
    source = BASE.read_text()
    if sha(source.encode()) != BASE_SHA:
        raise RuntimeError('unexpected production wrapper')
    pins = json.loads(PINS.read_text())['file_pins']
    if pins['/usr/lib/h713-hdmi/h713-hdmi-signal.py']['sha256'] != BASE_SHA or len(pins) != 56:
        raise RuntimeError('unexpected baseline manifest')
    unit = REPO/'tools/hdmi/h713-hdmi-signal.service'
    if any(sha(unit.read_bytes()) != pins[path]['sha256'] for path in (
            '/usr/lib/h713-hdmi/h713-hdmi-signal.service',
            '/etc/systemd/system/h713-hdmi-signal.service')):
        raise RuntimeError('production unit does not match baseline')
    manifest = {'schema': 'h713-start-delay-v1', 'bundle': '/usr/lib/h713-hdmi',
        'excluded_boot_id': 'afe48e93-6604-44de-a220-acb9416e8363',
        'file_pins': pins, 'allowed_delay_ms': [0, 2000],
        'production_source_sha256': BASE_SHA, 'baseline_manifest_sha256': sha(PINS.read_bytes())}
    raw = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()
    candidate = transform(source, sha(raw))
    proof = verify_ast(source, candidate)
    out.mkdir(parents=True, exist_ok=False)
    (out/'manifest.json').write_bytes(raw)
    (out/'h713-hdmi-signal.py').write_text(candidate)
    for name in ('hdmi_delay_bench.py', 'RUNBOOK.md'):
        shutil.copyfile(HERE/name, out/name)
    shutil.copyfile(REPO/'tools/hdmi/test-hdmi-signal.py', out/'test-hdmi-signal.py')
    shutil.copyfile(BASE, out/'production-wrapper.py')
    shutil.copyfile(REPO/'tools/hdmi/h713-hdmi-signal.service', out/'production-signal.service')
    for delay in (0, 2000):
        (out/f'delay-{delay}.conf').write_text(
            '# SAMPLE ONLY: one future authorized boot, never restart the current owner.\n'
            '[Service]\nExecStart=\n'
            'ExecStart=/usr/bin/python3 /usr/lib/h713-hdmi-delay-bench/h713-hdmi-signal.py start '
            f'--bundle /usr/lib/h713-hdmi --bench-delay-ms={delay} '
            '--bench-manifest=/usr/lib/h713-hdmi-delay-bench/manifest.json\n')
    (out/'AST-PROOF.json').write_text(json.dumps(proof, sort_keys=True, indent=2)+'\n')
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    print(build(parser.parse_args().out))
