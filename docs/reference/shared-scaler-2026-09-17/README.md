> **Historical 0120 measurements.** Final installed module and 49/49 compliance
> are in [the 0121 validation record](../cedrus-controls-2026-09-17/README.md).
> The final 53-capture matrix passes; all 51 common checks preserve active pixels.

# Shared scaler validation, 2026-09-17

Evidence for [patch 0120 and its handoff](../../handoff-2026-09-17-shared-scaler.md).
Board: root@192.168.4.1, H713 bench DDR3, running kernel 6.18.38.
All preserved captures used the clean-build module MD5
`b167f116f54201bf2069c2a96d122722`.

- `results.json` / `scaler-final-tests.log`: 51 passing pixel captures, with
  true unscaled controls, both sizing APIs, all five H.264/seven HEVC vectors,
  larger pitches, concurrent codecs, and a later H.264 P-frame.
- `results-main10.json` / `scaler-main10-final.log`: three passing Main10
  captures, including a later P-frame and S_FMT/COMPOSE active-byte equality.
  The encoder emitted nonfatal NUMA-affinity messages; encoding returned zero
  and the decoder, pixel, and DMA guard checks passed.
- `dmesg-new.txt`: empty, with no kernel messages during the 51-capture matrix.
- `final-compliance.txt`: 48/49, unchanged pre-existing TRY_EXT_CTRLS failure.

PSNR uses a raw NV12 bicubic software reference. `99` denotes zero error.
Scaled planes are extracted using actual pitch and canvas height. Main10
exports the upper 8-bit planes; software conversion can round/dither, so its
unscaled reference is not expected to be byte-identical.

Captures are preserved as lossless `.nv12.gz` files; per-decode stderr remains
uncompressed. Both remain on the board under
`/mnt/media-data/scaler-final-tests` and `/mnt/media-data/scaler-main10-final`.
The reusable `tools/video/cedrus-scaler-check.py` combines both check groups
into 53 captures, without repeating the Main10 format case.
