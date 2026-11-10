#!/usr/bin/env python3
"""Unique audio markers measure source-relative sample drift in fixed48k PCM."""
import importlib.util
import math
import wave
from pathlib import Path
import numpy as np

RATE = 48000
MARKER_FRAMES = 16384
INTERVAL = 30
spec = importlib.util.spec_from_file_location('tone_analysis', Path(__file__).with_name('audio-rate-analysis.py'))
tone_analysis = importlib.util.module_from_spec(spec); spec.loader.exec_module(tone_analysis)


def marker(index):
    noise = np.random.default_rng(713000+index).standard_normal(MARKER_FRAMES)
    smooth = np.convolve(noise, np.hanning(33), mode='same')
    smooth -= smooth.mean()
    return np.rint(smooth * (12000/np.max(np.abs(smooth)))).astype('<i2')


def marker_frames(seconds):
    return list(range(2*RATE, (seconds-11)*RATE, INTERVAL*RATE))


def make_source(path, seconds):
    """Write one second at a time; RAM use does not grow with duration."""
    positions = {frame//RATE: i for i,frame in enumerate(marker_frames(seconds))}
    t = np.arange(RATE)/RATE
    tone = np.column_stack([6500*np.sin(2*np.pi*f*t) for f in (1000,2000)]).astype('<i2')
    with wave.open(str(path), 'wb') as wav:
        wav.setnchannels(2); wav.setsampwidth(2); wav.setframerate(RATE)
        for second in range(seconds-6):
            samples = tone.copy() if second < seconds-10 else np.zeros_like(tone)
            if second in positions:
                samples[:MARKER_FRAMES,0] = marker(positions[second])
            wav.writeframesraw(samples.tobytes())


def locate(samples, template):
    """Normalized matched filter; subframe quadratic peak interpolation."""
    x = samples.astype(float)
    y = template.astype(float); y -= y.mean()
    n = 1 << math.ceil(math.log2(len(x)+len(y)-1))
    numerator = np.fft.irfft(np.fft.rfft(x,n)*np.conj(np.fft.rfft(y,n)),n)[:len(x)-len(y)+1]
    sums = np.concatenate(([0.],np.cumsum(x)))
    squares = np.concatenate(([0.],np.cumsum(x*x)))
    m = len(y)
    energy = np.maximum(squares[m:]-squares[:-m]-(sums[m:]-sums[:-m])**2/m,0)
    denominator = np.sqrt(energy*np.sum(y*y))
    score = np.divide(numerator,denominator,out=np.zeros_like(numerator),where=denominator>0)
    peak = int(np.argmax(score)); delta = 0.
    if 0 < peak < len(score)-1:
        a,b,c = score[peak-1:peak+2]
        if a-2*b+c: delta = float(.5*(a-c)/(a-2*b+c))
    return peak+delta,float(score[peak])


def analyze_raw(path, seconds):
    if path.stat().st_size != seconds*RATE*4:
        raise RuntimeError('unexpected raw capture frame count')
    checks=[]
    with path.open('rb') as stream:
        for index,source_frame in enumerate(marker_frames(seconds)):
            # Five seconds covers startup latency and up to1000ppm relative
            # drift over an hour. Unique templates reject replayed old markers.
            start=max(0,source_frame-5*RATE)
            end=min(seconds*RATE,source_frame+5*RATE+MARKER_FRAMES)
            stream.seek(start*4)
            data=np.frombuffer(stream.read((end-start)*4),dtype='<i2').reshape(-1,2)
            offset,score=locate(data[:,0],marker(index))
            frame=start+offset
            stream.seek((round(frame)+RATE)*4)
            tone=tone_analysis.analyze(stream.read(MARKER_FRAMES*4))
            checks.append({'index':index,'source_frame':source_frame,'capture_frame':frame,
                           'correlation':score,'tone_pass':tone['tone_pass'] and tone['capture_rate_hz']==RATE})
        stream.seek((seconds-1)*RATE*4)
        silent=not any(stream.read(RATE*4))
    if len(checks)<3: raise RuntimeError('need at least three timing markers')
    x=np.array([c['source_frame'] for c in checks],dtype=float)
    y=np.array([c['capture_frame'] for c in checks])
    slope,offset=np.polyfit(x,y,1)
    residual=y-(slope*x+offset)
    ppm=float((slope-1)*1e6)
    maximum=float(np.max(np.abs(residual)))
    # Smooth clock wander can curve the hour-long fit. Gate sudden changes
    # between equal-length marker intervals, not accumulated fit curvature.
    interval_change=float(np.max(np.abs(np.diff(y,n=2))))
    passed=(all(c['correlation']>=.65 and c['tone_pass'] for c in checks)
            and silent and abs(ppm)<=1000 and interval_change<=48)
    return {'pass':bool(passed),'frames':seconds*RATE,'marker_count':len(checks),
            'source_relative_drift_ppm':ppm,'latency_offset_frames':float(offset),
            'maximum_timing_residual_frames':maximum,
            'maximum_adjacent_interval_change_frames':interval_change,
            'rms_timing_residual_frames':float(np.sqrt(np.mean(residual**2))),
            'final_second_all_zero':silent,'markers':checks,
            'acceptance':{'minimum_correlation':.65,'maximum_absolute_drift_ppm':1000,
                          'maximum_adjacent_interval_change_frames':48}}


def analyze_clock(samples):
    """Capture cadence relative to board CLOCK_MONOTONIC_RAW, not UTC accuracy."""
    if len(samples)<3: raise RuntimeError('need at least three board clock samples')
    x=np.array([(s['before_raw']+s['after_raw'])/2 for s in samples])
    x-=x[0]
    y=np.array([s['hw_ptr'] for s in samples],dtype=float)
    slope,offset=np.polyfit(x,y,1)
    return {'samples':len(samples),'frames_per_board_raw_second':float(slope),
            'capture_vs_board_raw_ppm':float((slope/RATE-1)*1e6),
            'maximum_read_uncertainty_seconds':max((s['after_raw']-s['before_raw'])/2 for s in samples),
            'maximum_residual_frames':float(np.max(np.abs(y-(slope*x+offset))))}
