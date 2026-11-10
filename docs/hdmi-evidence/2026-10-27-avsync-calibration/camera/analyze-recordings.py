#!/usr/bin/env python3
"""Reproduce these three recordings' slow-motion timing measurements.

Requires ffmpeg, ffprobe, numpy. Run from repository root. Normal/ramp portions
are excluded explicitly; do not generalize these bounds to a different movie.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import numpy as np

OUTPUT = Path(__file__).resolve().parent
SOURCE_GAPS = np.array([.7, 1.1, .9, 1.4, .8, 1.2, 1., 1.3])
RATE = 48000
SLOW = 8


def decode(path):
    meta = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)]))
    frames = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json', str(path)]))
    t = np.array([float(f['best_effort_timestamp_time']) for f in frames['frames']])
    v = np.frombuffer(subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(path), '-map', '0:v:0', '-vf', 'crop=200:200:860:440,scale=1:1', '-pix_fmt', 'gray', '-f', 'rawvideo', '-']), dtype=np.uint8).astype(float)
    audio = np.frombuffer(subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(path), '-map', '0:a:0', '-ac', '1', '-ar', str(RATE), '-f', 'f32le', '-']), dtype='<f4')
    assert len(t) == len(v) and np.all(np.diff(t) > 0)
    # 40 ms lock-in window at the slowed 1 kHz tone, centred every 5 ms.
    n = 1920
    z = audio*np.exp(-2j*np.pi*(1000/SLOW)*np.arange(len(audio))/RATE)
    cumulative = np.r_[0, np.cumsum(z)]
    idx = np.arange(n, len(audio), 240)
    envelope = abs(cumulative[idx]-cumulative[idx-n])/n
    return meta, t, v, (idx-n/2)/RATE, envelope


def measure(t, v, at, e, start, end, video_fraction=.5, audio_fraction=.5):
    lo, hi = np.percentile(v, [20, 98])
    threshold = lo+video_fraction*(hi-lo)
    vi = np.flatnonzero((v[1:] > threshold) & (v[:-1] <= threshold))+1
    vi = vi[(t[vi] > start) & (t[vi] < end)]
    flashes = (t[vi]+t[vi-1])/2
    assert len(flashes) >= 5
    # Source's irregular gap order independently checks the 8x time scale.
    fits = []
    for phase in range(8):
        source = np.r_[0, np.cumsum([SOURCE_GAPS[(phase+j) % 8] for j in range(len(flashes)-1)])]
        slope, intercept = np.polyfit(source, flashes, 1)
        fits.append((float(np.max(abs(flashes-(source*slope+intercept)))), slope, phase))
    residual, fitted_slow, phase = min(fits)
    assert abs(fitted_slow-SLOW) < .1 and residual < .2, (fitted_slow, residual)
    pairs = []
    for i, flash in zip(vi, flashes):
        region = np.flatnonzero(abs(at-flash) < .8)
        local = e[region]
        floor = float(np.percentile(local, 20))
        peak = float(np.max(local))
        threshold = floor+audio_fraction*(peak-floor)
        crossing = region[1:][(local[1:] >= threshold) & (local[:-1] < threshold)]
        assert len(crossing) >= 1, (flash, len(crossing))
        # Envelope may recross on the trailing echo of the same 0.4 s beep.
        assert at[crossing[-1]]-at[crossing[0]] < .65, (flash, at[crossing])
        j = crossing[0]
        beep = at[j-1]+(at[j]-at[j-1])*(threshold-e[j-1])/(e[j]-e[j-1])
        pairs.append({'flash_frame': int(i), 'flash_midpoint_export_sec': float(flash),
                      'beep_export_sec': float(beep),
                      'audio_minus_flash_real_ms': float((beep-flash)*1000/SLOW)})
    assert all(b['beep_export_sec'] > a['beep_export_sec'] for a, b in zip(pairs, pairs[1:]))
    values = np.array([p['audio_minus_flash_real_ms'] for p in pairs])
    return {'pairs': pairs, 'paired': len(pairs), 'cadence_fit_slow_factor': float(fitted_slow),
            'cadence_fit_max_export_residual_sec': residual, 'source_gap_phase': phase,
            'offset_ms': dict(zip(['min', 'p05', 'median', 'p95', 'max'], map(float, np.percentile(values, [0, 5, 50, 95, 100])))),
            'real_span_sec': float((flashes[-1]-flashes[0])/SLOW)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only', choices=('baseline', 'test', 'test2'))
    args = parser.parse_args()
    for name, start, end in [('baseline', 4, 46), ('test', 8, 111), ('test2', 8, 134)]:
        if args.only and name != args.only:
            continue
        path = Path('local/lcd-photos/test_111')/(name+'.mov')
        meta, t, v, at, envelope = decode(path)
        result = measure(t, v, at, envelope, start, end)
        sensitivity = []
        for vf in (.25, .5, .75):
            for af in (.25, .5, .75):
                sensitivity.append({'video_fraction': vf, 'audio_fraction': af,
                                    'median_ms': measure(t, v, at, envelope, start, end, vf, af)['offset_ms']['median']})
        result.update({'file': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                       'slow_export_region_sec': [start, end], 'retime_factor': SLOW,
                       'audio_detector_hz': 1000/SLOW, 'real_frame_interval_ms': 1000/(30*SLOW),
                       'threshold_sensitivity': sensitivity,
                       'qualification': 'Uncalibrated camera A/V and slow-motion export bias; sound propagation included. No visible simultaneous physical/acoustic calibration reference identified. Short real-time span does not qualify drift. AAC decoded with original edit/skip metadata; no manual priming subtraction.'})
        (OUTPUT/(name+'-slow-analysis.json')).write_text(json.dumps(result, indent=2)+'\n')
        (OUTPUT/(name+'-metadata.json')).write_text(json.dumps(meta, indent=2)+'\n')
        np.savez(OUTPUT/(name+'-slow-signals.npz'), video_pts=t, brightness=v, audio_pts=at, tone_envelope=envelope)
        print(name, result['offset_ms'], 'paired', result['paired'], 'cadence', result['cadence_fit_slow_factor'], flush=True)


if __name__ == '__main__':
    main()
