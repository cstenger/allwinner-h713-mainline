# libva-v4l2-request patches

The VA-API driver that lets **stock** mpv and ffmpeg decode on the H713's VE.
It is a translator, not a decoder: ffmpeg parses the bitstream and hands over
picture and slice parameters, and this shim converts them into V4L2 Request API
controls for cedrus. Nothing upstream of it is patched — that is the whole
point of choosing this route (see [../../docs/vaapi-scope.md](../../docs/vaapi-scope.md)).

## Base

| | |
|---|---|
| upstream | <https://github.com/bootlin/libva-v4l2-request> |
| branch | **PR #38**, `refs/pull/38/head` — *not* `master` |
| pinned base | `1c5f2cad21dff3b56d35355082867c24e4f191c6` ("Don't advertise broken profiles") |
| license | MIT |

`master` is a red herring: its last commit is 2019-05-17 and it uses the
pre-stabilization `V4L2_CID_MPEG_VIDEO_H264_*` controls, whose structs no
longer match the 6.18 uAPI. **PR #38 already did that port** — it uses all
eight `V4L2_CID_STATELESS_H264_*` controls, precisely the set cedrus registers,
and assumes slice-based decode, which is the only mode cedrus offers.

Getting the tree:

```
git clone https://github.com/bootlin/libva-v4l2-request
git -C libva-v4l2-request fetch origin refs/pull/38/head:pr38
git -C libva-v4l2-request checkout pr38
git -C libva-v4l2-request am ../patches/libva-v4l2-request/*.patch
```

Build it **on the board**, not on the host. The driver's entry-point symbol is
`__vaDriverInit_<major>_<minor>` derived from the *libva pkg-config version* at
build time, so a host build against libva 1.24 produces a `.so` that the
board's libva 1.22 loader will not call.

## The patches

| # | What | Why |
|---|------|-----|
| 0001 | `#include "utils.h"` in `h264.c` | `request_log()` is called but never declared; implicit declarations have been an error since GCC 14 |
| 0002 | Build H.264 only; advertise only what `RequestCreateConfig` accepts | see below |
| 0003 | Create the bitstream buffer with the surface, not with the context | the one that actually blocked decoding — see below |
| 0004 | Port HEVC: PR #44's `h265.c` on this base, plus the four sites it needs | HEVC on the stabilized uAPI. Neither upstream PR decodes here alone: #38 has the format ordering cedrus requires, #44 has the modern port |
| 0005 | `h265`: pass the scaling matrix | `V4L2_CID_STATELESS_HEVC_SCALING_MATRIX` was never set by *either* upstream tree, so any stream with `scaling_list_enabled_flag = 1` decoded against flat matrices — see below |

Patch 0002 does two things that look separate and are not:

- **The bundled `include/hevc-ctrls.h` is deleted.** It is a 2019 snapshot of
  HEVC controls that have since been stabilized into `linux/v4l2-controls.h`,
  so every file including it redefines five structs the kernel headers already
  define — 5 errors across three files. `h265.c` cannot simply use the new
  definitions either: PR #38 ported H.264 and left HEVC on the old uAPI, using
  3 of the 8 controls cedrus registers. So `h265.c` drops out of the build and
  stays in the tree as the starting point for that port, which
  `docs/vaapi-scope.md` costs at ~400 lines with a reference-picture-set
  restructure.
- **`RequestQueryConfigProfiles` no longer advertises MPEG-2 or HEVC.**
  `RequestCreateConfig` already refuses both, so advertising them made `vainfo`
  report profiles that fail at `vaCreateConfig` — and `vainfo` is exactly the
  tool used to decide whether this driver works at all.

Patch 0003 is the one that mattered, and it is a good example of a failure that
points at the wrong half of the system. The symptom was

```
v4l2-request: Unable to enable stream: Invalid argument
[h264] Failed to create decode context: 1 (operation failed).
```

which reads as a codec problem. `strace` says otherwise:

```
VIDIOC_CREATE_BUFS {count=0, type=VIDEO_OUTPUT} = 0 ({count=0})
VIDIOC_STREAMON [V4L2_BUF_TYPE_VIDEO_OUTPUT] = -1 EINVAL
```

The shim sized the bitstream queue from the render targets handed to
`vaCreateContext`. ffmpeg allocates VA surfaces on demand and hands over none,
so the queue was created empty and `STREAMON` was correctly refused. The buffer
now belongs to the surface, which is where the OUTPUT format was already being
set for the same underlying reason.

