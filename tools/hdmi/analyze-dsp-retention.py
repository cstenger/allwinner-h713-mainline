#!/usr/bin/env python3
"""Classify completed warm version observations; never equate timeout with zero."""
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
    s, baseline = record['state'], record['baseline']
    valid = record.get('preflight_valid') is True and baseline_valid(baseline) and \
        record.get('warm_boot_id') not in (None, '', baseline['boot_id']) and \
        s.get('schema') == 'h713-dsp-retention-v1' and s.get('step') == 46 and \
        s.get('hold') == 1 and s.get('violated') == 0 and s.get('failed') == 0 and \
        s.get('timeout') == 0 and s.get('claimed') == 0 and \
        s.get('outcome0') == 1 and s.get('outcome1') == 1
    result = {'classification': 'inconclusive', 'patch_version_survives_tested_warm_path': None,
              'versions': None, 'dsp_ram_erasure': 'not directly measured',
              'automatic_hdmi_recovery': 'unproven',
              'audiotop_was_inherited': bool(s.get('interface_inherited'))}
    if not valid:
        return result
    v = [s['raw0'] & 0xffff, s['raw1'] & 0xffff]
    result['versions'] = v
    if v == [1, 1]:
        result.update(classification='patched_versions_retained', patch_version_survives_tested_warm_path=True)
    elif v == [0, 0]:
        result.update(classification='zero_versions_after_warm_access', patch_version_survives_tested_warm_path=False)
    else:
        result['classification'] = 'mixed_or_other_versions'
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('record', type=Path)
    args = p.parse_args()
    print(json.dumps(analyze(json.loads(args.record.read_text())), indent=2))


if __name__ == '__main__':
    main()
