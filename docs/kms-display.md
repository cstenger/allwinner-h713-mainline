# KMS for the H713 panel

Started 2026-08-15. Gives the projector a DRM card node so ordinary DRM
clients — `mpv --vo=drm`, a compositor, fbcon — can present on the panel,
instead of every program mapping `0x05600000` through `/dev/mem` and
reimplementing the AFBD commit sequence for itself.

> **The card number changed on 2026-08-24 and every `card1` below is stale.**
> The driver became built-in (`CONFIG_DRM_SUN50I_H713_AFBD=y`) so the boot log
> would reach the panel, and it now probes before panfrost's module loads:
> **the panel is `card0` and panfrost is `card1`**, the reverse of what this
> document records. The numbering is only ever probe order — resolve it at
> runtime rather than hardcoding either value:
>
> ```bash
> for d in /sys/class/drm/card*/device/driver; do
>   [ "$(basename "$(readlink -f "$d")")" = sun50i-h713-afbd ] && echo "$d" | cut -d/ -f5
> done
> ```
>
> Note also that **`kmssink` needs `driver-name=sun50i-h713-afbd`** — its
> auto-detection only tries a hardcoded list of driver names that this one is
> not on, and never worked here. See
> [`handoff-2026-08-24-display.md`](handoff-2026-08-24-display.md).

**Status: WORKS, hardware-verified on the bench board 2026-08-15.**

| | |
| --- | --- |
| Probe | `adopting 1280x720, stride 5120, source 6c100000` — geometry read back from the hardware, not configured |
| Page flips | **1320 flips across three runs at 59.71 fps, 0 timeouts** — the panel's exact rate, and the same number gles-play measured |
| Persisted | the FIT is written to the FAT (`fatwrite mmc 1:2`, 7,739,380 bytes); the board boots it via `bootcmd` with `sha256+ OK` on kernel and FDT, and the driver behaves identically from that boot |
| Vblank | 2254 interrupts on `GICv2 142`; no `flip_done` timeouts, no DRM warnings |
| Scanout | AFBD source sampled *during* a run alternates `0x6c900000` / `0x6c500000` — real buffers, not the logo address |
| Node | `/dev/dri/card1` (**not** card0 — panfrost takes minor 0 as a render-only device), connector 33 type 7 (LVDS), connected |
| fbdev | `Console: switching to colour frame buffer device 160x45`, `fb0: sun50i-h713-afb` |
| **mpv** | **`mpv --vo=drm` plays 720p to the panel, 0 dropped frames over 25 s of looped playback.** mpv reports `Driver: sun50i-h713-afbd 1.0.0`, `Selected mode: 1280x720 (1280x720@59.97Hz)`, `DRM Atomic support found`, `Using primary plane 34 as draw plane` |

**Operator-confirmed, twice, and this is the evidence registers cannot give:**

- A **Linux login prompt on the projector** — the first time this project has put
  Linux's own output on the panel rather than an image U-Boot published. That is
  fbcon on `/dev/fb0`, i.e. the KMS driver driving scanout end to end.
- During the mpv run, **the colour bars with the diagonal, played through at
  least twice** — that is `testsrc2`, the content of `v04-1280x720-high.h264`,
  so mpv's decoded frames demonstrably reached the panel.

One thing to expect and not mistake for a fault: **after any reboot the panel is
dark until `h713_disp auto 0x34 logo` runs again.** The driver adopts a display
someone else brought up; it cannot bring one up. A blank panel at the U-Boot
prompt means exactly that and nothing more.

---

## What it is

`drivers/gpu/drm/tiny/sun50i-h713-afbd.c` (patch 0037), node `display@5600000`
(patch 0038), `CONFIG_DRM_SUN50I_H713_AFBD=m`.

A `drm_simple_display_pipe`: one CRTC, one primary plane, one fixed-mode LVDS
connector. It owns exactly two things — **which buffer is scanned out, and when
the swap happens.**

## 2026-09-01: fullscreen NV12 handoff confirmed under KMS ownership

