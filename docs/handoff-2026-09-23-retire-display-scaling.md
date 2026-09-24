# Handoff — retiring display-side scaling, 2026-09-23

Closes item 4 of [the scaled-playback handoff](handoff-2026-09-17-scaled-playback.md)
("**Then** reconsider the display-side scaling patches ... Not before"), which
was gated on HEVC and Main10 reaching the panel. They did, on 2026-09-17.

**What changed:** six kernel patches left `patches/kernel/series` —
0098, 0103, 0105, 0106, 0108 and 0111. The series is 85 entries, down from 91.
The video plane no longer drives the proc upscaler at `0x05180000`, the afbd DT
node no longer maps it, and `h713_afbd_video_atomic_check()` accepts one source
rectangle again: the full 1280x720 panel.

**Nothing else moved.** Cedrus, the VA driver and mpv are untouched. The VE
polyphase scaler (0120) is what makes this possible and it is unchanged.

## Why these six, when the handoff named five

The handoff listed 0098/0103/0106/0108/0111. **0105 has to go with them**, for
two reasons. Its context depends on 0098 — it rewrites the
`h713_afbd_init_video_info()` signature that 0098 introduced, so the series
does not apply without it. And its subject only exists in the retired regime:
it puts the framebuffer *pitch* rather than the visible width in the VideoInfo
descriptor, and pitch and visible width can differ only when the picture is
smaller than the panel it is padded into. With one framebuffer geometry, pitch
== width == 1280 and the patch is a no-op.

No other patch in the series touches `sun50i-h713-afbd.c` after 0080, so the
six are a leaf. They are a **chain**, not independent: restore all six or none.

## Why nothing could still reach the path

The evidence is in userspace, not in the kernel, and it is what makes this a
retirement rather than a regression.

- **mpv's `vo_drm` refuses any configuration whose displayed source size
  differs from the mode** (`patches/mpv/0003`, kept by `0004`). Fullscreen and
  uncropped are already required, so the destination is always the panel, and
  therefore the source it asks the plane for is always 1280x720.
