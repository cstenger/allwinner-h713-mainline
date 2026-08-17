# Hardware decode for stock players — VA-API scope

Written 2026-08-16. Answers one question with numbers rather than estimates:
**what would it take for `mpv` (and anything else using ffmpeg) to decode on the
VE instead of the CPU, without patching mpv, ffmpeg or GStreamer?**

The short version: the chain is real, the H.264 half is nearly free, the HEVC
half is a rewrite, and 10-bit is blocked in the kernel rather than in userspace.

---

# RESULT — H.264 decodes on the VE through stock ffmpeg, 2026-08-16

**Done, and validated bit-exact on hardware.** `libva-v4l2-request` (PR #38 plus
[three patches](../patches/libva-v4l2-request/)) drives cedrus from unmodified
ffmpeg. All five vectors of the M1 ladder — 320x240 baseline through 1920x1080
high — decode **bit-exact** against the host-generated references, and the VE's
interrupt count rises by exactly one per frame, so the hardware is doing it.

| | |
| --- | --- |
| `vainfo` | loads `__vaDriverInit_1_22`, advertises 5 H.264 profiles, `VAEntrypointVLD` |
| bit-exactness | 5 of 5 vectors, `tools/video/va-decode-test.sh` |
| decode cost | **1.233 s wall / 0.637 s CPU** for 60 frames of 1080p (software: 2.72 s CPU) |
| what blocked it | *not* the codec — the shim created the bitstream queue with zero buffers, because ffmpeg no longer preallocates a VA surface pool. See patch 0003. |

**The one number to carry into the display work:** copying decoded frames back
to system memory with `hwdownload` costs *more than the decode* (1.8 s extra for
186 MB of 1080p) because V4L2 MMAP buffers are uncached. Decode-to-file pays
that; a display path that maps the surface as a dma-buf does not.

## The display path — plays on the panel, and crashes the kernel intermittently

Step 6 was attempted the same session. It gets **all the way to video on the
panel**: `mpv` hardware-decodes on the VE and renders through EGL-on-GBM against
our KMS driver, and a 1200-frame 720p25 clip has played to completion.

The two things worth knowing before picking this up:

**1. It must be `--hwdec=vaapi-copy`, not `--hwdec=vaapi`.** Plain `vaapi`
fails with `Could not create a VA display`, and the reason is structural rather
than a misconfiguration: mpv's `vo=gpu` DRM path asks for a **render node on the
KMS device** (`drm_params_v2.render_fd`) and our display-only driver has none —
`renderD128` belongs to panfrost on `card0`. `--vaapi-device` is accepted and
*ignored* on this path. Our shim ignores the DRM fd entirely, so any node would
do; mpv just will not offer one. Patching mpv is out of scope by standing
constraint, so `vaapi-copy` — which builds its own VA display and honours
`--vaapi-device` — is the working invocation:

```
LIBVA_DRIVER_NAME=v4l2_request mpv --hwdec=vaapi-copy \
  --vaapi-device=/dev/dri/renderD128 \
  --vo=gpu --gpu-context=drm --drm-device=/dev/dri/card1 clip.mp4
```

That costs the copy-out measured above. Zero-copy would need either a render
node on `card1` or the `drmprime-overlay` path (mpv reports `Failed to find
drmprime plane with idx=-2` today).

**2. It panics intermittently — and it is memory corruption, not a codec bug.**
Two of four runs of the same 48-second clip took the board down. Captured on
serial:

```
Unable to handle kernel NULL pointer dereference at virtual address 0000000000000010
CPU: 3  Comm: kworker/u16:1
Workqueue:  0x0 (pan_js)             <- panfrost job scheduler, work fn is NULL
pc : stmmac_hw_setup+0x844/0xbd4     <- nonsense; this board has no Ethernet
Call trace: dequeue_entities / dequeue_task_fair / __schedule / worker_thread
...
cedrus 1c0e000.video-codec: frame processing timed out!
rcu: INFO: rcu_sched detected stalls on CPUs/tasks: 0-...! 1-...! 3-...!
```

A workqueue whose work function is `0x0` and a PC that resolves to an unrelated
built-in symbol are both signatures of **corrupted kernel memory**, not of a
driver returning an error. It surfaces in panfrost's job scheduler because that
is what runs constantly during playback, which does not mean panfrost is the
culprit. In play: `sun50i_h713_afbd`, `sunxi_cedrus`, `sunxi_scanout_dmabuf`,
`panfrost`.

**The controls say it is the combination, not either half:**

| run | result |
| --- | --- |
| hardware decode, `--vo=null`, 48 s / 1200 frames | **stable** (VE IRQ count exactly 1200) |
| software decode, on the panel, 48 s | **stable**, played to completion |
| hardware decode **on the panel**, 48 s | **2 of 4 runs panicked** |

**Start the next session by making the crash legible rather than by guessing:**
build the kernel with **`CONFIG_KASAN`** and reproduce — a use-after-free or an
out-of-bounds write is exactly what KASAN names in one run, and this tree has
form here (`patches/kernel/0034-misc-decd-fix-oob-write-in-vsync-handler.patch`).
Add **`CONFIG_PSTORE`/ramoops** so a panic survives the reboot (nothing reached
the journal — journald cannot flush during a panic), and **`CONFIG_MAGIC_SYSRQ`**,
whose absence has now cost two physical power cycles this session.

**Still open:** the crash above, zero-copy display, HEVC in the shim, and 10-bit.

---

# HANDOFF — start here, 2026-08-16

**The decision already made:** do not patch mpv, ffmpeg or GStreamer. Adapt our
own code to fit them. That is what makes libva-v4l2-request the route — it is a
VA-API *driver*, so stock players use it unmodified.

