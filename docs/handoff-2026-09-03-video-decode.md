# H713 handoff — 2026-09-03

Written at the end of a session that finished audio, opened and then blocked
HDMI input, and got mpv playing hardware-decoded video. The zero-copy
investigation that was live in the first draft is now **resolved** in §4.

Read alongside: [video-decode.md](video-decode.md) (the live investigation),
[audio.md](audio.md), [hdmi-in.md](hdmi-in.md),
[arisc-route-scope.md](arisc-route-scope.md).

---

## 1. Board and repo state RIGHT NOW

| | |
| --- | --- |
| repo | HEAD `ed9ba46`; patch 0007 and this handoff are uncommitted; preserve the pre-existing `external/u-boot` modification |
| board | up, reachable at `root@192.168.4.1` over its own WiFi AP |
| kernel | `#1 SMP Thu Sep 3 00:17:09 PDT 2026` — includes out-of-series patch 0092 |
| VA driver | **CLEAN BUILD INSTALLED** via `tools/video/build-va-driver.sh --install --test`; series id `f4b13b628e610aa2`, `__vaDriverInit_1_22` verified against the board's libva. Zero-copy re-confirmed on it |
| autoboot | `bootdelay=5`, saved; the board reaches Linux + WiFi unattended |

**Restoring the pre-investigation VA driver** (this also removes the zero-copy
fix, so use it only as a control):

```sh
ssh root@192.168.4.1 'cd /root/va-driver-build/src &&
  cp picture.c.orig-preprintf picture.c &&
  cp surface.c.orig-preprintf surface.c &&
  cp v4l2.c.orig-preprintf v4l2.c &&
  cd /root/va-driver-build && ninja -C build &&
  cp build/src/v4l2_request_drv_video.so /usr/lib/aarch64-linux-gnu/dri/'
```

There is also a pristine binary at
`/usr/lib/aarch64-linux-gnu/dri/v4l2_request_drv_video.so.orig-preprintf`.

**Recovering a kernel that hangs at probe** — U-Boot reads the rootfs, and
`install-kernel-fit.sh` leaves every previous kernel there:

```text
=> ext4load mmc 1:1a 0x50000000 /root/fits/replaced-<stamp>.fit
=> bootm 0x50000000
```

14.9 MiB/s, no host transfer. **U-Boot parses partition numbers as HEX** — the
rootfs shown as partition 26 is `mmc 1:1a`.

---

## 2. Finished this session

**Audio playback is DONE** (patches 0082–0086, in series). 440.01 Hz at 44.1 kHz
and 440.00 at 48 kHz, correct volume law, amp following playback. Three things
were wrong and are now right: the speaker is on the **headphone amp** not
LINEOUT; bit 15 alone is correct; and the audio PLL never left its 172 MHz boot
value, making everything play 4.8 % slow.

**Analog audio capture is CLOSED, negatively.** The board has no microphone and
no analog input — confirmed by the owner, after RE of the stock image showed
every capture path referenced but never defined. Patch 0091 (ADC path) is
out-of-series and should not be finished. **HDMI-in audio is unaffected** and is
a separate, digital path; see [hdmi-in.md](hdmi-in.md).

**mpv plays hardware-decoded video today**, with no source changes:

```sh
LIBVA_DRIVER_NAME=v4l2_request mpv --vo=drm --hwdec=vaapi-copy clip.h264
LIBVA_DRIVER_NAME=v4l2_request mpv --vo=gpu --gpu-context=drm --hwdec=vaapi-copy clip.h264
```

The handoff's old claim that mpv was blocked on a missing render node was
**false**: mesa pairs our display-only `card0` with panfrost's `renderD128` by
itself, and `vo=gpu` reaches `GL_RENDERER='Mali-G31 (Panfrost)'`. The only
missing piece was the `LIBVA_DRIVER_NAME` environment variable.

Measured, 300 frames, startup amortised:

```text
720p   vaapi-copy vo=null 137 fps   software vo=null 207 fps   vo=drm 97 fps
1080p  vaapi-copy vo=null  91 fps   software vo=null 174 fps   vo=drm 58 fps / vo=gpu 41 fps
```