Patch 0005 is worth reading for how it was found rather than for its size. The
control was simply never set — by either upstream tree, which corrects patch
0004's "#44 dropped the iqmatrix handling": PR #38's own pre-#44 `h265.c`
mentions `iqmatrix` three times, all in the declaration block of
`h265_set_controls()`, and then sets three controls that do not include a
scaling matrix. #44 merely removed the unused declarations. And **the gate
could not see that**: h01, h02 and
h03 all have `scaling_list_enabled_flag = 0`, and cedrus writes its scaling-list
SRAM only when that SPS flag is set, so a driver that fills nothing at all
scores bit-exact on all three. Two vectors were added to close the blind spot
(`h04`, implicit HEVC default lists; `h05`, explicit custom lists that are
non-flat at 4x4 and whose DC coefficients differ from their own matrix), and
they showed `MISMATCH (va) ve+25` — the engine decoding all 25 frames, to the
wrong answer — before the fix and bit-exact after it.

No scan conversion is needed, which is the opposite of what the bitstream syntax
suggests. HEVC codes scaling lists in up-right diagonal order, but **both APIs
specify raster**: `va_dec_hevc.h` says "Matrix entries are in raster scan order
which follows HEVC spec" and the V4L2 control's kernel doc says "expected in
raster scan order". ffmpeg's parser already undoes the scan
(`scaling_list_data()` in `libavcodec/hevc/ps.c` stores at the raster position;
`vaapi_hevc.c` copies across unchanged), so the shim's job is a straight copy.
`h05` is the evidence — its lists are non-flat at every size, so a wrong
permutation could not have come out bit-exact.

## Status — validated on hardware 2026-08-16

`vainfo` loads the driver (`__vaDriverInit_1_22`) and advertises the five H.264
profiles with `VAEntrypointVLD`. All five vectors of the M1 ladder decode
**bit-exact** against the host-generated references, through stock ffmpeg with
no patches to it:

| vector | result |
|---|---|
| `v01-320x240-baseline` (8 frames) | bit-exact |
| `v02-1280x720-baseline` (60) | bit-exact |
| `v03-1280x720-main` (60) | bit-exact |
| `v04-1280x720-high` (60) | bit-exact |
| `v05-1920x1080-high` (60) | bit-exact |

The VE's interrupt count rose by exactly 60 across a 60-frame decode, so the
hardware did the work — decode-only cost **1.233 s wall / 0.637 s CPU** for
60 frames of 1080p, against 2.72 s of CPU for the software decoder.

One measurement worth carrying forward: adding `hwdownload` to copy those
frames back to system memory costs *more* than the decode does (1.8 s extra for
186 MB), because V4L2 MMAP buffers are uncached. That is a cost of
decode-to-file validation, not of playback — a display path that maps the
surface as a dma-buf never pays it.

Reproduce with [`tools/video/va-decode-test.sh`](../../tools/video/va-decode-test.sh),
which scores a software control first so a hardware mismatch cannot be confused
with a broken yardstick.

## HEVC — validated on hardware 2026-08-22

`vainfo` additionally advertises `VAProfileHEVCMain` with `VAEntrypointVLD`, and
every HEVC vector decodes **bit-exact** through stock ffmpeg, with the GStreamer
oracle scoring the same 5/5 on the same run:

| vector | what it adds | result |
|---|---|---|
| `h01-640x480-main` (25 frames) | HEVC Main, WPP on | bit-exact |
| `h02-1280x720-main` (25) | panel-native size | bit-exact |
| `h03-640x480-nowpp` (25) | WPP off | bit-exact |
| `h04-640x480-scaling` (25) | scaling lists, implicit defaults | bit-exact |
| `h05-640x480-scaling-custom` (25) | explicit custom lists + DC coefficients | bit-exact |

Reproduce with [`tools/video/hevc-decode-test.sh`](../../tools/video/hevc-decode-test.sh).
The H.264 ladder is unregressed at 5/5 in the same session.

**Still not covered:** 10-bit (Main10) is blocked in the kernel — mainline
cedrus exposes no 10-bit capture format — and the two inert PPS flag bits noted
in patch 0004 are still wrong. Tiles, `transquant_bypass` and long-term
references have no vector yet.