- **`vd_lavc` only ever asks the decoder to shrink** (`patches/mpv/0004`:
  "Only shrink. Asking for a larger picture than the stream has is not this
  hardware's job"). A sub-panel stream produces no scale request, so its
  surfaces stay at the stream's own size.
- **A sub-panel surface could not reach the plane even so.** 0106 required the
  framebuffer itself to be exactly 1280x720; a 640x480 decode yields a 640x480
  framebuffer, which `atomic_check` rejected before any of the proc code ran.

So the magnify route had no producer once the VE could land on the panel size
exactly. It was reachable only from `tools/display/kms-nv12-plane-test.c SRC=`,
a diagnostic, which now refuses with an explanation instead of failing at the
commit with a bare `EINVAL`.

## What is genuinely given up

**Upscaling with no GPU.** The VE scales 1x-4x *down* only, and the proc block
was the only thing on the board that could magnify. 480p content on this 720p
panel therefore has no hardware path today — mpv already refuses it and directs
the user to `--hwdec=vaapi-copy`, which is the state before this change as well
as after it, but the *latent* capability is what the six patches held.

That is the reopen condition, and the kernel half of it already exists: cedrus
patch 0107 separates COMPOSE from the capture canvas, so a small picture can be
decoded into a panel-sized buffer. What is missing is a producer that asks for
that, and the six patches to put back. Each of the six carries a header saying
so.

## Verification, before hardware

**The series still applies and the result is exactly the pre-0098 driver.**
Reconstructed the file two ways — every in-series patch that touches it
(0037, 0063, 0078, 0079, 0080, plus the six) reproduces the currently installed
tree byte for byte, which validates the method; the same run without the six
reproduces the new build tree byte for byte. The removal leaves no residue:
`proc`, `PROC_*` and `0x05180000` no longer appear in the driver, and the DT
node is back to three `reg` ranges (`afbd`, `route`, `lvds`).

**Full build:** `JOBS=12 tools/build/build.sh kernel`, 85 patches, Image + both
DTBs + modules + bench FIT.

Build tree: `build/linux-6.18.38-cc7f8012dc29ab6ade523fcce35dd06ec8aa88bea2353e596344eca4b8d441df`

## Deploying it needs a flash, not a module swap

`CONFIG_DRM_SUN50I_H713_AFBD=y` — the driver is **built in**, and the DT changed
as well. This cannot be tested by copying a `.ko`: it needs the new FIT and a
**power cycle**, not a warm reboot (warm reboots kill this display). Confirm the
U-Boot logo is actually visible before believing any display result, and expect
`p23` not to be mounted after a cold boot.

## Validation on hardware — PASSED 2026-09-23

Cold-booted on the new FIT (kernel built Sep 23 19:33, 86-patch series — the
series grew from 85 to 86 after this file was first written, when patch 0125
landed at 14:55). Operator watched the panel for every visual step.

1. **Console and afbd clean.** Three reg ranges in `/proc/iomem`
   (`route`, `lvds`, `afbd`); `0x05180000` absent, as is any `proc` reference.
   The DT node carries three `reg` pairs. Panel lit, Linux prompt visible.
2. **1080p H.264 — pass.** `mpv --vo=drm --hwdec=vaapi` on `leota-1080p.mp4`:
   `Using hardware decoding (vaapi)`, `Using direct DRM PRIME video-plane
   scanout`, `A-V: 0.000`, no dropped frames, exit 0. The `video-0` plane held
   **crtc-0 with a changing framebuffer id** (49 → 47 → 41), NV12,
   **1280x720** — the VE landing on the panel size exactly, which is the whole
   premise of the retirement. Zero failed atomic commits. Operator: correct
   picture, no visible flaws.
3. **HEVC and Main10 — pass.** Both scanned out NV12 1280x720 on `video-0`
   with changing fb ids. Main10's buffer is larger (1728512 vs 1384448 bytes),
   consistent with the 8+2 layout it still carries. Operator-confirmed.
4. **720p, no scaling — pass.** `VO: [drm] 1280x720 vaapi[nv12]`, same plane
   behaviour. Operator-confirmed.
5. **Headless control gates — pass, and unaffected as predicted.**
   `va-decode-test.sh` 5/5 bit-exact, `hevc-decode-test.sh` 14/14 (including
   `h10-656x480-unaligned` bit-exact on all three arms), `mpeg2-decode-test.sh`
   6/6. No kernel messages during any gate.

Zero IOMMU faults and zero failed commits across the whole session. The only
`dmesg` warnings are WiFi/BT/pinctrl from boot, unrelated to display.

> **Trap worth recording.** The first 1080p attempt appeared to fail: the
> `video-0` plane never took a crtc. The cause was the invocation, not the
> driver — the gates `export LIBVA_DRIVER_NAME=v4l2_request` and nothing sets
> it in root's shell, so libva could not resolve a driver
> (`vaGetDriverNames() failed`) and mpv fell back to **software** decode into
> the primary plane while still printing a cheerful `VO: [drm]` line. Set that
> variable before any manual mpv run, and gate on the plane state rather than
> on mpv's own output.

## Re-validated on the 88-patch build — 2026-09-23, later the same night

The validation above ran on the **86-patch** build. Patches 0126 and 0127 then
changed the reserved regions of the IOMMU group that cedrus and the display
*share*, and the video path imports cedrus dma-bufs into the display through
exactly that IOMMU. The 2-hour soak could not cover it — it runs no display, by
design — so the panel was re-tested on the build we actually intend to ship.

All four cases operator-confirmed again, with the plane holding crtc-0 and a
changing NV12 1280x720 framebuffer each time:

| case | mpv VO line | result |
| --- | --- | --- |
| 1080p H.264 | `1920x1080 vaapi[nv12]` | correct, `A-V: 0.000` |
| HEVC | `1920x1080 vaapi[nv12]` | correct |
| HEVC Main10 | `1920x1080 vaapi[nv12]` | correct |
| 720p, no scaling | `1280x720 vaapi[nv12]` | correct |

**Zero IOVA collisions and zero failed atomic commits** across every run, which
is the specific thing 0126 could have broken.

> **The first pass of this test could not have failed the way it was meant to.**
> HEVC and Main10 were run back to back, and both clips are the *same*
> resolution test card, 6 seconds each. On the glass they read as one
> continuous segment — so if Main10 had rendered nothing, the operator would
> still have seen an unbroken test card and called it fine. The operator caught
> this ("seems like I may have missed a test"), not the harness.
>
> Re-run as an explicit A/B: HEVC looped for 10 s, a black clip for 3 s, then
> Main10 for 10 s. Both legs separately confirmed, each with its own hardware
> decode and its own cycling framebuffers.
>
> The general rule: **when an operator is the instrument, consecutive cases must
> be visually distinguishable.** Two tests that look identical are one test.