Software decode beats hardware-decode-plus-copy at both resolutions: the
readback costs more than four A53s spend decoding. So `vaapi-copy` is a
CPU-offload win, not a throughput win, and **zero-copy is the point, not an
optimisation**.

**True zero-copy now works as well.** The final command and evidence are in
§4. mpv reports `VO: [gpu] 1280x720 vaapi[nv12]`, its decoded surfaces are
exported directly as dma-bufs, and there is no `hwdownload` fallback.

---

## 3. Blocked elsewhere

**HDMI input** is blocked on HPD. Every ARM-side explanation is eliminated —
power domain, clock gate and reset all confirmed already enabled
(`0x0701022c = 0x00010001`). `0x07091014` is not ARM-addressable; HPD needs
running ARISC firmware. Scoped in [arisc-route-scope.md](arisc-route-scope.md):
multi-week, boot-path change, PSCI blast radius, one dominating unknown (the
firmware load address). **Do not start casually.**

---

## 4. RESOLVED — zero-copy `--hwdec=vaapi`

### Root cause

The handoff's prime suspect, `request_fd < 0`, is refuted. On the failing path
the request fd was valid (`18`), both QBUFs succeeded, and
`media_request_queue()` succeeded. The wait then timed out after 300 ms. The
kernel logged the matching cause:

```text
sun50i-iommu ... Page fault for 0x... (master 0, dir rd)
cedrus ... frame processing timed out!
```

Master 0 is the VE. The bad address was not a display-lifetime problem; Cedrus
had been given a capture allocation much smaller than the picture it was
decoding.

The complete surface trace exposed the setup sequence:

1. mpv probes VA/EGL interop by creating and exporting two **128x128** surfaces.
2. It destroys those VA objects.
3. It then asks for the real **1280x720** decoder surfaces.

`libva-v4l2-request` had two coupled lifetime bugs. Its process-global
`SET_FORMAT_OF_OUTPUT_ONCE` remained latched at 128x128, and
`RequestDestroySurfaces` unmapped userspace but never released the V4L2
`CREATE_BUFS` allocations. The later surfaces therefore remained 24,576-byte
128x128 buffers even though Cedrus decoded a 1280x720 picture into them. The VE
read past the allocation, faulted in the IOMMU, and never completed the media
request. The later double-QBUF/EINVAL was only fallout from that first timeout.

### Fix

Production patch
[`0007-Release-probe-buffers-before-decoder-format.patch`](../patches/libva-v4l2-request/0007-Release-probe-buffers-before-decoder-format.patch)
does three things:

- replaces the process-wide boolean with the complete format currently
  programmed on the OUTPUT queue;
- releases both V4L2 queues when the final pre-context VA surface disappears,
  so mpv's real decoder geometry can be set legally;
- backs libavutil's later 16x16 upload-probe surface with the active 1280x720
  queue geometry. A streaming V4L2 mem2mem queue has one format; the VA object
  still keeps its requested logical dimensions.

The third item matters. Without it decode requests all completed, but mpv's
16x16 helper allocation hit `S_FMT: EBUSY`, so filter negotiation performed a
CPU hwdownload. With it, mpv keeps the true dma-buf interop path.

### Hardware proof

```sh
LIBVA_DRIVER_NAME=v4l2_request \
mpv --no-config --no-audio --vo=gpu --gpu-context=drm \
    --gpu-hwdec-interop=vaapi --hwdec=vaapi \
    --loop-file=inf /root/leota-720p.h264
```

A 20-second paced run played visibly moving video (operator-confirmed) and
completed five loops / 300 frames:

```text
Using hardware decoding (vaapi).
VO: [gpu] 1280x720 vaapi[nv12]
capture QBUF=300  capture DQBUF=300  decode failures=0  hwdownloads=0
```

The decoded 1280x720 surfaces were exported as 1,382,400-byte dma-bufs. An
independent 300-frame untimed stress run also balanced QBUF/DQBUF at 300/300,
with no new IOMMU fault or Cedrus timeout in `dmesg`. This establishes decode,
queue lifecycle, zero-copy negotiation, and visible presentation separately.

Patch 0007 applies cleanly to the six-patch pinned driver.

