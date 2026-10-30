#!/usr/bin/env python3
"""Compare saved board inventory with this checkout and retained artifacts.

Offline only. Does not rebuild firmware or contact the board. Artifact matches
are explicitly weaker than source matches or demonstrated clean rebuilds.
"""
from pathlib import Path
import collections
import hashlib
import json
import subprocess
import re
import difflib

ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent
inventory = json.loads((BASE / 'board-inventory.json').read_text())
files = inventory['files']
for path, text in json.loads((BASE / 'additional-utility-text.json').read_text()).items():
    assert hashlib.sha256(text.encode()).hexdigest() == files[path]['sha256']
    files[path]['text'] = text
modules = json.loads((BASE / 'module-artifact-matches.json').read_text())
tracked = [p for p in subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT, text=True).split('\0') if p]
index = collections.defaultdict(list)
for p in tracked:
    if p.startswith(('tools/', 'modules/')):
        index[Path(p).name].append(p)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


recipes = (ROOT / 'tools/rootfs/customize.sh').read_text()
aliases = {'h713-hdmi-capture.service': 'tools/hdmi/h713-hdmi-capture-startup.service',
           'enable-mixer.sh': 'tools/hdmi/enable-speaker-mixer.sh'}
manifests = []
for p, value in files.items():
    if Path(p).name != 'SHA256SUMS' or 'text' not in value:
        continue
    checks = []
    for line in value['text'].splitlines():
        digest, name = line.split('  ', 1)
        assert not Path(name).is_absolute() and '..' not in Path(name).parts
        target = str(Path(p).parent / name)
        actual = files.get(target, {}).get('sha256')
        checks.append({'path': target, 'expected': digest, 'actual': actual, 'matches': actual == digest})
    manifests.append({'path': p, 'all_match': all(c['matches'] for c in checks), 'checks': checks})

firmware_pins = {}
for line in (ROOT / 'modules/aic8800/firmware.sha256sums').read_text().splitlines():
    if line.strip():
        digest, name = line.split(None, 1)
        firmware_pins[name.strip()] = digest
