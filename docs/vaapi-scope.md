# Hardware decode for stock players — VA-API scope

Written 2026-08-16. Answers one question with numbers rather than estimates:
**what would it take for `mpv` (and anything else using ffmpeg) to decode on the
VE instead of the CPU, without patching mpv, ffmpeg or GStreamer?**

The short version: the chain is real, the H.264 half is nearly free, the HEVC
half is a rewrite, and 10-bit is blocked in the kernel rather than in userspace.

---

# HANDOFF — start here, 2026-08-16

**The decision already made:** do not patch mpv, ffmpeg or GStreamer. Adapt our
own code to fit them. That is what makes libva-v4l2-request the route — it is a
VA-API *driver*, so stock players use it unmodified.

**The goal for the next session:** get `libva-v4l2-request` decoding H.264 on
the VE, validated to bit-exactness with **no display involved**. Display comes
after, because it is a separate and larger risk.

## Board state as of this handoff

| | |
| --- | --- |
| Kernel | `6.18.38`, built from the current series, **persisted** to the FAT (`fatwrite mmc 1:2 h713-kernel.fit`) and booting from it via `bootcmd` |
| Rootfs | flashed 2026-08-16 with `--profile dev`; `/` grew to 4.5 G |
| KMS | `sun50i-h713-afbd` **autoloads at boot** (it is in `/lib/modules` with an OF alias); panel shows a Linux console |
| `/root` | `drm-flip{,.c}`, `sun50i-h713-afbd.ko`, `v04-1280x720-high.h264`, `h01-640x480-main.h265`, `h02-1280x720-main.h265`, `h03-1280x720-main10.h265` |
| Missing for this work | **nothing on the board** — `libva-dev`, `meson`, `ninja-build` and `ffmpeg` were added to `--profile dev` *after* that flash, so the rootfs must be rebuilt and reflashed first |

**The panel needs `h713_disp auto 0x34 logo` at the U-Boot prompt before `boot`,
every single time.** Without it the KMS driver correctly refuses to probe. For
decode-only work you can skip it — nothing about VA-API needs the display.

## Operational gotchas this session cost time on

- **Serial writes must be paced.** Long command lines sent in one burst come
  back with doubled characters (`ddrivers`, `afbbd`) and the *shell runs the
  corrupted line*. `tools/serial/console.py` writes one character at a time and
  is the tool to use. This looks like a display artifact and is not.
- **`modprobe` is a silent no-op if a stale build is already loaded.** udev
  autoloads the module at boot, so after copying a new `.ko` you must `rmmod
  sun50i_h713_afbd` first or you will test the old one and misread the result.
- **Fastboot needs a cold power cycle.** Linux leaves musb in a state U-Boot's
  warm-reset path does not reinitialise, so `reboot bootloader` lands at a
  prompt with `No USB controllers found`. Flashing the rootfs therefore needs a
  human to pull power and press a key during the boot delay.
- **A FIT transfer over serial is ~12 minutes** at 10.8 KB/s. Budget for it.
- **mpv needs `--drm-device=/dev/dri/card1`** — panfrost holds minor 0 as a
  render-only node.

## The plan, in order

1. **Rebuild and reflash the rootfs** to get the build dependencies:
   `tools/rootfs/build.sh --ssh-key KEY --profile dev`, then fastboot it (needs
   the cold power cycle above). ~10 min build, ~5 min flash.
2. **Clone and fix the driver.** `git clone
   https://github.com/bootlin/libva-v4l2-request`, then `git fetch origin
   refs/pull/38/head:pr38 && git checkout pr38` — master is the 2019
   pre-stabilization code and is *not* the starting point. Two fixes, both
   measured here by actually building it:
   - drop `h265.c` and `include/hevc-ctrls.h` from the build (they collide with
     the now-upstream HEVC controls — 5 redefinition errors across 3 files);
   - add the missing `#include` for `request_log` in `h264.c` (1 error).
3. **Build on the board** (`meson setup build && ninja -C build`) and install as
   `/usr/lib/aarch64-linux-gnu/dri/v4l2_request_drv_video.so`.
4. **`LIBVA_DRIVER_NAME=v4l2_request vainfo`** — does it initialise and
   advertise H.264 profiles? First real go/no-go.
5. **Decode to a file and check it byte-for-byte.** This is the gate, and the
   references already exist: `local/video-test/v0*.nv12` from the M1 ladder, and
   `/root/v04-1280x720-high.h264` is already on the board. Force NV12, compare
   md5 — exactly as `m1-decode-test.sh` does. **Do not skip to mpv here.** A
   failure at this step is in the shim; a failure after mpv is added could be
   either half.
6. **Only then the display path**: `mpv --hwdec=vaapi --vo=gpu
   --gpu-context=drm --drm-device=/dev/dri/card1`. Expect this to be where the
   time goes.

