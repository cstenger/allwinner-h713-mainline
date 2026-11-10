#!/usr/bin/env python3
"""Generate a 48-kHz stereo WAV and JSON schedule for speaker calibration."""
import argparse
import json
import math
from pathlib import Path
import struct
import wave

RATE = 48000
DURATION = 56


def build(output):
    if output.suffix.lower() != ".wav":
        raise ValueError("output must have a .wav suffix; the schedule uses .json")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Ten seconds of digital silence distinguishes HDMI stream activation
    # from the first tone. No hard waveform edges should create test clicks.
    segments = [dict(start=10 + i * .3, duration=.15, dbfs=-30, hz=600, label='marker')
                for i in range(3)]
    segments += [dict(start=14 + i * 6, duration=4, dbfs=db, hz=1000,
                      label=f'1 kHz, {db} dBFS peak')
                 for i, db in enumerate((-36, -30, -24, -18, -12, -6))]
    with wave.open(str(output), 'wb') as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        for second in range(DURATION):
            block = bytearray()
            for n in range(second * RATE, (second + 1) * RATE):
                t = n / RATE
                sample = 0.0
                for segment in segments:
                    local = t - segment['start']
                    if 0 <= local < segment['duration']:
                        edge = min(.15, segment['duration'] / 2)
                        envelope = min(1.0, local / edge,
                                       (segment['duration'] - local) / edge)
                        envelope = .5 - .5 * math.cos(math.pi * envelope)
                        sample += envelope * 10 ** (segment['dbfs'] / 20) * math.sin(
                            2 * math.pi * segment['hz'] * local)
                value = round(sample * 32767)
                block += struct.pack('<hh', value, value)
            wav.writeframesraw(block)
    output.with_suffix('.json').write_text(json.dumps({
        'rate': RATE, 'channels': 2, 'duration_seconds': DURATION,
        'format': 'S16_LE', 'segments': segments,
        'instructions': 'One phone recording: begin before board power-on; keep fixed distance; '
                        'continue through boot and this entire WAV. Silence at WAV 0-10s '
                        'tests stream activation; tones are peak levels, not RMS.'
    }, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    try:
        build(args.output)
    except ValueError as error:
        parser.error(str(error))
