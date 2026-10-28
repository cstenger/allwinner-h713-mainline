# Camera recording analysis

Inputs supplied by operator: `local/lcd-photos/test_111/baseline.mov` and `test.mov`. Original files stay outside Git; hashes and metadata identify them. Operator estimates phone about one foot from the speaker: about 0.9 ms sound flight time, too small to explain the measured discrepancy.

These are baked slow-motion MOV exports, 30 fps on the export timeline with normal-speed/ramp ends. Inner source cadence fits an 8.00× slow factor and the 1 kHz test tone is about 125 Hz. Therefore the retained sections have approximately 4.17 ms real-time frame spacing. We exclude baseline export time before 4 s and after 46 s, and test before 8 s and after 111 s. They cover only about 4.2 and 11.4 real seconds between paired events, respectively; they cannot qualify long-run drift.

`analyze-recordings.py` decodes video presentation timestamps and the default AAC track, samples a 200×200 centre patch inside the projection, checks irregular source cadence, and uses a centred 40 ms export-time 125 Hz lock-in envelope. AAC edit/skip metadata are honoured by ffmpeg; no manual priming subtraction is applied. The midpoint between the last below-threshold and first above-threshold frame brackets flash onset. Tone onset uses interpolation through a local amplitude threshold. Trailing recrossings within the same reverberant beep are allowed.

Baseline: five paired flashes/beeps, default median −23.74 ms, p05/p95 −27.33/−19.88 ms. 70 ms target: twelve pairs, default median +43.37 ms, p05/p95 +32.82/+50.48 ms. Positive is audio late. These are camera-recorded estimates including propagation and uncalibrated camera/export bias, not certified hardware offsets.

A nine-way threshold sweep (25/50/75% video and tone amplitude) gives baseline median range approximately −29.38 to −22.31 ms, and 70 ms median range +28.78 to +61.93 ms. The slow-motion audio onset is substantially smeared, making a precise final calibration from these files alone unreliable. Direction and overcorrection are consistent across thresholds. The absence of a visible physical/acoustic reference leaves camera bias unmeasured.

Three independent synthetic checks validate sign, eightfold time-scale conversion and known delay response/cadence rejection. Three mutations (wrong sign, missing time-scale division, disabled cadence guard) are caught; see `analysis-validation.txt`. Full pairs, threshold sweeps, hashes, cadence fits and selected ranges are in `*-slow-analysis.json`; decoded signals are retained in NPZ files. Reproduce from repository root with `python3 docs/hdmi-evidence/2026-10-27-avsync-calibration/camera/analyze-recordings.py`.

Initial exploratory output that treated the export timeline as ordinary video was superseded and moved to ignored build scratch. Only the retiming-aware results here are used for calibration. The later test2 recording and selected setting are documented below; the absent visible reference remains a qualification.

## 40 ms verification: test2.mov

The third recording was taken at the temporary 40 ms target. Its retained export interval is 8..134 seconds. Fifteen pairs span 14.50 real seconds; irregular source cadence fits 8.002× retiming. Recorded median is **−2.44 ms**, p05/p95 **−15.07/+3.03 ms**, min/max −15.14/+5.06 ms. Nine-way onset-threshold sensitivity gives median range −9.13..−0.35 ms. About one foot of acoustic flight contributes +0.9 ms to the recorded offset; subtracting it would shift the default median to approximately −3.3 ms, before unknown camera/export bias.

The operator could not clap while holding the phone, so there is no independent physical/acoustic reference. The 40 ms target is selected as the practical **recording-matched calibration**, with the above limitation. Absolute optical/acoustic zero is not certified. A one-handed visible hard-surface tap can refine camera bias later without needing a clap.

The board now stores `H713_HDMI_AUDIO_DELAY_SEC=0.040` in `/etc/default/h713-hdmi-speaker`. The temporary `/run` override was removed. A speaker-only restart reads that saved value and passes stereo routing/ownership checks; video stayed active. Orderly warm-reboot persistence subsequently passed, including saved target, actual loopback command, live routing/flow and operator picture/beep confirmation; see the parent report. There is no absolute host-monitor-to-projection measurement in these recordings, and they do not establish long-run drift.
