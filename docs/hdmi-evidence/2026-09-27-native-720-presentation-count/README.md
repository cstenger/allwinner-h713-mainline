# Native 720p sink presentation accounting

This follow-up adds per-buffer accounting around the native 1280x720 NV16 to
NV12 panel route and closes a source-mode validation hole found by optical
review. The corrected camera-gated run delivered 360 source buffers to the
KMS sink in 6.084748 seconds (59.16 fps). The sink reported 360 rendered and
zero dropped buffers, with no PTS mismatches or unmatched buffers.

## Optical failure caught before acceptance

The first counted run accidentally used the persistent 640x480 SCP probe after
the prior native probe disappeared from host `/tmp`. The host read EDID SHA256
`0812e13a13f9d6f84aca26f136c1a55f5bcb03fb8f24a93c107f3c5f96f89290`
and exposed only 640x480 modes, but the capture module and GStreamer caps still
interpreted the ring as 1280x720. All 360 buffers therefore reached the sink
and its counters passed even though the raster was wrong.

The optical result explains the geometry exactly. A 640x480 luma plane is
307,200 bytes, which becomes 240 rows when consumed at a 1,280-byte stride.
The visible top third consequently joined pairs of 640-pixel rows horizontally,
while the remaining two thirds consumed non-luma data and appeared green.
[`test-91-wrong-edid.jpg`](test-91-wrong-edid.jpg) retains a contact sheet from
the owner's `test_91/IMG_0912.mov`, whose SHA256 is
`51aa4ce4cbbfc527b1c99b88446b8804db1eb0ae298224287c0cb21eb2615f21`.
The otherwise-passing counters and the 640p source trace are retained as
[`failed-summary.json`](failed-summary.json),
[`failed-pipeline-summary.json`](failed-pipeline-summary.json), and
[`failed-trial.log`](failed-trial.log). This run is a failure, not evidence of
correct presentation.

## Source-mode guardrail

`tools/hdmi/build-scp-probe.py --mode 1280x720` now generates and builds the
mode-specific probe from tracked sources against the same kernel build used by
the capture module. The corrected probe SHA256 is
`da78b61bf86c3f434e433ff5a7ffe9dd752198e6253b04d5b4080e659701975d`.

Before opening the capture overlay, `run-native-720-panel.py` now requires all
of the following:

- exact EDID SHA256
  `1bf44b2172fb4e512d8a575c58f2abbcfd96d2f2902bea5b8a7a323248fb9013`;
- `1280x720` in the source connector's advertised modes;
- live MIPS port 1 in state 5 at 1280x720; and
- zero pixel repeat.

The test cannot reach the misleading 1280x720 userspace caps or KMS plane when
the receiver is actually producing 640x480. A non-visible preflight then read
one complete marker frame: all 720 rows, both horizontal edges, one patterned
frame, zero band mismatches, and zero stripe mismatches. See
[`full-raster-analysis.json`](full-raster-analysis.json) and
[`full-raster-frame.png`](full-raster-frame.png).

## Corrected counted run

The camera-gated run at `20260927T220318Z` recorded:

- pinned 1280x720 EDID and live receiver lock at 1280x720;
- 360 source buffers, 360 sink buffers, and 360 rendered buffers;
- zero sink drops, PTS mismatches, and unmatched buffers;
- mean/max source-to-sink-pad conversion time of 3,890.82/9,214 us;
- 365 driver completion events, 362 deliveries, three no-buffer overwrites,
  zero rejected frames, and zero unstable frames;
- exact driver accounting (`365 = 362 + 3 + 0`) and five bounded shutdown-tail
  events beyond the 360-buffer pipeline;
- fbcon framebuffer 40 preserved before, during, and after playback, with NV12
  framebuffer 42 active only on `video-0` during playback; and
- zero new IOMMU, atomic-commit, vblank-quiesce, or retire-drain errors.

The owner reported the corrected test looked much better. Review of
`test_92/IMG_0913.mov` confirms a full-frame motion pattern, one correctly
laid-out Leota image, no green lower field or horizontally repeated raster,
and final console return. The video SHA256 is
`dcc5870e64f430e8bdbc3af0ba3d9ed4079c50fd0dd51b5f8717b86be5504670`;
[`test-92-corrected.jpg`](test-92-corrected.jpg) is the retained contact sheet.

After EOS, the overlay retired, the source connector returned to
disconnected/disabled, fbcon was unblanked, the 640x480 full-verification
capture configuration was restored, MIPS remained live at guarded source 3,
and the display error count remained zero.

This establishes complete userspace source/sink accounting plus correct
full-frame optical geometry for the bounded run. The sink's `rendered` counter
does not prove that every buffer caused a distinct physical page flip, and the
run does not measure source-to-photon latency; those remain separate gates.
