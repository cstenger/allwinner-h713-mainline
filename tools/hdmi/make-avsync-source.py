#!/usr/bin/env python3
"""Build a lossless 720p60 HDMI flash/beep source with exact frame/sample onsets."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

RATE = 60
AUDIO_RATE = 48000
CYCLE_FRAMES = 504
EVENT_FRAMES = (0, 42, 108, 162, 246, 294, 366, 426)


def build(output, seconds=42):
    if not 20 <= seconds <= 120:
        raise ValueError('source duration must be 20..120 seconds')
    frames = round(seconds*RATE)
    if abs(frames-seconds*RATE) > 1e-6 or frames % CYCLE_FRAMES:
        raise ValueError('duration must contain whole 8.4-second cycles')
    output.mkdir(parents=True, exist_ok=False)
    video_on = '+'.join(f'between(mod(n\\,{CYCLE_FRAMES})\\,{f}\\,{f+3})' for f in EVENT_FRAMES)
    samples_per_frame = AUDIO_RATE // RATE
    cycle_samples = CYCLE_FRAMES * samples_per_frame
    audio_on = '+'.join(f'between(mod(n\\,{cycle_samples})\\,{f*samples_per_frame}\\,{f*samples_per_frame+2399})' for f in EVENT_FRAMES)
    clip = output/'hdmi-avsync-720p60.mkv'
    cmd = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
           '-f', 'lavfi', '-i', f"color=c=black:s=1280x720:r={RATE}:d={seconds},drawbox=color=white:t=fill:enable='{video_on}'",
           '-f', 'lavfi', '-i', f"aevalsrc='0.3*sin(2*PI*1000*n/{AUDIO_RATE})*({audio_on})':s={AUDIO_RATE}:d={seconds}",
           '-c:v', 'ffv1', '-level', '3', '-pix_fmt', 'yuv420p',
           '-c:a', 'pcm_s16le', '-ac', '2', '-shortest', str(clip)]
    subprocess.run(cmd, check=True)
    manifest = {'clip': clip.name, 'sha256': hashlib.sha256(clip.read_bytes()).hexdigest(),
                'seconds': seconds, 'video_fps': RATE, 'audio_rate': AUDIO_RATE,
                'cycle_frames': CYCLE_FRAMES, 'event_frames': EVENT_FRAMES,
                'flash_frames': 4, 'beep_samples': 2400,
                'note': 'Onsets share integer frame/sample boundaries; tone starts at a sine zero crossing.'}
    (output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(clip)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--seconds', type=float, default=42)
    args = parser.parse_args()
    build(args.output, args.seconds)
