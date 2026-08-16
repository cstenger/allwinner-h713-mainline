# KMS for the H713 panel

Started 2026-08-15. Gives the projector a DRM card node (`card1` in practice —
panfrost holds minor 0) so ordinary DRM clients — `mpv --vo=drm`, a compositor,
fbcon — can present on the panel, instead of every program mapping `0x05600000`
through `/dev/mem` and reimplementing the AFBD commit sequence for itself.

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

**Operator-confirmed the same day:** a **Linux login prompt on the projector** —
the first time this project has put Linux's own output on the panel rather than
a U-Boot-published image. That is fbcon on `/dev/fb0`, i.e. the KMS driver
driving scanout end to end.

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

`dec@5600000` is now `status = "disabled"`. This answers the video-decode loose
end "decide what DECD is for": DECD probes and works but has no job — its
registers are not in the scanout fetch path — while holding the two resources a
display driver needs, the AFBD window and SPI 110. Two drivers cannot own one
window and one interrupt. It is still built (`CONFIG_SUNXI_DECD=m`) and the node
is one word from coming back.

## Memory

Framebuffers come from the scanout carveout via `memory-region`, not system CMA.
Not because CMA is short — the bootargs carry `cma=128M`, so it is roomy — but
because the carveout is the memory AFBD is already proven to scan out of, and
keeping display buffers out of the pool cedrus decodes into stops the two paths
competing as either grows.

`uboot-scanout@6c100000` therefore became a `shared-dma-pool` and grew from 8 to
16 MiB. It stays `no-map`, which is correct on arm64: `rmem_dma_setup()` only
demands a mapping under `CONFIG_ARM`, and `dma_init_coherent_memory()` memremaps
the region write-combine, which is what a framebuffer wants. Confirmed at boot:

```
Reserved memory: created DMA memory pool at 0x000000006c100000, size 16 MiB
OF: reserved mem: initialized node uboot-scanout@6c100000, compatible id shared-dma-pool
```

The resize was not theoretical. On hardware the fbdev console takes
`0x6c100000`, and a client's two flip buffers land at `0x6c500000` and
`0x6c900000` — the third would not have fitted in the old 8 MiB.

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

### mpv is not yet testable here

`mpv --vo=drm` is the eventual client, but mpv is not on this image — it is in
the rootfs built on 2026-08-15 (`--profile dev`), which has not been flashed. And
when it is, mpv will decode in **software**: Debian's ffmpeg has no
V4L2-stateless hwaccel, so it cannot drive cedrus. `gles-play` remains the
hardware-decoded path.

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

## Still open

- **Nobody has looked at the projector yet.** Every check above is a register,
  an event count or a kernel message. They are consistent and hard to fake, but
  a photo in `local/lcd-photos/` is what this project normally requires, and the
  provenance rules there exist because a misattributed photo cost two sessions.
- **The module is at `/root/sun50i-h713-afbd.ko`, not in `/lib/modules`**, so it
  does not autoload. That is deliberate for now: autoloading would replace the
  boot logo with a console on every boot, which is a product-visible change
  nobody has asked for. The rootfs build is where it should land when it does.
- **Atomic modesetting is not exposed** (`DRIVER_ATOMIC` is set but the driver
  uses the legacy simple-pipe path); no plane properties, no async flips.
- Still does **not** close the "display needs U-Boot every boot" gap.
