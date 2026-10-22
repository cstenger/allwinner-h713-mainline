#!/usr/bin/env python3
"""Build an isolated warm TVFE-retention kernel and observer bundle; never install."""
import argparse
import difflib
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
ASSETS = Path(__file__).with_name('dsp-retention')
REL = 'drivers/pmdomain/sunxi/sun50i-h713-ppu.c'
BASE_SOURCE = '3b5c2b2303d5c0c8b4a4917b5f25ef774ec135220a27530bf4d92734f99e60f4'


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def instrument(source):
    def once(old, new):
        nonlocal source
        if source.count(old) != 1:
            raise ValueError('ambiguous source anchor: ' + old[:60])
        source = source.replace(old, new)
    once('static int __init h713_tvfe_trace_early(void)',
         '#include "h713-retention-hold.inc"\n\nstatic int __init h713_tvfe_trace_early(void)')
    once('if (!h713_tvfe_trace_enabled)\n\t\treturn 0;',
         'if (!h713_tvfe_trace_enabled) {\n\t\th713_tvfe_retain_check();\n\t\treturn 0;\n\t}')
    once('h713_tvfe_boot_trace("linux_early_initcall");',
         'h713_tvfe_boot_trace("linux_early_initcall");\n\th713_tvfe_retain_check();')
    once('\t/* Wait for domain idle before switching */',
         '\tif (h713_tvfe_retain_requested && pd->hw_id == 1) {\n'
         '\t\th713_tvfe_retain_violated = true;\n\t\th713_tvfe_retain_applied = false;\n'
         '\t\tpr_err("H713 RETENTION violated: TVFE power command on=%d\\n", on);\n\t}\n\n'
         '\t/* Wait for domain idle before switching */')
    once('bool always_on = h713_ppu_hw_ids[i] < 0 ||',
         'bool retain = h713_tvfe_retain_eligible && i == 1;\n'
         '\t\tbool always_on = retain || h713_ppu_hw_ids[i] < 0 ||')
    once('\t\tif (always_on) {',
         '\t\tif (retain && !h713_ppu_is_on(pd)) {\n\t\t\tret = -EIO;\n'
         '\t\t\tgoto err_remove_domains;\n\t\t}\n\n\t\tif (always_on) {')
    once('\t\t\tpd->genpd.flags = GENPD_FLAG_ALWAYS_ON;',
         '\t\t\tif (retain && !h713_ppu_is_on(pd)) {\n\t\t\t\tret = -EIO;\n'
         '\t\t\t\tgoto err_remove_domains;\n\t\t\t}\n'
         '\t\t\tpd->genpd.flags = GENPD_FLAG_ALWAYS_ON;')
    once('\th713_tvfe_boot_trace("ppu_probe_complete");',
         '\th713_tvfe_retain_applied = h713_tvfe_retain_eligible &&\n'
         '\t\t!h713_tvfe_retain_violated && h713_ppu_is_on(&pds[1]);\n'
         '\tif (h713_tvfe_retain_requested)\n'
         '\t\tpr_notice("H713 RETENTION applied=%d; TVFE always-on bench flag\\n",\n'
         '\t\t\th713_tvfe_retain_applied);\n'
         '\th713_tvfe_boot_trace("ppu_probe_complete");')
    return source + '\n#include "h713-retention-observer.inc"\n'


def make_guard():
    guard = (ROOT / 'tools/hdmi/h713-hdmi-hold-guard').read_text()
    anchor = '[ -n "$held" ] || exit 0'
    if guard.count(anchor) != 1:
        raise ValueError('unexpected production guard source')
    return guard.replace(anchor,
        'C=${H713_GUARD_CMDLINE:-/proc/cmdline}\n'
        'case " $(cat "$C" 2>/dev/null) " in\n'
        '  *" h713_tvfe_retain=1 "*) held="$held h713_tvfe_retain";;\nesac\n' + anchor)


