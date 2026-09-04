# H713 handoff — 2026-09-03 (playback and packaging)

Second handoff of the day. The first,
[handoff-2026-09-03-video-decode.md](handoff-2026-09-03-video-decode.md),
covers the zero-copy VA-API investigation and is still accurate about **decode**.
This one covers what happened after it: packaging the patched mpv so it survives
a reflash, and discovering that `vo=drm` had never actually displayed anything.

**Headline: video and audio now play together on the panel, operator-confirmed.**

---

## 1. State right now

| | |
| --- | --- |
| repo | `fddcb6c` on `h713-display-video-path`, **pushed**, in sync with origin |
| working tree | clean except the pre-existing `external/u-boot` submodule modification — leave it |
| board | up at `root@192.168.4.1` over its own WiFi AP, ~8.5 h uptime |
| kernel | `6.18.38 #1 SMP Thu Sep 3`, includes out-of-series patch 0092 |
| VA driver | series `f4b13b628e610aa2`, 7 patches, installed 14:03 |
| mpv | series `b8ba2246d667e4c6`, **2 patches**, installed 17:05, at `/usr/local/bin/mpv` |
| board disk | **91 MB free of 2.7 GB (97 % full)** — this constrains everything |

Verify all of it in one command:

```bash
tools/video/check-video-stack.sh
```

It now covers three components (cedrus, VA driver, mpv) and exits non-zero on
drift. Expect it to report DRIFT on the **cedrus module** — no module is built
for `KERNEL_CONFIG=sysrq` under `build/`. That is pre-existing and unrelated to
video; the VA driver and mpv sections both read MATCH.

### On the board, left deliberately

```text
/root/leota-av-720p.mp4   4.5 MB  720p H.264 High + AAC 44.1k stereo, 77 s
/root/av-test.sh                  plays it once through the direct path
/root/av-loop.sh                  same, looping (for sampling plane state)
/root/leota-720p.h264             video-only, what the --test gate uses
/usr/local/bin/mpv.*.bak    2 x   PRE-FIX binaries, both display nothing
```

The two `.bak` files are ~4.5 MB on a disk with 91 MB free. Delete them once
you trust the current build; they are only useful as negative controls.

---

## 2. What this session finished

### mpv is packaged and reproducible

`tools/video/build-mpv.sh` builds the patched mpv **in an emulated arm64
container** and installs it. It cannot build on the board — that was measured,
not assumed: the rootfs is 2.7 GB at ~97 % full and freeing 126 MB of stale
kernel images was nowhere near enough for a build tree plus ~10 dev packages.

```bash
tools/video/build-mpv.sh                        # build + verify, no install
tools/video/build-mpv.sh --install --test       # the full path, ~20 min
tools/video/build-mpv.sh --test                 # gate the board, no rebuild
tools/video/build-mpv.sh --rebuild-rootfs       # after changing DEPS
```

Host prerequisites are checked first and named exactly. The one that matters:
**`debian-archive-keyring` must be installed**, not merely cached in
`build/cache` as a `.pkg.tar.zst`. Its absence makes apt reject every Debian
repository as unsigned, and it cost four failed attempts that all looked like
key-*format* problems.

The 1.1 GB rootfs tarball is cached in `local/upstream/mpv-arm64/` (gitignored,
2.3 GB with the extracted tree). Safe to delete; `--rebuild-rootfs` regenerates
it in ~5 minutes.

**Building off-target loses the guarantee that the binary links against the
board's libraries**, so the script runs `ldd` on the board after installing and
fails on any `not found`. That check is not decorative: mpv links
`libdisplay-info.so.2`, which happens to be present only because something else
in the image pulls it in.

### `vo=drm` displayed nothing, and now does

`mpv --vo=drm --hwdec=vaapi` had **never put a picture on the panel**. It was
found the first time anyone played a clip with an audio track and looked at the
screen: sound correct, panel black.

`flip_page()` validated the next queued frame with `!frame->fb`. A PRIME frame
stores its framebuffer in `prime_fb.fb_id` and leaves `->fb` NULL —
`enqueue_prime_frame()` never sets it. So every decoded frame matched the
`Hole in swapchain?` branch and was dequeued without `queue_flip()` ever
running, and the video plane was never given an `FB_ID`. What reached the panel
was the black primary plane.

Fixed in
[`patches/mpv/0002-vo_drm-flip-PRIME-frames-not-swapchain-holes.patch`](../patches/mpv/0002-vo_drm-flip-PRIME-frames-not-swapchain-holes.patch).

Decode, dma-buf export and every atomic commit were healthy throughout. The
frames were discarded at the last step.

### The gate reads the kernel now, not mpv's opinion

This is the part worth carrying forward. `--test` used to grep mpv's log for
`Using direct DRM PRIME video-plane scanout` and report PASS. mpv prints that
when it **selects** the path, not when a frame reaches the screen — so the gate
passed a permanently black panel, and did so for as long as the patch existed.