## What to expect to go wrong

The compile is measured and safe; the *runtime* is not. PR #38 is unmerged
third-party work whose own commit message says "POC", developed against H3/A64
VEs rather than this one, and one of its commits is literally *"Don't advertise
broken profiles"*. Our cedrus is proven bit-exact through GStreamer, so the
kernel half is sound — what is unproven is whether this shim drives it
correctly. If step 5 produces frames that are *close but not identical*, suspect
the reference-list or DPB mapping before suspecting the hardware.

The display path in step 6 wants EGL-on-GBM against a KMS driver that only
scans out physically contiguous memory. GBM's split render/display arrangement
should handle it, but nobody has run it here.

**Fallback that needs none of this:** GStreamer already decodes H.264 *and*
HEVC on this hardware today. If the shim disappoints, a GStreamer sink wrapping
the proven `gles-play` path gets hardware-decoded video to the panel with no
third-party dependency at all.

---

## Why mpv cannot do it today

V4L2 has two decoder APIs and they are not interchangeable:

| | who parses the bitstream | who speaks it |
| --- | --- | --- |
| **Stateful M2M** | the kernel driver | ffmpeg's `h264_v4l2m2m`, i.e. mpv |
| **Stateless / Request API** | *userspace* | GStreamer's `v4l2codecs` |

