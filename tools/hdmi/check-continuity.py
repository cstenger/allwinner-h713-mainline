#!/usr/bin/env python3
"""Offline phase/amplitude screen of 48-kHz stereo S16_LE capture seconds 3–9.

The stimulus must be left 1 kHz/right 2 kHz. Metrics are not pass/fail criteria
or proof against all dropped/repeated samples, especially whole tone cycles.
"""
import argparse
import json
from pathlib import Path
import sys
import wave

import numpy as np

RATE = 48000
BLOCK_FRAMES = 960
START_SECOND = 3
END_SECOND = 9
LIMITATION = ('Periodic tones cannot detect every drop/repeat, including an integer '
              'number of tone cycles; this is not a long-term stability test or a '
              'check that the expected tone is present.')


def measure(samples, frequency):
    samples = np.asarray(samples)
    if samples.ndim != 1 or len(samples) < 2 * BLOCK_FRAMES or len(samples) % BLOCK_FRAMES:
        raise ValueError('need at least two complete 960-frame blocks in one channel')
    if not np.all(np.isfinite(samples)):
        raise ValueError('samples must be finite')
    blocks = samples.reshape(-1, BLOCK_FRAMES).astype(float)
    carrier = np.exp(-2j * np.pi * frequency * np.arange(BLOCK_FRAMES) / RATE)
    correlated = blocks @ carrier
    amplitude = np.abs(correlated)
    median_amplitude = float(np.median(amplitude))
    if median_amplitude <= 0 or not np.isfinite(median_amplitude):
        raise ValueError('no usable median tone amplitude; phase/relative amplitude undefined')
    steps = np.diff(np.unwrap(np.angle(correlated)))
    return {
        'max_residual_phase_step_rad': float(np.max(np.abs(steps - np.median(steps)))),
        'min_relative_amplitude': float(np.min(amplitude) / median_amplitude),
    }


def analyze_wave(path):
    with wave.open(str(path), 'rb') as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth(), wav.getcomptype()) != (RATE, 2, 2, 'NONE'):
            raise ValueError(f'{path}: expected 48-kHz stereo S16_LE PCM WAV')
        if wav.getnframes() < END_SECOND * RATE:
            raise ValueError(f'{path}: recording must reach second {END_SECOND}')
        wav.setpos(START_SECOND * RATE)
        frames = (END_SECOND - START_SECOND) * RATE
        raw = wav.readframes(frames)
    if len(raw) != frames * 4:
        raise ValueError(f'{path}: truncated recording in analysis window')
    samples = np.frombuffer(raw, dtype='<i2').reshape(-1, 2)
    return [measure(samples[:, i], frequency) for i, frequency in enumerate((1000, 2000))]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('captures', nargs='+', type=Path, help='explicit capture WAV paths')
    parser.add_argument('--output', required=True, type=Path, help='new JSON report path')
    args = parser.parse_args(argv)
    if args.output.suffix.lower() != '.json':
        parser.error('--output must have a .json suffix')
    captures = [path.resolve() for path in args.captures]
    if len(captures) != len(set(captures)):
        parser.error('capture paths must be distinct')
    if args.output.resolve() in captures:
        parser.error('output must differ from every input')
    if args.output.exists():
        parser.error('output already exists; choose a new report path')
    try:
        result = {
            'method': '960-frame blocks, seconds 3–9; subtract median phase increment to allow clock drift',
            'limitation': LIMITATION,
            'trials': {str(path): analyze_wave(path) for path in captures},
        }
        text = json.dumps(result, indent=2, allow_nan=False) + '\n'
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x') as output:
            output.write(text)
    except (OSError, ValueError, EOFError, wave.Error) as error:
        print(f'continuity analysis failed: {error}', file=sys.stderr)
        return 1
    print(text, end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