It now reads `/sys/kernel/debug/dri/*/state` while playback runs and requires:

- the drmprime plane is attached to a CRTC;
- it holds a framebuffer;
- **that framebuffer changes between two samples** — a frozen fb id is a still
  picture, which no mpv log line distinguishes from working video;
- zero `Hole in swapchain?`;
- no new IOMMU faults or Cedrus timeouts in `dmesg` during the run.

Verified in **both** directions, which is the only thing that makes it credible:

```text
                          fixed         pre-fix
plane crtc                crtc-0        (null)
plane fb                  47 -> 48      0 -> 0
swapchain holes           0             297
old (log-only) verdict    PASS          PASS
new verdict               PASS          FAIL
```

The pre-fix binary is still on the board if you want to re-run that control.

### Smaller fixes made while verifying

- **`build-va-driver.sh` truncated `/etc/h713-video-stack` with `>`**, erasing
  the `mpv_` keys. Both scripts now strip only their own keys and append.
- **`check-video-stack.sh` gained an mpv section**, plus a check that PATH
  actually resolves to `/usr/local/bin/mpv` — a stock `/usr/bin/mpv` winning
  would revert the video path while every stamp still read MATCH.
- **`hevc-10bit-test.sh:71`** died with `hw_frame: unbound variable` when
  `gst.raw` was missing: an inline division failed under `set -u` (there is no
  `set -e`), so a shell error was being reported as a driver failure. The VA1
  gate means something now.
- **`strings … | grep -q` under `set -o pipefail`** rejected a correct binary —
  `grep -q` exits early, the producer takes SIGPIPE, pipefail fails the
  pipeline. Cost one full container build. Both such checks use process
  substitution now.

---

## 3. What to do next

In rough order of value.

1. **Soak playback.** Everything so far is minutes-long runs. The decode path
   has a 2 h / 195 k-frame soak behind it; the *display* path has nothing
   comparable since the fix. Loop `/root/leota-av-720p.mp4` for an hour with
   `dmesg` watched. Note the standing hazard about MIPS below before doing it.
2. **Audio/video sync over a long run.** The 77 s clip stayed in sync by ear.
   Nothing has measured drift, and the audio PLL history (172 MHz, 4.8 % slow)
   makes this worth an actual measurement rather than an impression.
3. **Decide patch 0092's shipping policy.** `DRIVER_RENDER` on a display-only
   device advertises a capability the hardware lacks, but it is in the kernel
   that every successful result was measured on. Out of series today. Do not
   mistake the mpv fix for evidence that 0092 is unnecessary.
4. **10-bit HEVC through the shim.** Decodes today via GStreamer at 57 dB PSNR;
   the shim refuses Main10 only because it advertises Main. Cheapest win is to
   advertise Main10 and decode to NV12. See `docs/hevc-10bit-findings.md`.
5. **HDMI input** — still blocked on HPD, still the biggest feature, still
   multi-week. `0x07091014` is not ARM-addressable and needs running ARISC
   firmware. Read [arisc-route-scope.md](arisc-route-scope.md) before starting;
   the load address is the one unknown that could dominate everything else.
6. **`sun50i_h713/platform.mk` says "Without a management processor there is no
   SCPI support"** — wrong, the H713 has an ARISC. Left alone because the TF-A
   submodule is clean and there is no `patches/atf/` to carry the change.

---

## 4. Standing hazards

Unchanged from the previous handoff, and all still live:

- **`0x07091014` hard-locks the board on a plain read.** Twice. `0x07090000` is
  the RTC and is fine; it is `0x07091000` specifically.
- **Do not run real Cedrus traffic with the display MIPS alive** — hard-locks
  the SoC, no watchdog. mpv playback is fine today because the MIPS is parked.
