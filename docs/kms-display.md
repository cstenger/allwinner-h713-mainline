# KMS for the H713 panel

Started 2026-08-15. Gives the projector a `/dev/dri/card0` so ordinary DRM
clients — `mpv --vo=drm`, a compositor, fbcon — can present on the panel,
instead of every program mapping `0x05600000` through `/dev/mem` and
reimplementing the AFBD commit sequence for itself.

**Status: builds, not yet run on hardware.** Everything below about registers and
sequences is carried over from work that *was* hardware-verified; everything
about this driver's behaviour is a prediction until someone boots it. The test
procedure is at the bottom, and it is the next thing to do.

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
inherited claims before ([h713-inherited-claims-were-wrong]). It is believed
here for one specific reason: an out-of-bounds write in that handler crashed the
board **every ~100 vsyncs, i.e. every ~1.7 s** (patch 0034), which only happens
if the interrupt genuinely fires at 60 Hz. The cadence is evidence; the bit
assignments are not, and are the first thing to doubt if vblank misbehaves.

## What this cost DECD, and why

`dec@5600000` is now `status = "disabled"`. This answers the video-decode loose
end "decide what DECD is for": DECD probes and works but has no job — its
registers are not in the scanout fetch path — while holding the two resources a
display driver needs, the AFBD window and SPI 110. Two drivers cannot own one
window and one interrupt. It is still built (`CONFIG_SUNXI_DECD=m`) and the node
is one word from coming back.

## Memory

Framebuffers come from the scanout carveout via `memory-region`, not system CMA:
CMA is 16 MiB and cedrus decodes into it, so two 3.5 MiB framebuffers would
starve the decode path this display exists to show.

`uboot-scanout@6c100000` therefore became a `shared-dma-pool` and grew from 8 to
16 MiB — at 1280x720x4, 8 MiB held U-Boot's two slots exactly and nothing else.
It stays `no-map`, which is correct on arm64: `rmem_dma_setup()` only demands a
mapping under `CONFIG_ARM`, and `dma_init_coherent_memory()` memremaps the
region write-combine, which is what a framebuffer wants.

---

## Testing it — the next session's job

Nothing below has been run.

```
reboot bootloader
h713_disp auto 0x34 logo     # REQUIRED, as always
boot
```
then on the target:
```
modprobe sun50i-h713-afbd
dmesg | grep -i afbd         # expect: adopting 1280x720, stride 5120, source 6c100000
ls /dev/dri/                 # expect card0 (plus renderD128 from panfrost)
```

**Expect the U-Boot logo to be replaced by a console** the moment the module
loads: `CONFIG_DRM_FBDEV_EMULATION=y` means fbcon takes the new `/dev/fb0`. That
is the cheapest confirmation scanout is live and under Linux's control. If the
panel instead shows garbage or repeats, suspect stride or format first — the
same 4-bytes-per-pixel arithmetic that produced the "4x repeat greyscale" in the
direct-YUV work applies here.

Then the actual goal:

```
mpv --vo=drm /root/video-test/v04-1280x720-high.h264
```

Note mpv will decode this in **software** — Debian's ffmpeg has no V4L2-stateless
hwaccel, so mpv cannot drive cedrus. 720p on 4x A53 may or may not hold 60 fps;
that is a separate question from whether scanout works, and `gles-play` remains
the hardware-decoded path.

### Do not run these at the same time

`gles-play`, `gles-tear`, `gles-scanout` and `h713-present` poke the AFBD
registers through `/dev/mem`. With the KMS driver bound they are a second owner
of the same registers and will fight it. Unbind the driver, or do not run them.

### Risks worth naming before the first boot

- **Wrong vblank bits** would show up as a page flip that never completes:
  clients hang waiting for an event. `drm_crtc_handle_vblank` never firing is
  the signature. Falling back to `disable_vblank` + immediate events is a
  one-line diagnostic.
- **The carveout growing to 16 MiB** moves the top of usable RAM. If anything
  was quietly relying on memory just above `0x6c900000`, this is where it
  breaks.
- **fbcon on the panel** is new behaviour at module load. Because the driver is
  a module, `rmmod` and a reboot are always available.