Out-of-series patch 0077 booted the KMS driver with DECD disabled, leaving
source 0 untouched for a controlled coexistence test. KMS had demonstrably
taken over first: the operator confirmed the Linux login prompt on the panel.
A first script then pointed source 0 at the byte-verified NV12 frame-60
carveout, programmed the known geometry/stride/gain state, committed it, and
changed the downstream selector from `0x29000000` to `0x39000000` for ten
seconds.

The login prompt was replaced, proving KMS did not suppress source 0 and the
selector did route away from the RGB channel. But the result was a **garbage
frame**, not the unmistakable face in the source buffer. Restoring the nine
registers brought the login prompt back correctly; post-test state was exact
and there were no kernel warnings or IOMMU faults.

An explicit second control committed the KMS RGB channel off before selecting
source 0 and produced the same garbage. That ruled out concurrent RGB fetch,
but comparison against the captured DECD state exposed the real defect in both
tests: only ring slot 0 had been populated. DECD's apparently static submit
repeats Y, C, and VideoInfo across all four slots and sets the dirty latch.

The corrected test reproduced that complete ring while RGB was committed off.
The dirty latch was consumed, **the operator saw the decoded face rendered
correctly**, and disabling source 0 restored the Linux login prompt. Every ring
and control register returned to its saved value with no fault.

The implementation shape is therefore confirmed, with an important hardware
constraint: expose source 0 as an opaque fullscreen NV12 DRM overlay, but treat
it as an exclusive mux in the driver. Enabling it retains the primary RGB
framebuffer in DRM state while stopping the RGB hardware fetch; disabling it
restores RGB. The first version should accept only linear 1280x720 NV12 with no
scaling, crop, rotation, or alpha. The exact test and result are in
[handoff-2026-09-01-decd-kms-shape.md](handoff-2026-09-01-decd-kms-shape.md).

Out-of-series patch 0078 is the first implementation of that shape. It keeps
the proven RGB simple pipe and adds a manually initialized atomic overlay plane
for linear fullscreen 1280x720 NV12 only. The driver owns the exclusive mux
transition, repeats each framebuffer across the complete four-slot source ring,
and allocates the VideoInfo page from the display device's DMA address space.
It builds cleanly and is staged for its first visible test; it has not yet been
booted. This version intentionally retains GEM DMA's contiguous-import rule.
Runtime IOMMU attachment and fragmented Cedrus PRIME imports are the next phase,
not hidden inside the initial plane proof.

## What it deliberately does not do

The panel is brought up *before Linux*. U-Boot's `h713_disp` loads the MIPS
co-processor, which programs the VBlender timing and the LVDS PHY. Nothing in
Linux can do that bring-up yet, so this driver **adopts a running display** and
never touches:

- timing or the LVDS PHY — the MIPS owns them;
- `rst_bus_disp` — asserting it would kill a panel this driver cannot bring
  back. The DT node has **no `resets` property**, so the means is withheld
  rather than the rule merely being remembered in C;
- the AFBD clock *rate* — `clk_summary` shows 100 MHz under the display U-Boot
  established, and moving a divider beneath a live panel is how you lose it.

So this does **not** close the "display needs U-Boot every boot" gap. That is
still the largest bench-to-product gap and it is still ahead.

## Geometry is read, not assumed

Probe reads the mode back out of the hardware:

| register | meaning |
| --- | --- |
| `0x05600160` | `height << 16 \| width` |
| `0x05600170` | stride in bytes |
| `0x05600178` | current source address |

