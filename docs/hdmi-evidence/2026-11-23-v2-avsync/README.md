# V2 HDMI speaker delay check — November 23, 2026

**Result: keep 0.115 s on the V2.** The HY200_QZ713_V2 at the bench board's
delay measures +19.5 ms (audio after flash) on the phone, the same as the
bench board's +18.9 ms at the same delay. Corrected for the phone's own
bias, that is about −5..+14 ms. Positive means audio late.

## Setup

- **Board:** V2, slot A, U-Boot 0019 loaded over FEL (boot `6e6289a5`, the
  last boot of the 2026-11-23 logo→FEL chain), kernel 0221. The speaker
  service ran `pw-loopback --latency=20 --delay=0.115` from the rootfs's
  `/etc/default/h713-hdmi-speaker`. Capture and speaker PCMs were RUNNING.
- **Source:** the same PC, playing the 2026-10-27 clip
  (`build/hdmi-avsync-2026-10-27/source-v2/hdmi-avsync-720p60.mkv`, sha256
  `fb40949d…`, irregular full-screen flashes with simultaneous 1 kHz beeps)
  with mpv: full screen on HDMI-A-1 (EDID `H713 HDMI IN`, 1280×720), audio to
  `alsa_output.pci-0000_0c_00.1.hdmi-stereo`, volume 100. mpv reported
  60 fps, 0 dropped frames, A/V error 0.
- **Recording:** `IMG_1136.MOV`, iPhone 17 Pro, 4K at 30 fps, normal speed,
  46.2 s, kept in `local/lcd-photos/test_120/` (hash in
  [recordings.sha256](recordings.sha256)).
- **Phone bias:** same phone model and mode as the 2026-11-18 pen-tap clip
  `IMG_1118`, so its bound applies: the phone's audio is 6..24 ms late
  relative to its video
  ([tap-bias-IMG_1118.json](../2026-11-18-avsync-recalibration/tap-bias-IMG_1118.json)).
- **Analyzer:** the 2026-10-27
  [`camera/analyze-recordings.py`](../2026-10-27-avsync-calibration/camera/analyze-recordings.py)
  with `--slow 1`, unchanged.

## Measurements

| Window (recording s) | Pairs | Median (ms) | p05..p95 | Threshold sweep medians |
| --- | ---: | ---: | --- | --- |
| 0.3–40.2, first play | 38 | **+19.5** | +15.6..+29.0 | +7.7..+31.3 |
| 40.2–45.9, after the mpv loop seam | 6 | +39.1 | — | +11.0..+49.5 |

- In the first window, 36 of 38 pairs lie between +15 and +25 ms. The two
  outliers (+54.6, +50.7) are about one camera frame (33 ms) late, consistent
  with the flash crossing the patch threshold a frame early.
- The offset stepped by about +20 ms at the mpv loop seam (clip end at
  recording ~40.6 s). The 2026-11-18 bench recording also stepped across a
  seam (+11.2 → +20.0 ms). The board's loopback runs continuously, so this is
  most likely the host player restarting its audio. Only the first window is
  used for the result.
- Corrected for the phone bias: +19.5 − (6..24) = **−4.5..+13.5 ms**. The bench
  board at 0.115 s gave −5..+13 ms on 2026-11-18.

## Limits

Same as 2026-11-18: phone bias is bounded, not measured exactly (30 fps); the
delay also compensates this PC's own output timing; long-run drift is not
covered. Six pairs after the seam are too few to say how the host's loop
behaves over many loops. A longer seamless clip, or a light sensor and the
Scarlett mic on one clock, would remove both limits.

## Change

None. The V2 rootfs keeps `H713_HDMI_AUDIO_DELAY_SEC=0.115`;
`tools/hdmi/build-v2-overlay.py` now cites this record.