rows = []
recipe_differences = {}
for p, value in files.items():
    name = Path(p).name
    row = {'installed_path': p, **{k: value[k] for k in ('sha256', 'size', 'mode', 'uid', 'gid', 'symlink', 'error') if k in value}}
    row['status'] = 'unmapped'
    candidates = index[name].copy()
    templates = list(re.finditer(r'cat > [^\n]*' + re.escape(name) + r'["\x27]? <<[\x27"]?(\w+)[\x27"]?\n(.*?)\n\1(?:\n|$)', recipes, re.S))
    if name in aliases:
        candidates.insert(0, aliases[name])
    matches = [s for s in candidates if (ROOT / s).is_file() and sha(ROOT / s) == value.get('sha256')]
    if 'error' in value:
        row['status'] = 'absent_or_unreadable'
    elif matches:
        row.update(status='source_match', source_paths=matches)
    elif name == 'h713-hdmi-hold-guard':
        row.update(status='source_difference', source_paths=candidates,
                   note='Installed hook lacks repository checks for h713_hdmi_dsp_observe and h713_hdmi_dsp_access_audit; see saved diff.')
    elif p in modules:
        row.update(status='retained_artifact_match' if modules[p] else 'binary_rebuild_unproven',
                   matching_artifacts=modules[p],
                   note='Installed disk bytes only. Retained binary identity does not establish a current-source clean rebuild or loaded-module byte identity.')
    elif name in ('h713-hdmi.cmd', 'h713-hdmi.scr', 'manifest.json') and p.startswith(('/usr/lib/h713-hdmi/', '/usr/lib/h713-hdmi-health/')):
        rebuilt = ROOT / 'build/production-audit-2026-10-28/regenerated-startup' / name
        row.update(status='regenerated_match' if rebuilt.exists() and sha(rebuilt) == value.get('sha256') else 'generated_difference',
                   recipe='tools/hdmi/build-shared-startup.py',
                   note='Exact regeneration succeeded using existing ignored baseline and pinned kernel artifacts; not a clean-checkout build.')
    elif name == 'SHA256SUMS':
        row['status'] = 'recorded_manifest'
    elif '/__pycache__/' in p:
        row['status'] = 'runtime_generated_cache'
    elif templates:
        bodies = [t.group(2) + '\n' for t in templates]
        match = any(hashlib.sha256(body.encode()).hexdigest() == value.get('sha256') for body in bodies)
        row.update(status='rootfs_recipe_match' if match else 'rootfs_recipe_difference',
                   source_paths=['tools/rootfs/customize.sh'],
                   note='Compared with inline template; byte differences can include comments, packaging or configuration and require review.')
        if not match and value.get('text'):
            closest = max(bodies, key=lambda body: difflib.SequenceMatcher(None, value['text'], body).ratio())
            significant = lambda text: [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#')]
            row['noncomment_lines_match'] = significant(value['text']) == significant(closest)
            recipe_differences[p] = ''.join(difflib.unified_diff(value['text'].splitlines(True), closest.splitlines(True), fromfile='installed', tofile='rootfs template'))
            if name == 'h713-bt-attach.service':
                row['effective_timeout_qualification'] = 'Installed unit receives the 10-second stop timeout via /etc/systemd/system/h713-bt-attach.service.d/10-stop-timeout.conf; template puts it in the unit.'
    elif value.get('text') and value['text'] in recipes:
        row.update(status='rootfs_recipe_match', source_paths=['tools/rootfs/customize.sh'])
    elif '/firmware/aic8800_fw/' in p:
        row.update(status='pinned_firmware_match' if firmware_pins.get(name) == value.get('sha256') else 'firmware_pin_difference',
                   source_paths=['modules/aic8800/firmware.sha256sums'],
                   note='Proprietary file is a local-only build input; hash match does not supply redistributable source.')
    elif name == 'hdmi-audio-dsp.bin':
        row.update(status='pinned_firmware_match' if value.get('sha256') == '8e31db199e0078d142f622436ff0b7249b333dbb6df8ec3fbabc0d8fea6ea0c5' else 'firmware_pin_difference',
                   source_paths=['tools/hdmi/h713-hdmi-session.py'], note='Pinned proprietary DSP payload; bytes are not stored in this audit.')
    elif p == '/usr/local/bin/gst-plane-play':
        accepted = json.loads((ROOT / 'docs/hdmi-evidence/2026-10-28-playback-ownership/ACCEPTANCE-RESULT.json').read_text())
        row.update(status='accepted_binary_match' if value.get('sha256') == accepted['player_sha256'] else 'accepted_binary_difference',
                   source_paths=['tools/video/gst-plane-play.c'],
                   note='Matches recorded native-target compile/installation acceptance; no target build performed during read-only audit.')
    elif p == '/etc/default/h713-hdmi-speaker':
        saved = ROOT / 'docs/hdmi-evidence/2026-10-27-avsync-calibration/installed-speaker-defaults.conf'
        row.update(status='board_configuration_match' if sha(saved) == value.get('sha256') else 'board_configuration_difference',
                   source_paths=[str(saved.relative_to(ROOT))], note='Board-specific 40 ms calibration; generic installer does not create this defaults file.')
    elif p == '/var/lib/h713-hdmi-startup/kernel.sha256':
        boot = json.loads((BASE / 'boot-files.json').read_text())
        row.update(status='boot_pin_match' if value['text'].split()[0] == boot['h713-kernel.fit']['sha256'] else 'boot_pin_difference')
    elif p in ('/usr/bin/mpv', '/usr/lib/aarch64-linux-gnu/dri/v4l2_request_drv_video.so', '/usr/local/bin/mpv-direct'):
        row.update(status='installed_binary_fingerprinted',
                   note='See installed package inventory or video-stack stamp. Exact binary-to-source rebuild not demonstrated by audit.')
    elif '.before-' in name or '.ko.pre-' in name or name == 'install.log':
        row.update(status='historical_backup_or_log', note='Retained historical material, not an active implementation.')
    elif name == 'boot-environment.json':
        row.update(status='recorded_configuration_snapshot', note='Historical bundle configuration; live selected values were independently CRC-verified in the raw active environment.')
    elif p == '/etc/h713-video-stack':
        row.update(status='installation_provenance_stamp', note='Series stamps checked separately; kernel-module stamp predates the boot FIT and is not a complete release manifest.')
    elif p in ('/usr/lib/h713-hdmi-speaker/alsa-ctl', '/usr/lib/h713-hdmi-speaker/hdmi-speaker') or name == 'h713-keyd':
        row.update(status='binary_rebuild_unproven', note='Target-compiled utility; source/recipe exists, exact binary rebuild not performed. hdmi-speaker is retired from the active PipeWire route.')
    elif p.startswith('/etc/') and 'sha256' in value:
        row.update(status='board_local_configuration', note='Fingerprint recorded; no full image/configuration lock or exact template match established.')
    elif 'sha256' not in value:
        row['status'] = 'directory_metadata'
    elif candidates:
        row.update(status='source_difference', source_paths=candidates)
    rows.append(row)

boot_files = json.loads((BASE / 'boot-files.json').read_text())
boot_checks = {}
for name, item in boot_files.items():
    local = ROOT / 'build/out' / name
    boot_checks[name] = {**item, 'local_artifact': str(local.relative_to(ROOT)),
                        'local_sha256': sha(local) if local.is_file() else None,
                        'local_artifact_present': local.is_file(),
                        'matches_local': sha(local) == item['sha256'] if local.is_file() else None}
boot_checks['h713-hdmi.scr']['matches_installed_backend'] = boot_files['h713-hdmi.scr']['sha256'] == files['/usr/lib/h713-hdmi/h713-hdmi.scr']['sha256']
boot_checks['h713-hdmi.scr']['matches_regenerated'] = boot_files['h713-hdmi.scr']['sha256'] == sha(ROOT/'build/production-audit-2026-10-28/regenerated-startup/h713-hdmi.scr')
proper = ROOT / 'build/hdmi-reset-controls-2026-10-20/trial-package/proper-controls.bin'
normal = ROOT / 'build/out/u-boot-sunxi-with-spl-ddr3.bin'
normal_data = normal.read_bytes()[32768:]
proper_record = {**inventory['bootloader']['uboot-proper'],
                 'retained_artifact': str(proper.relative_to(ROOT)),
                 'retained_sha256': sha(proper),
                 'matches_retained': sha(proper) == inventory['bootloader']['uboot-proper']['sha256'],
                 'normal_build_proper_padded_sha256': hashlib.sha256(normal_data + bytes((-len(normal_data)) % 512)).hexdigest(),
                 'normal_build_inputs': 'build/out/u-boot-ddr3.inputs',
                 'classification': 'recorded_diagnostic_build_differs_from_normal_production_recipe'}

video_stamp = files['/etc/h713-video-stack']['text']
series_checks = {}
for component, prefix in [('libva-v4l2_request', 'va_driver'), ('mpv', 'mpv')]:
    patches = ROOT / 'patches' / component
    names = [p for p in (patches/'series').read_text().splitlines() if p]
    data = ''.join(sha(patches/p) + '  ' + str(patches/p) + '\n' for p in names)
    expected = hashlib.sha256(data.encode()).hexdigest()[:16]
    actual = next((line.split('=', 1)[1] for line in video_stamp.splitlines() if line.startswith(prefix+'_series=')), None)
    series_checks[component] = {'current_series_id': expected, 'installed_stamp': actual,
                                'matches_stamp': expected == actual, 'binary_rebuild_proven': False}
    if component == 'mpv':
        series_checks[component]['qualification'] = 'Retired patched mpv-direct stamp; active /usr/bin/mpv is a Debian package.'

kernel_tree = subprocess.check_output(['bash', '-c', 'KERNEL_CONFIG=sysrq tools/build/build.sh kernel-tree'], cwd=ROOT, text=True).strip()
generated = json.loads((BASE/'regenerated-startup-manifest.json').read_text())
saved_env = inventory['boot_environments']['documented-active'].get('selected_values', {})
manifest = {
    'schema': 'h713-production-audit-v1', 'source_commit': inventory['source_commit'],
    'audit_host_utc': inventory['audit_host_utc'], 'scope': 'HY200 QZ713DF_A1 DDR3 only; read-only board snapshot; no clean rebuild or functional retest',
    'board_clock_untrusted': True, 'boot_id': inventory['runtime']['/proc/sys/kernel/random/boot_id'],
    'clock_observation': next(c for c in inventory['commands'] if c['argv'][0] == 'timedatectl'),
    'local_build_output_ledger': json.loads((BASE / 'local-build-ledger-check.json').read_text()),
    'production_readiness': 'Incomplete: exact full source-based recreation not demonstrated; known guard drift and environment migration remain.',
    'findings': [
        {'id': 'F1', 'kind': 'source_difference', 'summary': 'Both installed hold guards lack two diagnostic-module checks present in current source.', 'evidence': 'hold-guard-difference.diff'},
        {'id': 'F2', 'kind': 'intentional_recipe_difference', 'summary': 'Installed proper is the recorded diagnostic reset-controls image, not the normal production U-Boot build.'},
        {'id': 'F3', 'kind': 'known_layout_defect', 'summary': 'Active valid environment remains at unintended LBA 0x32ec00; configured LBA 0x49ec00 is empty.'},
        {'id': 'F4', 'kind': 'stale_build_metadata', 'summary': 'All seven entries in build/out/SHA256SUMS differ from current host output bytes.', 'evidence': 'local-build-ledger-check.json'},
        {'id': 'F5', 'kind': 'configuration_gap', 'summary': 'System/RTC calendars incorrect and time synchronization unavailable.'},
        {'id': 'F6', 'kind': 'recreation_gap', 'summary': 'Startup regeneration succeeds with retained ignored inputs; no complete clean-checkout release assembly demonstrated.'},
    ],
    'status_counts': dict(collections.Counter(r['status'] for r in rows)),
    'installed_bundle_integrity': manifests, 'boot_files': boot_checks,
    'bootloader': proper_record, 'spl': inventory['bootloader']['spl'],
    'environment': inventory['boot_environments'], 'video_source_stamps': series_checks,
    'live_environment_commands_match_current_generator': {key: saved_env.get(key) == generated[key] for key in ('preboot', 'bootcmd')},
    'current_kernel_recipe_tree': {'path': kernel_tree, 'exists': Path(kernel_tree).is_dir(),
                                   'running_config_available': inventory['running_kernel_config'] is not None,
                                   'qualification': 'No current-input kernel build executed. Disk FIT identity is not an independent hash of the running kernel.'},
    'files': rows,
    'boot_display_assets': json.loads((BASE / 'boot-display-assets.json').read_text()),
    'recreation_gaps': [
        'Installed diagnostic U-Boot differs from normal pinned production recipe; final integration and accepted environment migration are not provided by a unified release process.',
        'Active saved environment remains at documented unintended LBA 0x32ec00 inside super; configured LBA 0x49ec00 is all zero. Correct source offset handling requires migration of saved guard configuration, not an isolated code swap.',
        'Shared startup regenerates exactly only with ignored October 20 baseline plus pinned build/out kernel artifacts; current builder is a delta updater, not a clean backend installer.',
        'Current kernel-input tree is absent and /proc/config.gz unavailable; no clean rebuild or current-input binary provenance proven for installed kernel/modules.',
        'Generic rootfs workflow does not assemble the complete accepted HDMI installation; separate installers and board calibration are required.',
        'Proprietary display/DSP/Wi-Fi inputs and local hotspot settings are not all supplied by the public checkout; credentials deliberately excluded from audit.',
        'Package versions and binary hashes recorded, but no Debian snapshot, complete compiler/dependency lock or full rootfs byte-rebuild proof.',
    ]}
(BASE / 'production-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
(BASE / 'rootfs-recipe-differences.json').write_text(json.dumps(recipe_differences, indent=2)+'\n')
print(json.dumps({'files': len(rows), 'status_counts': manifest['status_counts'],
                  'bundle_checks': {p['path']: p['all_match'] for p in manifests},
                  'boot_checks': boot_checks, 'kernel_tree': manifest['current_kernel_recipe_tree']}, indent=2))
