# HDMI speaker delay recalibration — November 18, 2026

**Result: the speaker delay is now 0.115 s (was 0.040 s).** At 0.040 s the
projector's speaker played about 70–80 ms before the picture. At 0.115 s the
measured offset, corrected for the phone's own A/V bias, is −5..+13 ms
(about +2 ms at the bias midpoint). Positive means audio late.

This supersedes the selection in
[the 2026-10-27 calibration](../2026-10-27-avsync-calibration/README.md),
whose 40 ms came from 8× slow-motion recordings with no physical reference.
That report already flagged the slow-motion audio onset as smeared and camera
bias as unmeasured; the tap reference below indicates it was large.

## Setup

Installed candidate on the DDR3 bench board (see
[the installation record](../../production-evidence/2026-11-17-candidate-installation/README.md)),
HDMI 720p60 from the same PC as 2026-10-27. The PC played the 2026-10-27 clip
(`build/hdmi-avsync-2026-10-27/source-v2/hdmi-avsync-720p60.mkv`, sha256
`fb40949d…`: irregular full-screen flashes with simultaneous 1 kHz beeps)
fullscreen on HDMI-A-1 with mpv, 0 dropped frames. The projector's PC audio
sink is the one whose ELD names `H713`; after a PC reboot that moved from ALSA
device 3 to device 8, which silently sent the beeps to another monitor until
caught. Recordings are phone videos in `local/lcd-photos/test_119/`
(hashes in [recordings.sha256](recordings.sha256)), not committed.

The analyzer is the 2026-10-27
[`camera/analyze-recordings.py`](../2026-10-27-avsync-calibration/camera/analyze-recordings.py),
generalised for new files: `--file/--start/--end/--name/--out`, `--slow` (1, 2,
4 or 8), a centred brightness patch, export-time limits scaled by the retime,
and a cadence residual floor of 1.5 video frames. Run on the three 2026-10-27
recordings it reproduces their pairs and threshold sweeps exactly.

## Measurements

| Recording | Mode | Delay | Pairs | Median (ms) | Notes |
| --- | --- | --- | ---: | ---: | --- |
| IMG_1114 | 4× slow motion (120 fps) | 0.040 | 19 | −35.1 | audio-threshold sweep −62..−6: slow-motion audio smears the onset; inconclusive |
| IMG_1115 | normal, 30 fps | 0.040 | 27 | **−63.8** | 26/27 within −67.6..−54.8; sweep −72..−54 |
| IMG_1116 | normal, ~24 fps | 0.040 | 9 | −52.0 | coarser, same direction |
| IMG_1121 | normal, 30 fps | **0.115** | 29 | **+18.9** | pooled over two halves around one mpv loop seam (+65 ms step, audio and video together); halves 11.2 / 20.0; two outliers (44, 83) |

**Phone bias (IMG_1118):** ten pen taps on the desk, contact in view, same
30 fps mode. Each click onset (60–130× noise) was paired with the frame where
the tracked pen tip first reaches the desk; contact lies between that frame
and the previous one. Nine taps bound the phone's audio as **6..24 ms late**
relative to its video (median midpoint +17 ms); one tap (40..73 ms, a press
or slide rather than a clean strike) was excluded. Per-tap bounds:
[tap-bias-IMG_1118.json](tap-bias-IMG_1118.json).

Corrected offsets: 0.040 s → −88..−70 ms; 0.115 s → **−5..+13 ms**. Raising
the delay by 75 ms moved the measured offset by 83 ms, consistent within
camera-frame quantisation.

## Installed change

`/etc/default/h713-hdmi-speaker` on the board: `H713_HDMI_AUDIO_DELAY_SEC`
0.040 → 0.115 (sha256 `38bfa7fb…` → `b737cb62…`), written atomically, original
kept at `/var/lib/h713-hdmi-startup/speaker-delay-2026-11-18/h713-hdmi-speaker.before`.
A speaker-only restart ran `pw-loopback --latency=20 --delay=0.115`; a later
power cycle came back with the same value. `config/hy200-ddr3-calibration.json`
now says `0.115` and points here; release tests read the expected value from
that file instead of a hard-coded 0.040.

## Limits

The delay compensates this PC's own output timing as well as the board's: a
different source may differ by a frame or two. Phone bias is bounded, not
measured precisely (30 fps). A photodiode and microphone on one audio
interface would give a sub-millisecond reference. Long-run drift is not
covered. The candidate release still ships 0.040 until rebuilt.

Analysis outputs: `avsync-*-slow-analysis.json`,
[pooled 0.115 s pairs](avsync-115ms-2026-11-18-pooled.json).
