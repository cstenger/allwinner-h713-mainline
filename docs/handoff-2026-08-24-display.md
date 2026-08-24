# Handoff — display, 2026-08-24

Companion to [`handoff-2026-08-24.md`](handoff-2026-08-24.md) (video decode).
Branch `h713-dvfs-1416-corruption`, pushed through `fd13987`. Nothing is left
only on the board except one saved U-Boot environment variable, noted below.

## What landed

1. **The Linux boot appears on the panel.** Two halves:
   - U-Boot runs `h713_disp auto 0x34 logo` from `CONFIG_PREBOOT`
     (`external/u-boot/configs/hy200_qz713df_a1_defconfig`), so the panel is up
     before Linux starts. The driver adopts a running framebuffer and refuses
     to probe without one, which is why this was needed.
   - Patch **0064** adds `console=tty0` to both boards' bootargs. fbcon was
     always bound; the command line just never named it. `/proc/consoles` now
     lists `tty0` and `ttyS0`. The kernel replays its log to a late console, so
     the panel should show the boot from the beginning.
2. **Patch 0063** — the driver reported `min_width == max_width`, which is legal
   and is what other fixed-panel tiny drivers do, but GStreamer's kmssink builds
   `GstIntRange(min,max)` from it and aborts every caps query. It opens the
   maximum instead of lowering the minimum: `min = 0` was tried on hardware
   first and moved the failure from negotiation to `-EIO` at commit.
3. **`kmssink` was never broken** — the standing claim was wrong. The original
   attempt asked for NV12, which this plane does not support.

## Verified, and the one thing that is not

Verified: preboot runs unattended after `reset`; `card1` adopts 1280x720;
`/proc/consoles` lists tty0; criticals gone; un-sized pipelines negotiate;
720p playback unchanged.

**NOT verified: that boot text is actually visible on the panel.** Nobody has
looked. That is the first thing to check.

## Numbers, and the mistake that produced the first set

1000 frames of 720p HEVC, decoded on the VE:

| path | delivered fps | dropped |
| --- | --- | --- |
| `videoconvert ! kmssink` (default) | 3.15 | 50% |
| `videoconvert n-threads=4 ! kmssink` | 14.15 | 4.4% |
| `mpv --hwdec=vaapi-copy --vo=gpu` | 32 | none (untimed) |
| `gles-play` (GPU, zero copy) | 59.71 | none |

An earlier version of this table said 24 fps for the CPU path. That was
wall-clock over 1000 frames — the stream's own duration — while QoS made
`videoconvert` skip half the frames. **Measure delivered frames
(`fpsdisplaysink`), never wall clock.** The same mistake hid the fact that
`n-threads` is worth 4.5x.

The cost is the read, not the arithmetic: 26 fps converting from ordinary
memory, 7 fps from the decoder's uncached buffers.

## Open work, in value order

1. **A GE2D driver.** `ge2d@5240000` is in the vendor DT — a 2D engine with
   colour-space conversion — and mainline 6.18 has no driver
   (`drivers/media/platform/sunxi/` has CSI, deinterlace, DE2 rotate, no GE2D).
   With one, `v4l2convert` does the conversion in hardware and the CPU path
   stops mattering. This is the largest remaining display win and it is a new
   driver, not tuning.
2. **Kernel-side panel init.** The driver still only *adopts* what U-Boot set
   up. A fresh boot without the preboot command has no display. Moving the init
   into the kernel is a large port (MIPS coprocessor, PLL, DE, timings) — the
   U-Boot implementation in `arch/arm/mach-sunxi/h713_mips.c` is the reference.
3. **U-Boot is not reflashed.** The board gets the preboot behaviour from its
   *saved environment*; the defconfig change is built but unflashed, so a
   bootloader reflash or an env wipe reverts it. `build/out/u-boot-sunxi-with-spl-ddr3.bin`
   carries it. Flashing the bootloader is the riskiest write available — decide
   deliberately.
4. **Cached decoder buffers: a dead end today.** `cedrus` does not set
   `allow_cache_hints`, and neither GStreamer allocator passes
   `V4L2_MEMORY_FLAG_NON_COHERENT`, so enabling it changes nothing measurable.
5. **Zero-copy for stock clients.** mpv needs `--hwdec=vaapi-copy` because
   `card1` has no render node; `gstreamer1.0-gl` is not installed and the board
   has no package mirror, so a stock GPU pipeline could not be tested.

## Board state

Kernel FIT on the FAT carries 0063 + 0064 (`console=tty0`). Cedrus and VA
driver are the shipping ones, stamped — run `tools/video/check-video-stack.sh`
to confirm. Panel is up. `/root/video-test/` has every vector and gate,
including `disp-720p.h265` (1000 frames of 720p) used for the numbers above.

**To get the panel back after a power cycle:** it is automatic now. If the env
is ever lost, `h713_disp auto 0x34 logo` at the U-Boot prompt, then `boot`.
`tools/serial/reboot-to-uboot.py /dev/ttyUSB0 60` catches the prompt;
`tools/serial/console.py --port /dev/ttyUSB0 --wait 60 "boot"` continues.