If it reads zero the driver fails probe with the reason ("run `h713_disp auto
0x34 logo` in U-Boot"), which is exactly what booting without display bring-up
looks like. Only `hdisplay`/`vdisplay` are real; the porches and pixel clock are
synthesised by `drm_cvt_mode()`, because nothing here programs timing.

## The commit sequence

Not new and not guessed. This is what `tools/video/gles-play.c` does, which
sustained **59.71 fps over 2700 frames at a measured 0.00% tearing rate** against
a 16.94% positive control:

```
write SRC (0x178) = buffer physical address
clear STATUS (0x168) pending bits      -- write-1-to-clear
set CTRL (0x140) bit 0
write READY (0x144) = 1                -- latches at the next vsync
```

The one thing dropped is gles-play's 50 ms poll of `STATUS` bit 1. `READY`
latches at vsync, so the flip completes on the vblank interrupt and the
page-flip event is armed against it — no spinning in an atomic path, and clients
get a present timestamp that corresponds to an actual present.

## Vblank

| register | meaning |
| --- | --- |
| `0x056000c0` | vsync IRQ status, byte, bit 0, write-1-to-clear |
| `0x056000c4` | vsync IRQ enable, byte, bit 0 |

Interrupt is `GIC_SPI 110`.

This protocol is inherited RE — it comes from the vendor DECD driver's
`dec_vsync_handler()` / `dec_irq_query()`, and this project has been burned by
inherited claims before ([h713-inherited-claims-were-wrong]). It was believed on
one piece of evidence: an out-of-bounds write in that handler crashed the board
**every ~100 vsyncs, i.e. every ~1.7 s** (patch 0034), which only happens if the
interrupt genuinely fires at 60 Hz.

**The bit assignments are now confirmed too**, which was the main open risk: 1320
page flips completed at exactly the panel rate with zero timeouts, and
`/proc/interrupts` shows the count climbing on `GICv2 142`. A wrong status or
enable bit would have produced flips that never complete.

## What this cost DECD, and why

`dec@5600000` is now `status = "disabled"`, because two drivers cannot own one
register window and one interrupt: KMS needs the AFBD window and SPI 110, and so
does DECD. It is still built (`CONFIG_SUNXI_DECD=m`) and the node is one word
from coming back.

> **Correction, 2026-08-31.** This section used to say DECD "has no job — its
> registers are not in the scanout fetch path." That is **wrong**, and it was
> wrong when written: DECD is the vendor's no-GPU video path, and a Linux DECD
> submit has since put a 1280x720 NV12 frame on the panel in full colour, then
> carried real Cedrus dma-bufs at 30 fps. It restated the retracted 2026-08-09
> "direct YUV scanout does not reproduce" result as a fact about the hardware,
> when what those experiments actually showed was that *our* register recipe was
> wrong. The resource conflict above is the real and
> only reason DECD is disabled here, and it is now a genuine architectural
> choice rather than a free one: today the two paths are mutually exclusive at
> the DT level, and DECD experiments run from a separate DECD-exclusive FIT.
> See
> [reference/linux-decd-scanout-confirmed-2026-08-31.md](reference/linux-decd-scanout-confirmed-2026-08-31.md).

## Memory — and the mistake that mpv exposed

Framebuffers come from **system CMA**. The first design used the scanout
carveout as a `shared-dma-pool` via `memory-region`, and that was wrong in a way
worth keeping written down, because the arithmetic looks fine right up until it
fails.

**A dma-coherent reserved pool allocates in power-of-two page orders.** A
1280x720x4 buffer is 3,686,400 bytes → 900 pages → rounded to 1024 pages, so it
occupies a **4 MiB slot**. A 16 MiB pool therefore yields exactly four buffers,
not the four-and-a-half the division suggests. The fbdev console holds one:

```
$ drm-flip alloc
  buffer 1: handle 1, 3686400 bytes
  buffer 2: handle 2, 3686400 bytes
  buffer 3: handle 3, 3686400 bytes
allocation 4 failed: Cannot allocate memory
3 full-screen buffer(s) available to a client
```

mpv wants more than three and died at `CREATE_DUMB` with `ENOMEM`. Unbinding
fbcon does **not** help — the console switches to a dummy device but the DRM
fbdev client keeps its buffer, and the count stays at 3.

CMA allocates by range instead: no power-of-two rounding, no small ceiling. The
same probe on CMA returns **64** (the probe's own cap), flips still run at 59.71
fps, and the AFBD source register reads `0x76d00000` — inside the CMA region at
`0x76c00000`, which also settles the question of whether AFBD is happy scanning
out of ordinary CMA memory rather than the carveout. It is.

`cma=128M` is in this board's bootargs, so there is room for both this and
cedrus. Note the earlier justification for the carveout — "CMA is only 16 MiB" —
was simply wrong: 16 MiB is the *config default*, overridden on the command line.

`uboot-scanout@6c100000` is therefore back to a plain 8 MiB `no-map`
reservation. Its remaining job is real but narrow: stop Linux using the memory
AFBD is actively scanning out of between boot and the driver taking over.

The driver still honours a `memory-region` if one is present, and logs which
allocator it used (`framebuffers from the system CMA pool`). Point it at a
carveout if scanout ever needs to live in a specific region — and inherit the
ceiling along with it.

---

## Reproducing the test

```
reboot bootloader
h713_disp auto 0x34 logo     # REQUIRED, as always
boot
```
then on the target:
```
insmod /root/sun50i-h713-afbd.ko    # or modprobe, once it is in /lib/modules
dmesg | grep -i afbd                # adopting 1280x720, stride 5120, source 6c100000
gcc -O2 -o drm-flip drm-flip.c      # tools/display/drm-flip.c, no libdrm needed
./drm-flip info
./drm-flip flip 900
```

`drm-flip` is the gate. It picks the card node that actually has CRTCs, so it
does not mistake panfrost's render-only minor 0 for the display, and it reports a
flip that never completes as *"vblank is not firing"* rather than hanging. It
uses raw ioctls and the UAPI headers in `/usr/include/drm` — libdrm's headers are
not on the minimal rootfs, and a display instrument you cannot run when you need
it is not an instrument.

**The U-Boot logo is replaced by a console** the moment the module loads:
`CONFIG_DRM_FBDEV_EMULATION=y` means fbcon takes the new `/dev/fb0`. If the panel
ever shows garbage or repeats instead, suspect stride or format first — the same
4-bytes-per-pixel arithmetic that produced the "4x repeat greyscale" in the
direct-YUV work applies here.

An eyes-free way to prove scanout is actually moving, which is worth knowing
because `0x6c100000` is *both* the logo address and the first pool allocation —
so reading it while idle proves nothing. Sample the source register during a
run:

```
(./drm-flip flip 900 &) ; busybox devmem 0x05600178   # 0x6c900000 / 0x6c500000
```

### mpv

```
mpv --vo=drm --drm-device=/dev/dri/card1 --no-audio v04-1280x720-high.h264
```

`--drm-device` is worth passing explicitly: mpv defaults to `card0`, which is
panfrost's render-only node here.

This decodes in **software** — Debian's ffmpeg has no V4L2-stateless hwaccel, so
mpv cannot drive cedrus, and `gles-play` remains the hardware-decoded path. It
still keeps up: 0 dropped frames over 25 s of looped 720p25. What this test
proves is the display half, not the decode half.

### Do not run these at the same time

`gles-play`, `gles-tear`, `gles-scanout` and `h713-present` poke the AFBD
registers through `/dev/mem`. With the KMS driver bound they are a second owner
of the same registers and will fight it. Unbind the driver, or do not run them.

### The risks named before the first boot, and what happened

- **Wrong vblank bits** — the main one. *Did not happen:* 1320 flips, 0
  timeouts. Had they been wrong, flips would never have completed.
- **The carveout growing to 16 MiB** moving the top of usable RAM. *No effect
  observed;* the board boots and runs normally.
- **fbcon on the panel** at module load. *Happened as predicted* — the console
  replaces the logo. The driver is a module, so `rmmod` and a reboot are always
  available.

## What plays on the panel today — measured 2026-08-24

1000 frames of 720p HEVC, decoded on the VE, displayed. Same clip, same board,
same boot.

| path | delivered fps | dropped | bounded by |
| --- | --- | --- | --- |
| `videoconvert ! kmssink` (default) | **3.15** | **50%** | CPU colour conversion |
| `videoconvert n-threads=4 ! kmssink` | **14.15** | 4.4% | the same, four ways |
| `mpv --hwdec=vaapi-copy --vo=gpu --drm-device=/dev/dri/card1` | **32** | none (untimed) | the copy round-trip |
| `gles-play` (GPU samples the decoder's dma-buf, zero copy) | **59.71** | none | vsync |

**Both stock paths work.** That corrects the standing claim that `kmssink`
could not drive this driver: it can, in `BGRx` at the panel size. The original
attempt asked for NV12 — which this plane does not support — and read
`not-negotiated` as "cannot".

> **MEASURE DELIVERED FRAMES, NOT WALL CLOCK.** The first version of this table
> reported 24 fps for the CPU path, from timing a 1000-frame run at 40 s. That
> number was the *stream's own duration*: the sink was syncing to the clock and
> QoS was making `videoconvert` skip late buffers, so half the frames were never
> converted at all. `fpsdisplaysink` reports `rendered: 127, dropped: 125`. A
> pipeline that keeps up with the clock and one that drops half its frames take
> exactly the same wall time.

### `n-threads` is worth 4.5x, and free

Default `videoconvert` is single-threaded. On this board that is 3.15 fps
delivered with half the frames dropped; `n-threads=4` gives 14.15 fps with 4.4%
dropped. Nothing else about the pipeline changes.

### Why it is slow at all: the read, not the arithmetic

The same NV12 → BGRx conversion, single-threaded, measured two ways:

| source of the NV12 | fps |
| --- | --- |
| ordinary memory (`videotestsrc`) | 26 |
| the decoder's V4L2 buffers | **7** |

A 3.7x penalty for reading the decoder's output, which is uncached — the same
~44 MB/s wall that `hwdownload` hits for VA-API. Threads help because they
overlap that latency, not because the conversion is compute-bound.

**Cached buffers are not available today.** `cedrus` does not set
`allow_cache_hints`, so a client cannot request non-coherent (cached) buffers —
and neither GStreamer's `v4l2` allocator nor its `v4l2codecs` allocator ever
asks: `V4L2_MEMORY_FLAG_NON_COHERENT` appears in neither. Enabling the flag
alone would therefore change nothing measurable, which is why it has not been
enabled.

**~~The hardware way out exists and is unwritten.~~ WRONG — corrected
2026-08-25.** This paragraph claimed `ge2d@5240000` was "a 2D engine with
colour-space conversion" and that a driver for it would let `v4l2convert` do
the work in hardware. It is not a 2D engine: `compatible = "trix,ge2d"`, its reg
windows are OSD/LVDS/AFBD, and its vendor sources drive the panel, backlight and
a TI DLP controller. It is the projector's display controller. There is no
Allwinner G2D on this SoC either, and direct NV12 scanout was implemented and
refuted on hardware (patch 0065, out of series). The full investigation is in
[`handoff-2026-08-24-display.md`](handoff-2026-08-24-display.md) under "Hardware
colour conversion".

**The hardware colour conversion on this board is the GPU**, and it already
works: `gles-play` sustains 59.71 fps zero-copy with `samplerExternalOES` doing
YUV→RGB in the texture unit.

**For real-time playback today, do not use the CPU.** mpv at 32 fps and
`gles-play` at 59.71 both already work.

## Still open

- **Nobody has looked at the projector yet.** Every check above is a register,
  an event count or a kernel message. They are consistent and hard to fake, but
  a photo in `local/lcd-photos/` is what this project normally requires, and the
  provenance rules there exist because a misattributed photo cost two sessions.
- **The module is at `/root/sun50i-h713-afbd.ko`, not in `/lib/modules`**, so it
  does not autoload. That is deliberate for now: autoloading would replace the
  boot logo with a console on every boot, which is a product-visible change
  nobody has asked for. The rootfs build is where it should land when it does.
- **An atomic commit fails at mpv's teardown**: `Failed to commit atomic request:
  Error number 22` (EINVAL), after playback has finished. Atomic *is* exposed —
  mpv finds it (`DRM Atomic support found`) and uses it for playback without
  complaint — so the likely cause is `drm_simple_kms_plane_atomic_check()`,
  which rejects any state where the CRTC and its plane are not enabled or
  disabled together. mpv's exit path appears to commit exactly that. Harmless
  for playback, and **observed not to strand the panel**: the console was back after mpv
  exited. Still the first thing to look at if a compositor misbehaves.
- Still does **not** close the "display needs U-Boot every boot" gap.
