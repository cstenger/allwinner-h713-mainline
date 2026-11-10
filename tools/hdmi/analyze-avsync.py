#!/usr/bin/env python3
"""Summarize electronic flash/beep pairs; never apply a delay automatically."""
import argparse
import json
import math
from pathlib import Path
import re
import statistics


def percentile(values, fraction):
    values = sorted(values)
    p = (len(values)-1)*fraction
    a = int(p)
    b = min(a+1, len(values)-1)
    return values[a] + (values[b]-values[a])*(p-a)


def analyze(text, current_delay=0.0):
    pairs = []
    for line in text.splitlines():
        if line.startswith('PAIR_CSV,'):
            _, flash, beep, offset = line.split(',')
            flash, beep, offset = map(float, (flash, beep, offset))
            if not all(math.isfinite(v) for v in (flash, beep, offset)):
                raise ValueError('non-finite event')
            if abs((beep-flash)*1000-offset) > .002:
                raise ValueError('event timestamps disagree with offset')
            if pairs and (flash <= pairs[-1][0] or beep <= pairs[-1][1]):
                raise ValueError('duplicate or unordered event pairing')
            pairs.append((flash, beep, offset))
    counts = re.search(r'^flashes (\d+), beeps (\d+)$', text, re.M)
    if counts is None or len(pairs) < 8:
        raise ValueError('need event counts and at least eight matched events')
    nf, nb = map(int, counts.groups())
    if min(nf, nb) < len(pairs) or len(pairs)/max(nf, nb) < .8:
        raise ValueError('insufficient flash/beep match coverage')
    if pairs[-1][0]-pairs[0][0] < 8:
        raise ValueError('observation shorter than one irregular event cycle')
    if not math.isfinite(current_delay) or not 0 <= current_delay <= .5:
        raise ValueError('invalid existing audio delay')
    x = [p[0]-pairs[0][0] for p in pairs]
    y = [p[2] for p in pairs]
    mx, my = statistics.mean(x), statistics.mean(y)
    slope = sum((a-mx)*(b-my) for a, b in zip(x, y))/sum((a-mx)**2 for a in x)
    median = statistics.median(y)
    requested = current_delay-median/1000
    return {'measurement': 'electronic display-plane / codec-monitor estimate',
            'sign': 'positive means audio late', 'matched': len(pairs),
            'flashes': nf, 'beeps': nb, 'span_sec': x[-1],
            'offset_ms': {'median': median, 'p05': percentile(y, .05),
                          'p95': percentile(y, .95), 'min': min(y), 'max': max(y)},
            'within_window_slope_ms_per_min': slope*60,
            'current_audio_delay_sec': current_delay,
            'audio_timing_correction_sec': -median/1000,
            'electronic_only_candidate_delay_sec': min(.5, max(0, requested)) if current_delay else None,
            'candidate_note': 'Local estimate only: PipeWire subtracts stream latency from its target delay. A zero target does not identify intrinsic latency; measure a nonzero trial first. Re-measure every candidate.',
            'candidate_outside_supported_range': not 0 <= requested <= .5,
            'qualification': 'DRM state can precede scanout by one vblank; panel/acoustic latency unmeasured. Confirm projected flash/speaker sync with calibrated camera. Short-window slope is not a long-run drift verdict.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    parser.add_argument('--current-delay', type=float, default=0)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = json.dumps(analyze(args.log.read_text(), args.current_delay), indent=2)+'\n'
    if args.output:
        with args.output.open('x') as f: f.write(result)
    print(result, end='')
