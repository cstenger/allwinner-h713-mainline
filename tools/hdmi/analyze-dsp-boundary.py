#!/usr/bin/env python3
"""Classify stage observations without equating missing responses with loss."""
import argparse
import json
from pathlib import Path


def baseline_valid(b):
    return bool(b.get('boot_id')) and b.get('hdmi_handoff') is True and \
        b.get('tv_domains_both_on') is True and \
        all(b.get('units', {}).get(u) == 'active' for u in ('capture', 'signal', 'speaker')) and \
        any('DSP versions 0000/0000' in line for line in b.get('dsp_journal', [])) and \
        any('pinned 724-pair DSP patch verified versions 1/1' in line for line in b.get('dsp_journal', []))


def analyze(record):
    s = record['state']
    result = {'classification': 'inconclusive', 'pairs': [None] * 4,
              'first_observed_change': None, 'direct_reset_ram_erasure': 'not measured',
              'automatic_hdmi_recovery': 'unproven',
              'audiotop_was_inherited': bool(s.get('interface_inherited'))}
    if not (record.get('preflight_valid') is True and baseline_valid(record['baseline']) and
            record.get('warm_boot_id') not in (None, '', record['baseline']['boot_id']) and
            s.get('schema') == 'h713-dsp-boundary-v1' and s.get('hold') == 1 and
            not any(s.get(k, 1) for k in ('violated', 'failed', 'timeout', 'claimed'))):
        return result
    pairs = s.get('pairs')
    if not isinstance(pairs, list) or len(pairs) != 4 or any(
            not isinstance(pair, dict) or not isinstance(pair.get('raw'), list) or len(pair['raw']) != 2 or
            not all(isinstance(v, int) and 0 <= v <= 0xffffffff for v in pair['raw'])
            for pair in pairs):
        return result
    # Pair validity requires its final release/check boundary, not merely two raw slots.
    for i, end in enumerate((55, 61, 67, 73)):
        if s.get('step', 0) >= end and pairs[i].get('outcome') == [1, 1]:
            result['pairs'][i] = [v & 0xffff for v in pairs[i]['raw']]
    if result['pairs'][0] is None:
        return result
    before = result['pairs'][0]
    if before == [0, 0]:
        result['classification'] = 'zero_before_audiotop_writes'
    elif before == [1, 1]:
        result['classification'] = 'patched_before_audiotop_writes'
    else:
        result['classification'] = 'mixed_or_other_before_audiotop'
    for i, operation in enumerate(('control', 'config', 'latch'), 1):
        previous, current = result['pairs'][i - 1:i + 1]
        if previous is not None and current is not None and current != previous:
            result['first_observed_change'] = operation
            result['classification'] = 'version_change_after_audiotop_' + operation
            break
    if s.get('step') == 73 and all(p == [1, 1] for p in result['pairs']):
        result['classification'] = 'patched_across_all_audiotop_steps'
    return result


def compare(no_logo, logo):
    a, b = analyze(no_logo), analyze(logo)
    result = {'classification': 'inconclusive', 'no_logo': a, 'logo': b,
              'direct_reset_ram_erasure': 'not measured'}
    # Require verified distinct cold cycles and explicit boot-loader arm evidence.
    arms = [(no_logo, 'no-logo'), (logo, 'one-logo')]
    for record, arm in arms:
        proof = record.get('arm_proof', {})
        if not proof.get('verified') or proof.get('arm') != arm or \
                proof.get('cold_boot_id') != record['baseline']['boot_id'] or \
                proof.get('warm_boot_id') != record.get('warm_boot_id'):
            return result
    if no_logo['baseline']['boot_id'] == logo['baseline']['boot_id'] or \
            no_logo.get('warm_boot_id') == logo.get('warm_boot_id'):
        return result
    if not no_logo['arm_proof'].get('fit_sha256') or no_logo['arm_proof']['fit_sha256'] != logo['arm_proof'].get('fit_sha256'):
        return result
    x, y = a['pairs'][0], b['pairs'][0]
    if x == [1, 1] and y == [0, 0]:
        result['classification'] = 'logo_path_difference_requires_replication'
    elif x == [0, 0]:
        result['classification'] = 'zero_observed_without_warm_logo_or_audiotop_writes'
    elif x == y == [1, 1]:
        result['classification'] = 'patched_before_audiotop_in_both_arms'
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('record', type=Path)
    p.add_argument('--logo-record', type=Path)
    args = p.parse_args()
    record = json.loads(args.record.read_text())
    out = compare(record, json.loads(args.logo_record.read_text())) if args.logo_record else analyze(record)
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    main()