**The goal for the next session:** ~~get `libva-v4l2-request` decoding H.264 on
the VE, validated to bit-exactness with no display involved~~ — **done, see
RESULT above.** What remains is the display path, and it is deliberately the
next thing rather than something to have done at the same time: with decode
proven bit-exact on its own, a playback failure now has only one place to hide.

## Board state as of this handoff

| | |
| --- | --- |
| Kernel | `6.18.38`, built from the current series, **persisted** to the FAT (`fatwrite mmc 1:2 h713-kernel.fit`) and booting from it via `bootcmd` |
| Rootfs | **reflashed 2026-08-16** with `--profile dev`, which now also carries `vainfo` and `gdb`; `/` is 4.5 G with ~3.1 G free |
| KMS | `sun50i-h713-afbd` autoloads at boot, but **did not probe on this boot** — the panel needs the U-Boot incantation below, which decode work skips. `/dev/dri` therefore has only `card0`/`renderD128` (panfrost) |
| VA-API | driver installed at `/usr/lib/aarch64-linux-gnu/dri/v4l2_request_drv_video.so`, source + build tree in `/root/libva-v4l2-request` |
| `/root` | `video-test/` (the five M1 vectors, `reference-md5.txt`, `m1-decode-test.sh`, `va-decode-test.sh`), `libva-v4l2-request/`, `h713-va-bringup.tar.gz` |
| Missing for this work | nothing |

The vectors and the patched source were put there by injecting a tarball into
`rootfs.ext4` with `debugfs -w -R "write ..."` before `img2simg` — no root
needed, and it beats pushing 2.4 MB over a serial console after every flash.

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
- **WiFi gets you ssh, and it took the board down.** `tools/wifi/sta-connect.sh`
  turns the boot hotspot into a station on a real network; ssh then works at
  3.6 ms and file transfer stops being the constraint. But the first sustained
  use of that link — an `apt-get update` — **wedged the board hard**: no ssh, no
  serial, tty echo alive but the shell dead. This kernel has no
  `CONFIG_MAGIC_SYSRQ`, so recovery was a physical power cycle. Keep the serial
  console attached, and prefer baking what you need into the image.
- **The board's clock can be months behind**, which makes `meson setup` abort
  with `Clock skew detected` on files newer than "now". `date -u -s` from the
  host, then `hwclock -w`.
- **`/tmp` is a 467 MB tmpfs.** One 1080p vector decodes to 186 MB of raw NV12,
  so a ladder run fills it and ffmpeg's ENOSPC leaves a *truncated file with a
  valid md5* — which scores as a MISMATCH and reads as a decode bug. Write raw
  output to `/var/tmp`.

## The plan, in order

Steps 1–5 are **done** (2026-08-16); they are kept here because they are how you
reproduce the result, not as work outstanding.

1. ~~Rebuild and reflash the rootfs~~ — done. `tools/rootfs/build.sh --ssh-key
   KEY --kernel-tree build/linux-6.18.38-<hash> --profile dev --image-size 4G`,
   then `run fastboot_mode` at the U-Boot prompt and `fastboot flash UDISK
   rootfs.simg`. The 1.4 GB sparse image uploads in 45 chunks / **6 min**.
2. ~~Clone and fix the driver~~ — done, and the fixes are now a tracked series
   in [`patches/libva-v4l2-request/`](../patches/libva-v4l2-request/) on the
   pinned PR #38 head. There were **three**, not two: the missing `#include`,
   the vestigial `hevc-ctrls.h`, and the one that actually blocked decoding
   (patch 0003, the empty bitstream queue).
3. ~~Build on the board~~ — done, ~40 s. Build **on the board** and nowhere
   else: the driver's entry point is `__vaDriverInit_<major>_<minor>` taken from
   the libva version at build time, so a host build against libva 1.24 produces
   a `.so` the board's 1.22 loader will never call.
4. ~~`vainfo`~~ — passes; five H.264 profiles, `VAEntrypointVLD`, nothing else
   advertised.
5. ~~Decode to a file and check it byte-for-byte~~ — **5 of 5 bit-exact**, via
   `tools/video/va-decode-test.sh`.
6. **The display path** — attempted, and it plays; see the section above for the
   `--hwdec=vaapi-copy` requirement and the intermittent kernel panic that is
   now the open problem. Note `card1` only exists if the panel was brought up
   first with `h713_disp auto 0x34 logo` at the U-Boot prompt; on a decode-only
   boot there is no KMS device at all. To get back to that prompt without a
   human at the power switch, `tools/serial/reboot-to-uboot.py` reboots and
   types through the autoboot delay.

## What to expect to go wrong

The prediction below was written before step 5 ran. It was right that the
runtime was the risk and wrong about where: the failure was not in the codec
mapping at all, but in buffer allocation — the shim assumed a VA-API client
contract (a preallocated surface pool) that ffmpeg no longer follows. Worth
remembering as a pattern: *the error message named the codec, and the codec was
fine.* `strace` found it in one run; reading h264.c would not have.

> The compile is measured and safe; the *runtime* is not. PR #38 is unmerged
> third-party work whose own commit message says "POC", developed against H3/A64
> VEs rather than this one. Our cedrus is proven bit-exact through GStreamer, so
> the kernel half is sound — what is unproven is whether this shim drives it
> correctly. If step 5 produces frames that are *close but not identical*,
> suspect the reference-list or DPB mapping before suspecting the hardware.

That last sentence never got tested: the frames were identical on the first run
that reached the decoder. The DPB and reference-list mapping in PR #38 is
correct for H.264 on this VE across all five vectors — and the ladder is built
to exercise exactly that, since `v03` and `v04` are `bframes=2:cabac=1:ref=3`,
so reference list construction and reordering are under test rather than
assumed.

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