- **Do not enable the vendor `sunxi-tvtop`** — its node claims `GIC_SPI 110`
  (the KMS driver's AFBD interrupt) and carries `panel_bl_en` = **PB5, the
  backlight *and* fan enable**.
- **PB5 is backlight and fan; never hold it low.**
- **Do not give the MIPS the AFBD block** — it removes the NV12 KMS plane the
  drmprime path depends on.
- **Check `pm_genpd_summary` and `clk_summary` before the first access to any
  new MMIO window**, and for clocks check the CCU register too, since
  `clk_summary` reports a refcount, not a hardware gate.
- **The board disk has 91 MB free.** Anything that writes to it needs the space
  checked first; this already made an on-board mpv build impossible.

Recovering a kernel that hangs at probe — U-Boot reads the rootfs, and
`install-kernel-fit.sh` leaves every previous kernel there:

```text
=> ext4load mmc 1:1a 0x50000000 /root/fits/replaced-<stamp>.fit
=> bootm 0x50000000
```

**U-Boot parses partition numbers as HEX** — the rootfs shown as partition 26 is
`mmc 1:1a`.

---

## 5. Method lessons, and one correction

**The correction:** the previous handoff and `patches/mpv/README.md` both
described `vo=drm` as verified. It was not. The evidence was mpv's own log plus
a separate `vo=gpu` run, and `vo=drm` had almost certainly been black since the
patch was written. Both documents now carry that correction inline rather than
having the false claims deleted — including a paragraph that reports the plane
as *detached at exit*, which reads as though it had been attached during
playback. It never was.

**The lesson that produced it.** Every instrument in play reported the component
it owned, correctly, and the composite was still broken:

| instrument | answered | did not answer |
| --- | --- | --- |
| mpv's log | did I select the path | did anything display |
| marker grep | did the patch compile in | does it work |
| VA gates | did decode produce right bytes | did the bytes reach a plane |
| kernel `dmesg` | did anything fault | (nothing faulted — correctly) |

**Nobody asked the display whether anything was on it.** When the deliverable is
a picture, one look at the panel outranks every log in the stack — and the
automated stand-in for that look is the plane state, not the player's narration.

This is the same shape as the scaling-list blind spot from 2026-08-22, where
every H.265 vector had `scaling_list_enabled_flag = 0` so a shim passing no
scaling matrix scored bit-exact on all of them. **Ask what a passing suite
cannot fail on.**

Two smaller ones, both of which cost real time today:

- **A gate you cannot afford to run stops being run.** `--test` used to require
  a 20-minute emulated rebuild first. It now gates what is installed.
- **Verify a gate can fail before trusting that it passed.** The plane-state
  gate is only credible because it was run against the broken binary and
  produced the exact diagnosis.

---

## Addendum — the resolution question, answered 2026-09-03 (later)

### Hardware playback works at 1280x720 only

| content | path | result |
| --- | --- | --- |
| 1280x720 | `--vo=drm --hwdec=vaapi` | **works**, operator-confirmed |
| 1920x1080 | `--vo=drm --hwdec=vaapi` | refused; plays audio only |
| 1920x1080 | `--vo=drm --hwdec=vaapi-copy` | ~0.2x realtime, audio 41 s ahead — unusable |
| 1920x1080 | stock mpv `--vo=gpu` (Panfrost) | ~0.83x realtime, sync fine, **481 dropped frames, visible artifacts** |

The GPU path is the only one that puts 1080p on the panel at all, and it does so
badly. It also needs the **stock** `/usr/bin/mpv`: our build is `-Dgl=disabled`
on purpose, so `gpu-context=drm` is not compiled into it.

### The scaler at 0x05000000 is NOT in our path

`docs/reference/firmware-display-block-survey-2026-08-31.md` identifies
`0x05000000` as a scaler and decodes its encoding — ratios in 1/64 units with
`0x40` as unity, luma/chroma height pairs for two coordinate spaces. Read live
on 2026-09-03 it holds exactly that:

```text
+0x174 0x00400040   +0x178 0x6002021C (540)   +0x1b8 0x60020438 (1080)
+0x274 0x00400040   +0x278 0x60020168 (360)   +0x2b8 0x600202D0 (720)
```

**But it stayed completely inert through a real playback on our path.** The RE
saw bit 31 set when a stock frame lands; across before/during/after samples of a
working DECD playback it never moved. Our driver maps `route` (0x5140000),
`lvds` (0x51C0000) and DECD (0x5600000) — that scaler belongs to the MIPS
pipeline. **Programming it is not the route to a scaling KMS plane.**

The open lead is DECD itself: its source geometry is programmable (the four
source-geometry words that fixed the horizontal repeat carried an inherited
1920x1088 fallback), so it distinguishes source from output. Whether it *scales*
between them or merely crops is **unknown and untested**. Establish that before
writing any driver code.

### An unbounded retry loop wedged the display — patch 0003

Feeding 1080p to the direct path produced **890,454** failed atomic commits
(`ERANGE`) with the clock frozen at `00:00:00` and audio playing. The geometry
guard checked "uncropped" and "fullscreen" but never that the two were **the
same size**, so any non-native resolution passed it and asked a plane that
cannot scale to scale.

Every retry reprograms the plane. That is not wasted cycles: it faulted the
video source on **IOMMU master 2** (`0xf8e12000`, adjacent to the RGB
framebuffer's `0xf8c00000`) and left the video plane showing black for the
720p clip that had worked minutes earlier. A power cycle cleared it.

[`0003-vo_drm-refuse-to-scale-and-stop-retrying-a-doomed-flip.patch`](../patches/mpv/0003-vo_drm-refuse-to-scale-and-stop-retrying-a-doomed-flip.patch)
rejects the scaling request up front, and independently abandons the direct path
after 60 consecutive failed flips. Verified: 890,454 failures → **0**, no
faults, plane never attached, 720p unregressed.

The `--test` gate now fails on any failed flip, which it previously ignored.

### Method note

The scaler was ruled out for free — three register reads around a playback,
no operator time, no visible test. The wedge that cost a power cycle came from
running a hardware path *before* asking what it would do when refused. **The
cheap measurement first; the destructive experiment never without a bound on
it.**
