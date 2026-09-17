# Handoff — scaled decode reaches the display path, 2026-09-17

Continues [the shared-scaler handoff](handoff-2026-09-17-shared-scaler.md), whose
"Next work" items 1 and 2 this covers. The kernel series is unchanged: same
module MD5 `772c6a46b668baafb98dcf00ddb15429`.

**State:** the VA driver and mpv negotiate, carry and display a hardware-scaled
picture. Confirmed on the projector by the operator — correct picture, audio in
sync, zero failed atomic commits, no LD_PRELOAD probe in the path.

**And item 2 is answered:** the VE scaler *does* honour an input crop. See
[the input-crop result](reference/ve-input-crop-2026-09-17.md). That removes the
one quality compromise in what shipped here, and what remains for it is an
interface question rather than a hardware one.

**Seeks work now too.** Looping the card on the projector exposed a
pre-existing bug that dropped hardware decoding permanently on the first seek;
`patches/libva-v4l2-request/0009` fixes it. It is unrelated to scaling — a 720p
file, which requests none, failed identically.

## What was added

Three patches.

`patches/libva-v4l2-request/0009` keeps the V4L2 queues alive while surfaces
still refer to them. `RequestDestroyContext` released both queues and cleared
`video_format` unconditionally, but a client may keep its surface pool across a
decoder re-initialisation and FFmpeg's does: mpv reuses the frame pool whenever
format and size are unchanged, which is exactly a loop or a seek, so the context
is destroyed and recreated while the surfaces live on. `RequestCreateContext`
then found `video_format` NULL and refused, surfacing as
`Failed to create decode context: 1 (operation failed)` and a permanent fall
back to software. `RequestDestroySurfaces` already had the right guard; this
path did not. After: seven loops of a scaled 1080p file, one decoder init
holding `vaapi[nv12]`, zero context failures, zero fallbacks, zero failed flips.

`patches/libva-v4l2-request/0008` teaches the VA driver to ask. It reads
`V4L2_REQUEST_SCALE` at every capture negotiation, S_FMTs the CAPTURE queue to
that size before any buffer exists, and reports the geometry the kernel actually
allocated through `vaExportSurfaceHandle`. `RequestCreateImage` refuses an image
larger than the buffer behind it.

`patches/mpv/0004` teaches mpv to use it. `vo_drm` publishes the mode it scans
out on the hwdec context; `vd_lavc` combines that with the stream's visible size
and sets the request before the frame pool is allocated; `vo_drm` reads the real
buffer geometry back out of `vaExportSurfaceHandle` and shows it on the video
plane.

## The three things that decided the design

**The request is a size, not a ratio.** A ratio is the more natural description
of what the hardware does, and it was the first design — scale by 3/2 to
1280x726 and crop the coded padding with the plane's SRC rectangle. The display
cannot express that: `h713_afbd_video_atomic_check` accepts one framebuffer
geometry and no other (1280x720, pitch 1280, `sun50i-h713-afbd.c`), so there is
no taller buffer to take a window out of. A ratio cannot reach 1280x720 either,
because the coded 1088 rows and the visible 1080 do not arrive at 720 by the
same factor. The hardware scales each axis independently, so an exact size is
expressible where a ratio is not.

**Neither mpv component can decide alone.** The VO knows the mode and not the
stream; the decoder knows the stream and not where its frames go. They meet only
in `init_generic_hwaccel()`, which is also the last moment before the surfaces
are allocated. Hence the new fields on `struct mp_hwdec_ctx` rather than a
computation in either place.

**FFmpeg drops the geometry, so mpv exports the surface itself.**
`av_hwframe_map()` copies the objects and layers out of the VA descriptor but
carries the AVFrame's own dimensions forward. A scaled surface therefore arrives
as 1280x720 of memory described as 1920x1080, and `drmModeAddFB2()` would be
told about storage that does not exist. `vaExportSurfaceHandle` reports the
truth, so `vo_drm` calls it directly, holds a reference to the surface rather
than to a mapping of it, and closes the exported fds once the GEM handles own
the storage. **This is why patch 0008's descriptor fields matter**: they are the
only channel through which a scaled picture's real size reaches anyone.

## Validation

Headless, on the board, against the installed stack.

| Check | Result |
| --- | --- |
| H.264 1080p, `V4L2_REQUEST_SCALE=1280x720` | coded 1920x1088, asked 1280x720, allocated 1280x720 |
| Same capture via the probe's `CEDRUS_CAPTURE_SIZE` vs via the VA driver | **byte-identical**, MD5 `f97c4409a6202f938169a54822c806f9` |
| `bogus` | ignored with a message, decode continues unscaled |
| Image download **with** scaling | fails cleanly at `vaCreateImage`, falls back; no overread |
| Image download **without** scaling | unchanged, MD5 `262698d49d712a49baf06da454b43697` |
| `hevc-decode-test.sh` / `va-decode-test.sh` / `hevc-10bit-test.sh` | 12 pass, 5 pass, PASS |
| 7 loops of a scaled 1080p file | one decoder init, `vaapi[nv12]` throughout, 0 fallbacks, 0 failed flips |
| 2 loops of a 720p file (no scale requested) | same, and the case that proved 0009 is not about scaling |