**Packaging is now complete.** `tools/video/build-va-driver.sh --install --test`
rebuilt the driver from the series on the board, verified `__vaDriverInit_1_22`
against the board's own libva 1.22, and installed it (outgoing driver kept as
`.20260903-140330.bak`). Zero-copy re-verified on that clean, un-instrumented
build:

```text
Using hardware decoding (vaapi).
VO: [gpu] 1280x720 vaapi[nv12]
decode failures: 0
```

So the result does not depend on any debug build. One caveat from the same run:
the script's gates report `VA1: 4 pass, 1 fail`, but that failure is a **bug in
the test**, not the driver — `hevc-10bit-test.sh:72: hw_frame: unbound
variable`, a shell error under `set -u`. Worth fixing so the gate means
something.

### Refuted explanations

- invalid or prematurely consumed request fd;
- surface state reset by `image.c`;
- sync targeting a different surface;
- capture memory-type mismatch;
- EGL retaining decoded buffers too long;
- missing render node.

---

## 5. Method lessons that cost real time

This session produced **four retractions**. Every one came from instrumentation
that did not show what it was assumed to show, not from bad measurements.

- **Never insert a statement before a `return` without checking for braces.**
  Adding an `fprintf` before the return of a braceless `if` made that return
  unconditional, so the driver failed on every call and four rounds were spent
  investigating the breakage. **Read the patched source after editing.**
- **Do not truncate a trace you are reasoning from.** A `head -12` cut a
  sequence mid-way and produced a confident, wrong "half-allocated surface"
  root cause.
- **Instrument every exit, not only the ones returning the error you chase.**
  Two exits that propagated a callee's status were missed and produced a wrong
  "never dispatched" conclusion.
- **"Entry" logging must be the first line.** A log placed after early returns
  reported a function as never called when it was called and exiting early.
- **Check what the interface actually returns.** EINVAL was used to rule out a
  correct hypothesis, on the assumption that a busy buffer must give EBUSY.
- **Check the instrument can show a positive before reading silence as a
  negative.** Applied to a compiled-out TF-A message, and to `clk_summary`
  showing a refcount rather than a hardware gate.
- **Always run the working path as a control in the same session.** It is what
  proved the instrumentation was not itself changing behaviour the second time
  around.

---

## 6. Other open items

- **`vo=drm` returns EINVAL from an atomic commit on teardown**, after playing
  to EOF. `vo=gpu` does not. Our driver, unexplained, harmless so far.
- **HDMI-in audio** — digital, via the audio bridge or i2s2/owa on
  `CLK_HDMI_AUDIO`, behind the same TVFE/TVCAP gate patch 0087 opens. Gated on
  HPD, but likely easier than HDMI video since it probably does not need the
  MIPS. Try it before video once HPD works.
- **`sun50i_h713/platform.mk` says "Without a management processor there is no
  SCPI support"** — that is wrong, the H713 has an ARISC. Worth correcting
  regardless of whether the ARISC route is pursued.
- **Patch 0092** (`DRIVER_RENDER` on a display-only device) is out of series. It
  advertises a capability the hardware lacks, but it remains part of the kernel
  used for the successful zero-copy proof because it lets mpv establish the VA
  display. Decide its shipping policy separately; do not mistake patch 0007's
  driver fix for evidence that 0092 is unnecessary.

## 7. Standing hazards

- **`0x07091014` hard-locks the board on a plain read.** Twice. `0x07090000` is
  the RTC and is fine; it is `0x07091000` specifically.
- **Do not enable the vendor `sunxi-tvtop`** — its node claims `GIC_SPI 110`
  (the KMS driver's AFBD interrupt) and carries `panel_bl_en` = **PB5, the
  backlight and fan enable**.
- **Do not give the MIPS the AFBD block** — it would remove the NV12 KMS plane
  the drmprime path needs and force a bespoke client.
- **PB5 is backlight *and* fan; never hold it low.**
- **Check `pm_genpd_summary` and `clk_summary` before the first access to any
  new MMIO window** — and for clocks, check the CCU register too, since
  `clk_summary` reports a refcount.
- Do not run real Cedrus traffic with the display MIPS alive — hard-locks the
  SoC, no watchdog.
