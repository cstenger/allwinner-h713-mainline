#!/usr/bin/env python3
"""Compare one clean-reset and one abrupt-reset raw UART log, without pass claims.

Each log must contain exactly one proper_preboot marker. Keep raw full captures
and extract the post-reset interval before analysis; mixed boots are rejected.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

PREFIX = 'H713 RESET v1 '
STAGES = ('spl_pre_dram', 'spl_post_dram', 'proper_preboot',
          'pre_workspace', 'post_logo', 'manual')
PATTERN = re.compile(
    r'H713 RESET v1 stage=(\w+) gp6=([0-9a-f]{8}) gp7=([0-9a-f]{8}) '
    r'mips_clk=([0-9a-f]{8}) mips_reset=([0-9a-f]{8}) '
    r'mips_status=([0-9a-f]{8}|unread)')
FIELDS = ('gp6', 'gp7', 'mips_clk', 'mips_reset', 'mips_status')


def parse(path):
    data = path.read_bytes()
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', data.decode(errors='replace'))
    records = []
    counts = {}
    for line_number, line in enumerate(text.splitlines(), 1):
        if PREFIX not in line:
            continue
        match = PATTERN.fullmatch(line)
        if not match or match[1] not in STAGES:
            raise ValueError(f'{path}:{line_number}: malformed/unknown reset marker')
        stage = match[1]
        if match[6] == 'unread' and not stage.startswith('spl_'):
            raise ValueError(f'{path}:{line_number}: missing proper MIPS status')
        counts[stage] = counts.get(stage, 0) + 1
        records.append({'stage': stage, 'occurrence': counts[stage],
                        'line': line_number, **dict(zip(FIELDS, match.groups()[1:]))})
    if counts.get('proper_preboot') != 1:
        raise ValueError(f'{path}: expected exactly one proper_preboot marker; mixed or missing boot')
    if any(counts.get(stage, 0) > 1 for stage in ('spl_pre_dram', 'spl_post_dram')):
        raise ValueError(f'{path}: repeated SPL stages; mixed boot')
    preboot = next(i for i, row in enumerate(records) if row['stage'] == 'proper_preboot')
    if any(not row['stage'].startswith('spl_') for row in records[:preboot]):
        raise ValueError(f'{path}: proper stages precede proper_preboot; mixed boot')
    if any(row['stage'].startswith('spl_') for row in records[preboot:]):
        raise ValueError(f'{path}: SPL stage after proper_preboot; mixed boot')
    if [row['stage'] for row in records[:preboot]] not in (
            [], ['spl_pre_dram'], ['spl_post_dram'], ['spl_pre_dram', 'spl_post_dram']):
        raise ValueError(f'{path}: invalid SPL stage order')
    return {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest(),
            'records': records,
            'coverage': {stage: counts.get(stage, 0) for stage in STAGES}}


def compare(clean, abrupt):
    trials = {'clean': parse(clean), 'abrupt': parse(abrupt)}
    indexed = {trial: {(r['stage'], r['occurrence']): r for r in value['records']}
               for trial, value in trials.items()}
    rows = []
    for stage, occurrence in sorted(set(indexed['clean']) | set(indexed['abrupt'])):
        left = indexed['clean'].get((stage, occurrence))
        right = indexed['abrupt'].get((stage, occurrence))
        rows.append({'stage': stage, 'occurrence': occurrence,
                     'missing_trial': 'clean' if left is None else 'abrupt' if right is None else None,
                     'differences': {field: {'clean': left[field], 'abrupt': right[field]}
                                     for field in FIELDS if left and right and left[field] != right[field]}})
    return {'schema': 1, 'hardware_recovery': 'unproven', 'trials': trials,
            'comparison': rows,
            'limits': 'Values are stage-specific observations; equality is not reset, DSP freshness, or recovery proof.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clean', required=True, type=Path)
    parser.add_argument('--abrupt', required=True, type=Path)
    args = parser.parse_args()
    try:
        result = compare(args.clean, args.abrupt)
    except (OSError, ValueError) as error:
        parser.exit(2, str(error) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