The byte-identical comparison is the load-bearing one. Geometry logs prove
negotiation, not pixels; asking for the same output size two different ways and
getting the same bytes proves the VA path reaches the same already-validated
kernel datapath. It is the check that would have failed had the new S_FMT
ordering disturbed anything — in particular the HEVC SPS bit-depth declaration,
which runs *after* the capture format is set and does not reset it.

## Validated on the display

`card0-LVDS-1` at 1280x720. 1080p H.264, `mpv --vo=drm --hwdec=vaapi`, no probe:
the driver logs `Coded 1920x1088, asked the driver for 1280x720, allocated
1280x720`, the video plane holds a crtc with changing framebuffer ids, there are
zero failed commits, and A-V stays at 0.000. The operator confirms the picture
and the sound.

**Still open:** whether the coded-padding band at the bottom is visible to the
eye. Both watched runs had forgiving bottom edges and the photograph that would
settle it was not taken. The headless measurement in
[the input-crop result](reference/ve-input-crop-2026-09-17.md) shows a test
card's bottom border coming out roughly twice as thick as it should, so the
expectation is that it IS visible on the right content.

## What it cost to find two bugs

Worth recording, because neither was visible to anything except a real run.

**The LD_PRELOAD probe hid a total failure.** Forcing the capture size at the
ioctl level made playback work while the VA driver was never consulted at all.
Removing the probe produced a black screen and the real bug: the driver parsed
its environment variable at `vaInitialize()`, which mpv calls while setting up
its video output — before it has opened the file, and long before `vd_lavc`
knows what to ask for. The request is now read at capture negotiation, which
also gives a resolution change a fresh answer.

**A "large enough" check cannot catch a buffer that is too big.** mpv tested
`fb_w < prime_src_w`, so an unscaled 1920x1088 buffer passed cleanly and then
died in the kernel as EINVAL on every flip, with nothing anywhere naming the
decoder. It now tests both directions when a scale was requested.

## Installed identities

```text
kernel_module_md5=772c6a46b668baafb98dcf00ddb15429
va_driver_patches=9
mpv_series=a451a720095a1595         mpv_patches=4
```

Read the live series ids out of `/etc/h713-video-stack`; they change per install.

Outgoing artefacts are kept beside each install, stamped with the time.

## Can stock mpv use this?

No, for three independent reasons, only one of which is about the scaler.

1. **There is no no-GPU direct scanout path upstream.** Upstream `vo_drm.c` has
   no PRIME support at all; it is a software-scaling VO. The only upstream
   direct-plane path is `hwdec_drmprime_overlay.c`, a `ra_hwdec_driver` needing
   a render context — `--vo=gpu` with GL or Vulkan, the Panfrost path this
   project avoids. Patch 0001 exists because "scan out on a plane" and "do not
   start a GPU" are not an upstream combination.
2. **Nothing in mpv or FFmpeg can ask a decoder for a specific output size.**
   VA-API has no entry point for decode-time scaling; it assumes a VPP pass.
   Hence the environment variable, which is an expedient and not an interface.
3. **FFmpeg discards the geometry**, as above.

Reason 1 is genuinely upstreamable. Reasons 2 and 3 are not, as things stand.
The lever that would most shrink the patch surface is moving the negotiation
into the VA driver — having it read the connected connector's mode itself —
which deletes the `vd_lavc` and `hwdec.h` changes and benefits any VA-API client
that scans out through the descriptor.

## Traps for the next session

- `local/upstream/va-driver-src` and `local/upstream/mpv-src` are **rebuilt from
  the series** by the build scripts (`git reset --hard` to the pinned base, then
  re-apply). Edits there are temporary; the patch file is the deliverable. The
  mpv tree was found carrying only part of patch 0003 — a stale leftover that
  would have produced a patch against the wrong base. `git commit --amend` after
  a build also amends the build script's commit, whose message is the patch
  filename.
- `build/linux-6.18.38-<hash>` is named by a hash of the **series**, so an edit
  left in that tree is silently reused by the next build. After the input-crop
  experiment the tree was restored and checked by artifact identity — rebuilt
  module md5 equal to the installed one — not by re-reading the source.
- Scaling is opt-in because it is only usable by a consumer that reads the
  geometry back out of the export descriptor. `hwdec=vaapi-copy` and
  `hwdownload` cannot, and now fail rather than read past the buffer.
- Display-side scaling patches 0098/0103/0106/0108/0111 are still in the kernel
  series and were not touched.

## Next work

1. **Land the input crop.** The hardware half is proven; the open question is
   how userspace declares the visible rectangle, and it collides with this
   driver's existing use of `S_SELECTION(CAPTURE, COMPOSE)`. Read
   [the result](reference/ve-input-crop-2026-09-17.md) before designing it.
2. **Photograph the bottom edge** on content with a bright bottom, to record
   what the compromise actually looks like before it is removed. The two photos
   taken on 2026-09-17 do not serve: the second one is a SOFTWARE-decoded frame,
   from after the seek bug dropped hardware decoding, so it says nothing about
   the VE scaler. Re-shoot now that 0009 is in.
3. **HEVC and Main10 to the panel.** They share the datapath but have not been
   through the display half.
4. **Then** reconsider the display-side scaling patches, per the previous
   handoff's item 3. Not before.
5. **Prepare upstreamable changes separately**: the generic SPS/TRY fix, the
   H713 scaler routing, the vo_drm PRIME scanout feature, and the downstream
   negotiation policy are four different submissions.
