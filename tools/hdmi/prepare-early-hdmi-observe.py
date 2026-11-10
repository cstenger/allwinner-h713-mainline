#!/usr/bin/env python3
"""Prepare an offline, read-only U-Boot resource observation script.

Does not connect to the board or install anything. The receiver aperture is
never read. Start from the exact installed command script, preserving its
existing commands and guards, and insert tagged reads of known resource regs.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

BASELINE = '33677778d4ce232d31d94ff36c6082583229cc41a02ec4319c37a88b02f46c8b'
ANCHORS = (
    ('before-logo', 'h713_disp auto 0x34 logo', False),
    ('after-logo', 'h713_disp auto 0x34 logo', True),
    ('after-relaunch', 'h713_disp mips-comm-trace 0x34', True),
    ('before-source', 'h713_disp commcall eaf13de5 chan=0 pid=${hdmi_pid} 3', False),
    ('after-source', 'h713_disp commcall eaf13de5 chan=0 pid=${hdmi_pid} 3', True),
    ('before-linux', 'bootm 0x50000000 - 0x4f000000', False),
)


def snapshot(stage):
    # EDID reset/clock and DDC mux only. These are already read by the
    # corresponding kernel resource drivers; no receiver/PHY MMIO is added.
    return (f'echo H713 EARLY HDMI stage={stage} && '
            'md.l 0x07010120 2 && md.l 0x07022004 1')


def prepare(original):
    if hashlib.sha256(original).hexdigest() != BASELINE:
        raise ValueError('installed baseline script differs; review before adapting')
    text = original.decode()
    entry = snapshot('script-entry') + '\n'
    changes = []
    for stage, anchor, after in ANCHORS:
        # Only edit commands inside the normal launch/source definitions,
        # leaving the separate logo-only fallback path unchanged.
        needle = ' && ' + anchor
        if text.count(needle) != 1:
            raise ValueError('ambiguous/missing checkpoint: ' + stage)
        replacement = (needle + ' && ' + snapshot(stage)) if after else (
            ' && ' + snapshot(stage) + needle)
        text = text.replace(needle, replacement, 1)
        changes.append((needle, replacement))
    candidate = entry + text
    restored = candidate.removeprefix(entry)
    for needle, replacement in reversed(changes):
        if restored.count(replacement) != 1:
            raise ValueError('checkpoint reversal differs')
        restored = restored.replace(replacement, needle, 1)
    if restored.encode() != original:
        raise ValueError('existing boot command/guard changed')
    return candidate.encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installed-command', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    data = prepare(args.installed_command.read_bytes())
    args.output.mkdir(exist_ok=False, parents=True)
    spec = importlib.util.spec_from_file_location(
        'startup_image', Path(__file__).with_name('build-startup.py'))
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    script = builder.legacy_image(data)
    (args.output / 'h713-hdmi.cmd').write_bytes(data)
    (args.output / 'h713-hdmi.scr').write_bytes(script)
    report = dict(
        status='PREPARED ONLY; not installed or hardware qualified',
        baseline_sha256=BASELINE,
        command_sha256=hashlib.sha256(data).hexdigest(),
        script_sha256=hashlib.sha256(script).hexdigest(),
        checkpoints=['script-entry'] + [a[0] for a in ANCHORS],
        reads={'0x07010120': 'EDID reset', '0x07010124': 'EDID clock',
               '0x07022004': 'PL8-PL15 mux; DDC is PL10-PL15'},
        original_commands_and_guards='byte-identical after removing observations',
        limits=['Serial printing adds boot time.',
                'No samples inside SPL, BL31, or either MIPS run.',
                'No HPD voltage, receiver register, or DDC transaction measurement.',
                'Clock/reset snapshots cannot exclude transient activity.'],
    )
    (args.output / 'preparation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