cedrus is stateless, because the Allwinner VE has no bitstream-parsing firmware
and mainline will not put an H.264 parser in the kernel. Measured on the board:
`libavcodec.so.61` contains `v4l2m2m` symbols and **zero** `v4l2request`
symbols. So there is no configuration that connects mpv to this hardware — the
V4L2 Request hwaccels are an out-of-tree series that LibreELEC has shipped since
2018 and that is [still not merged upstream](https://ffmpeg.org/pipermail/ffmpeg-devel/2024-August/332034.html).

This is also why `gles-play` works: it drives GStreamer, which does implement the
stateless protocol.

## The chain that does work

```
cedrus → V4L2 stateless → libva-v4l2-request → libva → ffmpeg → mpv
```

Everything right of the shim is stock and unpatched. The shim is a *translator*,
not a decoder: by the time VA-API is called, ffmpeg has already parsed the
bitstream and hands over picture and slice parameters, which the shim converts
into Request-API controls. That is the whole job.

[bootlin/libva-v4l2-request](https://github.com/bootlin/libva-v4l2-request) is
that shim. mpv and ffmpeg on our image already have VA-API compiled in
(`mpv --hwdec=help` lists `vaapi (h264-vaapi)`), so only the driver `.so` is
missing.

---

## H.264: nearly free

Master is a red herring — last commit **2019-05-17**, using the pre-stabilization
`V4L2_CID_MPEG_VIDEO_H264_*` controls, and its structs differ from the 6.18 uAPI
exactly as you would expect from that break (12 fields moved out of
`slice_params`, `pred_weights` split into its own control, `v4l2_h264_reference`
introduced).

**But [PR #38](https://github.com/bootlin/libva-v4l2-request/pull/38) already did
that port.** It targets kernel 5.14, uses all eight
`V4L2_CID_STATELESS_H264_*` controls — precisely the set cedrus registers in
6.18 — and assumes slice-based decode, which is the only mode cedrus offers.

Built here against modern kernel headers to measure rather than guess:

| errors | cause | fix |
| --- | --- | --- |
| 5 × struct redefinition, 3 files | vestigial bundled `include/hevc-ctrls.h` colliding with now-upstream HEVC controls | don't compile `h265.c` |
| 1 × `implicit declaration of 'request_log'` | missing `#include` in `h264.c` | one line |

**Zero H.264 uAPI mismatches.** Two supporting checks also came back clean:
`vaExportSurfaceHandle` with `DRM_PRIME_2` is implemented, so decoded surfaces
export as dma-buf — the same path `gles-play` already proved on this hardware —
and the ARM detiling assembly is `#ifdef __arm__`-guarded at both definition and
call site, so aarch64 builds and negotiates linear NV12.

## HEVC: a rewrite, but the hardware earns it

PR #38 ported H.264 and left HEVC on the 2019 API. `h265.c` uses three old
controls; 6.18 and cedrus need **eight**.

| | H.264 (ported) | HEVC (not ported) |
| --- | --- | --- |
| controls | 8 of 8 present | **3 of 8** |
| `sps` | identical | 30 → 26 fields, 9 removed |
| `pps` | identical | 32 → 17, **20 removed** |
| `slice_params` | ported | 38 → 30, 16 removed; `data_bit_offset` → `data_byte_offset` |
| `decode_params` | ported | **entirely new**, 13 fields |
| `scaling_matrix` | identical | **entirely new** |
| `dpb_entry` | +2 fields | `rps`/`pic_order_cnt` → `flags`/`pic_order_cnt_val` |
| effort | one `#include` | ~400 lines of `h265.c` largely rewritten |

Two kinds of work hide in that table. Most is **mechanical**: every individual
boolean (`amp_enabled_flag`, `cabac_init_present_flag`, …) collapsed into a
single `flags` bitfield, so every assignment changes shape. The part needing
thought is the **reference picture set restructure** — per-slice `rps` became
per-frame `decode_params` carrying `poc_st_curr_before/after` and `poc_lt_curr`,
so the shim must map VA-API's `ReferenceFrames` plus
`RefPicSetStCurrBefore/After/LtCurr` into that shape. `entry_point_offsets`
(WPP/tiles) is a new control on top.

The saving grace: GStreamer's `v4l2slh265dec` is a working implementation of
those exact eight controls against this exact kernel. The semantics can be read
off rather than derived.

---

## HEVC decodes on this hardware — measured 2026-08-16

Worth establishing *before* costing a port, because if the VE could not decode
HEVC the whole question would be moot. It can, and with no driver changes:

| vector | result |
| --- | --- |
| `h01-640x480-main` (25 frames) | **bit-exact**, md5 `9ebd49ec…` = host software reference |
| `h02-1280x720-main` (25 frames) | **bit-exact**, md5 `c898a8f0…` = host software reference |
| throughput | **~550 fps** — 500 frames of 720p in 0.905 s including process startup |

Method is the M1 gate's: deterministic `testsrc2` source, Annex-B elementary
stream, decoded on the host to linear NV12 as ground truth, decoded on the
target through `filesrc ! h265parse ! v4l2slh265dec ! video/x-raw,format=NV12`,
md5 compared. Forcing NV12 is required for the same reason as H.264 — unforced
it negotiates the 32x32 tiled `ST12`, which is correct output that can never
match a linear reference. Vectors are generated by
`tools/video/make-test-streams.sh` (`h01`, `h02`).

`gst-inspect-1.0` registers `v4l2slh265dec`, and `/dev/video0` advertises `S265`
(HEVC Parsed Slice Data) alongside `S264`, `MG2S` and `VP8F`.

## 10-bit does not work, and the blocker is in the kernel

`Main10` prerolls, reaches EOS in 40 ms having produced **zero frames**, and
forcing `P010_10LE` fails with `not-negotiated`.

The cause is not the H713. Our VE binds as `allwinner,sun50i-h6-video-engine`,
whose variant declares `CEDRUS_CAPABILITY_H265_10_DEC`, and the hardware
registers are there — `cedrus_regs.h` defines `VE_DEC_H265_SECOND_OUT_FMT_P010`
and `10BIT_4x4_TILED`, and `cedrus_h265.c` writes `VE_DEC_H265_10BIT_CONFIGURE`.
The kernel's uAPI even defines `V4L2_PIX_FMT_P010` and `NV15`.

But **`cedrus_video.c` exposes no 10-bit capture format at all** — its complete
list is `NV12`, `NV12_32L32`, `NV21`, `YUV420`, `YVU420` — and contains no
`bit_depth` handling. The capability bit only relaxes SPS *validation* in
`cedrus.c`; nothing downstream can express a 10-bit buffer, so nothing can
negotiate one.

So 10-bit HEVC needs a **cedrus patch** (add a 10-bit capture format gated on
`ctx->bit_depth`, wire the second-output-format registers), which is kernel work
in a staging driver — plausibly upstreamable, and independent of anything in
this document. Note also that the panel is 8-bit RGB after GPU conversion, so
10-bit buys source compatibility rather than visible quality.

---

## Scope, then

| item | effort | risk |
| --- | --- | --- |
| Build the shim for arm64, H.264 only | ~1 hour | low — measured, it's one `#include` and dropping `h265.c` |
| First decode, validated against the M1 ladder's references | a few hours | moderate — compiling is not decoding; PR #38 is unmerged WIP ("POC" in its own commit) developed against H3/A64-era VEs |
| mpv display path (`--hwdec=vaapi --vo=gpu --gpu-context=drm`) | unknown | **highest** — EGL-on-GBM against our KMS driver, never tried here, and the driver only scans out physically contiguous memory |
| HEVC in the shim | days | moderate — mechanical bulk plus the RPS restructure, with GStreamer as a reference |
| 10-bit HEVC | separate kernel work | unknown — no 10-bit format plumbed in mainline cedrus |

Recommended order: **decode-to-file first, display second.** Validate the shim
against the existing bit-exact references with no display involved, so a failure
lands in one half or the other rather than both.

And the standing alternative, which needs no shim at all: GStreamer already
decodes both H.264 and HEVC on this hardware today. What it lacks is only a sink
that reaches the panel without a CPU copy — see the GStreamer sink option in the
video-decode notes.
