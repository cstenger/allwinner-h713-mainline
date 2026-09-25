# Live HDMI capture on the projector panel

**Passed on board B, 2026-09-25.** The operator saw the moving white-square
HDMI test pattern on the projector panel. The bounded userspace preview read
`/dev/video1` as 640×480 NV16, converted it to a 960×720 image centered in a
1280×720 BGR0 canvas, and presented it on the existing DRM primary plane.
The black side bars preserve the 4:3 input aspect ratio on the 16:9 panel.
The source GPU read the expected 128-byte EDID and enabled 640×480 output.
No display driver, capture driver, boot image, or firmware changed.

The [summary](summary.json) records primary framebuffer 40 → 45 → 40 and AFBD
scanout `0xffc00000` → `0xff400000` → `0xffc00000`. The [DRM state](kms-during.log)
shows an active 1280×720 XR24 framebuffer held by mpv. [FFmpeg](target-ffmpeg.log)
delivered 120 frames at about 10–11 frames/s with full V4L2 frame verification;
[mpv](target-mpv.log) reported `VO: [drm] 1280x720 bgr0` and the first video
frame shown. The [source trial](trial.log) finished with
`peripheral_restored=1 mismatch=0`; the host GPU returned to
disconnected/disabled, the V4L2 module remained in full-verification mode,
and the SCP probe was absent afterward. A [second bounded run](repeat-summary.json)
for an operator recording also exited successfully and restored the console
framebuffer and AFBD scanout; its [source trial](repeat-trial.log) and
[capture log](repeat-target-ffmpeg.log) are preserved. The repeatable entry point is
[`run-panel-preview.py`](../../../tools/hdmi/run-panel-preview.py).

Earlier controls narrowed the initial blank-panel result. The first live
preview submitted 120 frames and switched the KMS framebuffer, but the
operator saw a blank panel. Synthetic BGR0 and NV16-to-BGR0 color bars did
appear. The operator also saw a [saved HDMI test frame](../2026-09-25-motion-irq/h713-motion-captured-first.png)
on the panel: its COSMIC menu and white squares came from the test source.
The initial live runner used mpv `--untimed`; the successful runner uses
paced playback. The board was cold-booted and the HDMI cable reseated between
tests, so the exact cause of the initial blank result is not isolated. After
that cold boot, the first HPD window had no GPU connection despite a clean
SCP trial. Reseating both cable ends restored GPU detection in a separate
12-second trial.

This is the first functional live preview, not the finished capture path.
Software conversion and full verification yielded about 10–11 frames/s;
firmware ring ownership is still inferred. FFmpeg logged a `VIDIOC_QBUF`
warning on close and mpv logged an atomic-commit error on teardown, despite
exit status zero and restored console scanout. Motion quality, latency, audio,
mode changes, and longer runs remain to be evaluated.
