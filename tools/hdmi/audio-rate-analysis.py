#!/usr/bin/env python3
"""Analyze stereo S16_LE diagnostic rings without assuming a capture rate."""
import numpy as np

RATES = (32000, 44100, 48000)


def analyze(data):
    if len(data) != 65536:
        raise ValueError("expected the private 64 KiB stereo S16_LE ring")
    samples = np.frombuffer(data, dtype="<i2").reshape(-1, 2).astype(float)
    channels = []
    for channel, tone in enumerate((1000, 2000)):
        x = samples[:, channel]
        power = abs(np.fft.rfft((x - x.mean()) * np.hanning(len(x)))) ** 2
        frequencies = np.fft.rfftfreq(len(x))
        peak = int(np.argmax(power[1:]) + 1)
        # Interpolate the Hann peak in log power; the ring can have a wrap seam.
        delta = 0.0
        if 0 < peak < len(power) - 1 and power[peak] > 0:
            a, b, c = np.log(np.maximum(power[peak-1:peak+2], 1e-30))
            if a - 2*b + c:
                delta = float(.5 * (a-c) / (a-2*b+c))
        cycles_per_sample = (peak + delta) / len(x)
        inferred = tone / cycles_per_sample if power.sum() else None
        candidates = {}
        for rate in RATES:
            hz = frequencies * rate
            total = float(power.sum())
            fraction = lambda target: float(power[abs(hz-target) <= 30].sum()) / total if total else 0.0
            candidates[str(rate)] = {"tone_fraction": fraction(tone),
                                     "opposite_fraction": fraction(3000-tone)}
        channels.append({"rms": float(np.sqrt(np.mean(x*x))),
                         "peak": float(abs(x).max()), "dc": float(x.mean()),
                         "inferred_capture_hz": inferred, "candidates": candidates})
    matches = [rate for rate in RATES if all(
        c["inferred_capture_hz"] is not None
        and abs(c["inferred_capture_hz"] / rate - 1) < .01
        and c["candidates"][str(rate)]["tone_fraction"] >= .90
        and c["candidates"][str(rate)]["opposite_fraction"] < .005
        and 2500 < c["rms"] < 6000 and c["peak"] < 30000
        and abs(c["dc"]) < 100 for c in channels)]
    return {"channels": channels, "capture_rate_hz": matches[0] if len(matches) == 1 else None,
            "tone_pass": len(matches) == 1,
            "silence_pass": all(c["rms"] <= 4 for c in channels)}