def prepare(base, output):
    base, output = base.resolve(), output.resolve()
    if output.exists():
        raise FileExistsError(output)
    if base in output.parents or output in base.parents or base == output:
        raise ValueError('output must be separate from base')
    old = json.loads((base / 'manifest.json').read_text())
    if not old.get('built') or not old.get('symvers_unchanged') or sha(base / 'kernel' / REL) != BASE_SOURCE:
        raise ValueError('exact successful TVFE trace candidate required')
    if sha(base / 'artifacts/kernel.fit') != '54a691f727e3b405540ea806f11afe5da6178109adb3747094b55ea4f12fbf7e':
        raise ValueError('trace candidate artifact changed')
    output.mkdir(parents=True, exist_ok=False)
    subprocess.run(['cp', '-a', '--reflink=auto', str(base / 'kernel'), str(output / 'kernel')], check=True)
    target = output / 'kernel' / REL
    original = target.read_text()
    changed = instrument(original)
    target.write_text(changed)
    (output / 'bench-ppu.patch').write_text(''.join(difflib.unified_diff(original.splitlines(True),
        changed.splitlines(True), fromfile='a/' + REL, tofile='b/' + REL)))
    driver = target.parent
    for src, name in [('retention-policy.h', 'h713-retention-policy.h'),
                      ('retention-hold.inc', 'h713-retention-hold.inc'),
                      ('observer.inc', 'h713-retention-observer.inc')]:
        shutil.copyfile(ASSETS / src, driver / name)
    for name in ['h713-dsp-lock.h', 'h713-dsp-completion.h']:
        shutil.copyfile(ROOT / 'modules/hdmi-dsp-probe' / name, driver / name)
    guard = make_guard()
    bundle = output / 'bundle'
    bundle.mkdir()
    (bundle / 'h713-hdmi-hold-guard').write_text(guard)
    (bundle / 'h713-hdmi-hold-guard').chmod(0o755)
    for src in ['dsp-retention.py', 'analyze-dsp-retention.py']:
        shutil.copyfile(ROOT / 'tools/hdmi' / src, bundle / src)
    manifest = {'schema': 1, 'purpose': 'bench DSP warm retention; not installed',
        'base': str(base), 'baseline': old['baseline'], 'built': False,
        'base_source_sha256': BASE_SOURCE, 'patched_source_sha256': sha(target),
        'assets': {p.name: sha(p) for p in sorted(ASSETS.iterdir()) if p.is_file()},
        'guard_previous_expected_sha256': sha(ROOT / 'tools/hdmi/h713-hdmi-hold-guard'),
        'requires': ['h713_tvfe_trace=1', 'h713_tvfe_retain=1', 'panic=0', 'loglevel=7'],
        'bundle': {p.name: sha(p) for p in bundle.iterdir() if p.is_file()}}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def build(output, jobs):
    manifest = json.loads((output / 'manifest.json').read_text())
    kernel = output / 'kernel'
    command = ['make', '-C', str(kernel), 'ARCH=arm64', 'LLVM=1', '-j' + str(jobs), 'Image', 'modules']
    with (output / 'build.log').open('w') as log:
        subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)
    artifacts = output / 'artifacts'
    artifacts.mkdir()
    (artifacts / 'Image.gz').write_bytes(gzip.compress((kernel / 'arch/arm64/boot/Image').read_bytes(), mtime=0))
    base = Path(manifest['base'])
    shutil.copyfile(base / 'artifacts/board.dtb', artifacts / 'board.dtb')
    its = (base / 'artifacts/kernel.its').read_text().replace(str(base / 'artifacts'), str(artifacts))
    its = its.replace('H713 bench TVFE boot trace v1', 'H713 bench DSP retention v1')
    (artifacts / 'kernel.its').write_text(its)
    subprocess.run([str(base / 'uboot-obj/tools/mkimage'), '-f', str(artifacts / 'kernel.its'),
                    str(artifacts / 'kernel.fit')], capture_output=True, check=True)
    shutil.copyfile(artifacts / 'kernel.fit', output / 'bundle/kernel.fit')
    manifest.update(built=True, build_command=command,
        compiler=subprocess.check_output(['clang', '--version'], text=True),
        kernel_release=(kernel / 'include/config/kernel.release').read_text().strip(),
        symvers_unchanged=sha(kernel / 'Module.symvers') == manifest['baseline']['kernel_symvers'],
        artifacts={p.name: {'size': p.stat().st_size, 'sha256': sha(p)} for p in artifacts.iterdir()},
        bundle={p.name: sha(p) for p in (output / 'bundle').iterdir() if p.name != 'manifest.json'},
        kernel_uts_version=(kernel / 'include/generated/utsversion.h').read_text().split('"')[1])
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (output / 'bundle/manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--build', action='store_true')
    p.add_argument('--jobs', type=int, default=12)
    args = p.parse_args()
    if args.jobs < 1:
        p.error('--jobs must be positive')
    prepare(args.base, args.output)
    if args.build:
        build(args.output.resolve(), args.jobs)
    print(args.output.resolve() / 'manifest.json')


if __name__ == '__main__':
    main()
