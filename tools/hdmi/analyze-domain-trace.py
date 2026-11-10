#!/usr/bin/env python3
"""Compare complete proper-only control vectors; never authorize recovery."""
import argparse
import importlib.util
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('reset_trace', HERE / 'analyze-reset-trace.py')
reset = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reset)
FIELDS = ('scp_reset', 'adc_clk', 'tvfe_clk', 'i2h_clk', 'cip_tsx', 'cip_mcx',
          'cip_tsp', 'tsa_tsp', 'cip27', 'cip_mts0', 'audio_cpu', 'audio_umac',
          'audio_ihb', 'tsa432', 'mpg0', 'mpg1', 'demod_bus', 'tcd3',
          'vincap_dma', 'cap_bus', 'hdmi_audio', 'tvcap_bus')
PREFIX = 'H713 DOMAINS v1 '


def parse(path):
    baseline = reset.parse(path)
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', path.read_bytes().decode(errors='replace'))
    expected = [r for r in baseline['records'] if not r['stage'].startswith('spl_')]
    records = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if PREFIX not in line:
            continue
        tokens = line.split()
        if tokens[:3] != ['H713', 'DOMAINS', 'v1'] or len(tokens) != 4 + len(FIELDS):
            raise ValueError(f'{path}:{line_number}: incomplete/malformed control vector')
        stage = tokens[3]
        if not stage.startswith('stage='):
            raise ValueError(f'{path}:{line_number}: missing stage')
        values = {}
        for key, token in zip(FIELDS, tokens[4:]):
            match = re.fullmatch(re.escape(key) + r'=([0-9a-f]{8})', token)
            if not match:
                raise ValueError(f'{path}:{line_number}: missing/reordered/malformed {key}')
            values[key] = match[1]
        index = len(records)
        if index >= len(expected) or stage[6:] != expected[index]['stage']:
            raise ValueError(f'{path}:{line_number}: unexpected control stage')
        # Every proper reset line must be immediately followed by its control vector.
        if line_number != expected[index]['line'] + 1:
            raise ValueError(f'{path}:{line_number}: control vector detached from reset marker')
        records.append({'stage': stage[6:], 'occurrence': expected[index]['occurrence'],
                        'line': line_number, 'values': values})
    if len(records) != len(expected):
        raise ValueError(f'{path}: missing control vectors')
    return {'path': str(path), 'sha256': baseline['sha256'], 'records': records}


def compare(clean, abrupt):
    trials = {'clean': parse(clean), 'abrupt': parse(abrupt)}
    index = {name: {(r['stage'], r['occurrence']): r['values'] for r in value['records']}
             for name, value in trials.items()}
    rows = []
    for key in sorted(set(index['clean']) | set(index['abrupt'])):
        left, right = index['clean'].get(key), index['abrupt'].get(key)
        rows.append({'stage': key[0], 'occurrence': key[1],
                     'missing_trial': 'clean' if left is None else 'abrupt' if right is None else None,
                     'differences': {field: {'clean': left[field], 'abrupt': right[field]}
                                     for field in FIELDS if left and right and left[field] != right[field]}})
    return {'schema': 1, 'hardware_recovery': 'unproven', 'trials': trials,
            'comparison': rows,
            'limits': 'Control words are not DSP versions, power-good, receiver readiness or SCP SRAM freshness. Sequential reads; earlier boot effects remain.'}


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
