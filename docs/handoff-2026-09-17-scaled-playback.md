# Handoff — scaled decode reaches the display path, 2026-09-17

Continues [the shared-scaler handoff](handoff-2026-09-17-shared-scaler.md), whose
"Next work" item 1 this is. The kernel side is unchanged: same series, same
module MD5 `772c6a46b668baafb98dcf00ddb15429`.

**State:** the VA driver and mpv now negotiate, carry and display a
hardware-scaled picture. Headless validation is complete and the pixels are
byte-identical to the already-validated kernel path. **The panel test has not
been run yet** — it needs an operator and a power cycle, and nothing below
should be read as evidence that a picture appeared on the panel.

## What was added

Two patches, one per component.

`patches/libva-v4l2-request/0008` teaches the VA driver to ask. It reads
`V4L2_REQUEST_SCALE`, S_FMTs the CAPTURE queue to the scaled size before any
buffer exists, and reports the geometry the kernel actually allocated through
`vaExportSurfaceHandle`. `RequestCreateImage` refuses an image larger than the
buffer behind it.

`patches/mpv/0004` teaches mpv to use it. `vo_drm` publishes the mode it scans
out on the hwdec context; `vd_lavc` turns that plus the stream's visible size
into the ratio and sets it before the frame pool is allocated; `vo_drm` reads
the real buffer geometry back out of `vaExportSurfaceHandle` and shows a
cropped rectangle of it on the video plane.

## The three things that decided the design

**The scale request is a ratio, not a target size.** VA surfaces are allocated
at the CODED size, so a 1080p H.264 stream is a 1920x1088 buffer. A "fit into
1280x720" rule spends eight rows of the height budget on coded padding and
letterboxes a picture that should fill the screen. Scaling by 3/2 puts the
visible 1080 rows onto exactly 720 and leaves the padding as spare rows past the
bottom of the panel, which the plane's SRC rectangle crops. This is the
coded-versus-visible trap from the previous handoff, answered without needing
the hardware to honour an input crop.

**Neither mpv component can compute the ratio alone.** The VO knows the mode and
not the stream; the decoder knows the stream and not the mode. They meet only in
`init_generic_hwaccel()`, which is also the last moment before the surfaces are
allocated. Hence the two new fields on `struct mp_hwdec_ctx` rather than a
computation in either place.

**FFmpeg drops the geometry, so mpv exports the surface itself.**
`av_hwframe_map()` copies the objects and layers out of the VA descriptor but
carries the AVFrame's own dimensions forward. A scaled surface therefore arrives
as 1280x726 of memory described as 1920x1080, and `drmModeAddFB2()` would be
told about storage that does not exist. `vaExportSurfaceHandle` reports the
truth, so `vo_drm` calls it directly, holds a reference to the surface rather
than to a mapping of it, and closes the exported fds once the GEM handles own
the storage. **This is why patch 0008's descriptor fields matter**: they are the
only channel through which a scaled picture's real size reaches anyone.

## Validation

Headless, on the board, against the installed stack.

| Check | Result |
| --- | --- |
| H.264 1080p, `V4L2_REQUEST_SCALE=3/2` | coded 1920x1088, asked 1280x726, allocated 1280x726 |
| Same capture via the probe's `CEDRUS_CAPTURE_SIZE=1280x726` vs via the VA driver | **byte-identical**, MD5 `b880bd5668a56abea1f8262d54bf8963` |
| `2/1`, `7/2` | 960x544, 550x312 |
| `5/1`, `bogus` | ignored with a message, decode continues unscaled |
| HEVC 720p `3/2`, Main10 640x480 `2/1` | 854x480, 320x240 |
| Image download **with** scaling | fails cleanly at `vaCreateImage`, falls back; no overread |
| Image download **without** scaling | unchanged, MD5 `262698d49d712a49baf06da454b43697` |
| `hevc-decode-test.sh` / `va-decode-test.sh` / `hevc-10bit-test.sh` | 12 pass, 5 pass, PASS |

The byte-identical comparison is the load-bearing one. Geometry logs prove
negotiation, not pixels; asking for the same output size two different ways and
getting the same bytes proves the VA path reaches the same already-validated
kernel datapath. It is the check that would have failed had the new S_FMT
ordering disturbed anything — in particular the HEVC SPS bit-depth declaration,
which runs *after* the capture format is set and does not reset it.

## Not yet validated

**Nothing has been put on the panel.** The whole mpv half — the export, the
framebuffer, the cropped SRC rectangle, the geometry check — has been compiled
and installed but never run against the display. Do not describe this work as
playback until that happens.

The panel is `card0-LVDS-1` at 1280x720, so the 1080p vector should negotiate
3/2, allocate 1280x726, and show its top-left 1280x720. The gate is the one from
the display memory: `/sys/kernel/debug/dri/*/state` must show the video plane
with a crtc, a non-zero fb, and an fb id that **changes** between reads. mpv
logging "Using direct DRM PRIME video-plane scanout" proves path selection only.

Power-cycle before the test; warm reboots kill this display. Confirm the boot
logo first — U-Boot prints "logo published" even on a black boot.

## Installed identities

```text
va_driver_series=4eb2d33db8ab898e   va_driver_patches=8
mpv_series=49448ad015be9bb8         mpv_patches=4
kernel_module_md5=772c6a46b668baafb98dcf00ddb15429
```

Outgoing artefacts were kept: `/usr/lib/aarch64-linux-gnu/dri/v4l2_request_drv_video.so.20260917-031348.bak`
and `/usr/local/bin/mpv.20260917-031610.bak`.

## Traps for the next session

- `local/upstream/va-driver-src` and `local/upstream/mpv-src` are **rebuilt from
  the series** by the build scripts (`git reset --hard` to the pinned base, then
  re-apply). Edits there are temporary; the patch file is the deliverable. The
  mpv tree was found carrying only part of patch 0003 — a stale leftover that
  would have produced a patch against the wrong base.
- Scaling is opt-in because it is only usable by a consumer that reads the
  geometry back out of the export descriptor. `hwdec=vaapi-copy` and
  `hwdownload` cannot, and now fail rather than read past the buffer.
- Display-side scaling patches 0098/0103/0106/0108/0111 are still in the kernel
  series and were not touched. Retiring them is item 3 of the previous handoff
  and stays blocked on panel validation.

## Next work

1. **Run the panel test** (above). Picture, aspect, bottom edge, A/V sync, long
   playback, seeks, a resolution change, and return to the console.
2. **Then** HEVC and Main10 to the panel, which share the datapath but have not
   been through the display half.
3. **Then** reconsider the display-side scaling patches, per the previous
   handoff's item 3. Not before.
4. Splitting for upstream is unchanged: the generic SPS/TRY fix, the H713 scaler
   routing, and the downstream playback policy are three different submissions.
   The mpv change would need `struct mp_hwdec_ctx` fields agreed upstream; the
   environment variable is a downstream expedient, not an interface.
