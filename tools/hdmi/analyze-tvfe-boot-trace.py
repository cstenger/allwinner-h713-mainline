#!/usr/bin/env python3
"""Find observed TVFE ON->OFF intervals; missing samples never prove a writer."""
import argparse
import json
from pathlib import Path
import re

MARKER = re.compile(r'H713 TVFE v1 stage=(\w+) gate=([0-9a-f]{8}) state=(begin|skipped|sample)(?: tvfe=([0-9a-f]{8}) tvcap=([0-9a-f]{8}))?\s*$')
REQUIRED = ('linux_early_initcall', 'ppu_probe_entry', 'ppu_before_reset_deassert',
            'ppu_after_reset_deassert', 'ppu_before_clock_enable',
            'ppu_after_clock_enable', 'ppu_probe_complete')
UBOOT = ('uboot_final_entry', 'uboot_before_quiesce', 'uboot_after_quiesce',
         'uboot_before_dm_remove', 'uboot_after_dm_remove')
DOMAIN_INIT = ('domain_init_before', 'domain_init_after_wait',
               'domain_init_after_on_delay', 'domain_init_after_off_delay')


def analyze(text, require_uboot=False):
    if len(re.findall(r'Linux version 6\.18\.38', text)) > 1:
        raise ValueError('multiple Linux boots; split evidence by boot')
    samples, skipped, pending = [], [], set()
    for line_no, line in enumerate(text.splitlines(), 1):
        if 'H713 TVFE v1 stage=' not in line:
            continue
        m = MARKER.search(line)
        if not m:
            raise ValueError('malformed marker at line %d' % line_no)
        stage, gate_hex, state, tvfe, tvcap = m.groups()
        gate = int(gate_hex, 16)
        if state == 'begin':
            if stage in pending:
                raise ValueError('overlapping same-stage samples; cannot pair observations')
            pending.add(stage)
            continue
        if stage not in pending:
            raise ValueError('sample without BEGIN at line %d' % line_no)
        pending.remove(stage)
        if state == 'skipped':
            if (gate & 0x10001) == 0x10001:
                raise ValueError('skip marker inconsistent with open bus')
            skipped.append({'stage': stage, 'line': line_no, 'gate': gate_hex})
            continue
        if (gate & 0x10001) != 0x10001 or tvfe is None or tvcap is None:
            raise ValueError('unsafe/incomplete PPU sample at line %d' % line_no)
        samples.append({'stage': stage, 'line': line_no, 'gate': gate_hex,
                        'tvfe': tvfe, 'tvcap': tvcap,
                        'tvfe_state': {0x10000: 'on', 0x20000: 'off'}.get(int(tvfe, 16) & 0x30000, 'unknown')})
    seen = {s['stage'] for s in samples}
    missing = [s for s in REQUIRED + (UBOOT if require_uboot else ()) if s not in seen]
    # The exact production driver initializes all five physical domains.
    counts = {stage: sum(s['stage'] == stage for s in samples) for stage in DOMAIN_INIT}
    missing.extend(stage + ' (expected 5 samples)' for stage, count in counts.items() if count != 5)
    transitions = []
    for before, after in zip(samples, samples[1:]):
        if before['tvfe_state'] == 'on' and after['tvfe_state'] == 'off':
            transitions.append({'last_on': before, 'first_off': after})
    return {'schema': 1, 'samples': samples, 'skipped': skipped,
            'incomplete_begin_stages': sorted(pending), 'missing_sample_stages': missing,
            'domain_init_sample_counts': counts,
            'coverage': 'complete' if not (pending or missing) else 'incomplete',
            'on_to_off_intervals': transitions,
            'first_observed_off': next((s for s in samples if s['tvfe_state'] == 'off'), None),
            'writer': 'unproven; correlate command/caller and refine the observed interval',
            'dsp_retention': 'not measured', 'automatic_hdmi_recovery': 'unproven',
            'samples_are_sequential_not_atomic': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    parser.add_argument('--require-uboot', action='store_true')
    args = parser.parse_args()
    print(json.dumps(analyze(args.log.read_text(errors='replace'), args.require_uboot), indent=2))


if __name__ == '__main__':
    main()
