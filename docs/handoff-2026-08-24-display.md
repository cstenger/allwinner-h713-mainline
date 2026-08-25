# Handoff — display, 2026-08-24

Companion to [`handoff-2026-08-24.md`](handoff-2026-08-24.md) (video decode).
Branch `h713-dvfs-1416-corruption`, pushed through `fd13987`. Nothing is left
only on the board except one saved U-Boot environment variable, noted below.

## What landed

1. **The Linux boot appears on the panel.** Four halves, by the end:
   - U-Boot runs `h713_disp auto 0x34 logo` from `CONFIG_PREBOOT`
     (`external/u-boot/configs/hy200_qz713df_a1_defconfig`), so the panel is up
     before Linux starts. The driver adopts a running framebuffer and refuses
     to probe without one, which is why this was needed.
   - Patch **0064** adds `console=tty0` to both boards' bootargs. fbcon was
     always bound; the command line just never named it. `/proc/consoles` now
     lists `tty0` and `ttyS0`.
   - **`CONFIG_DRM_SUN50I_H713_AFBD=y`**, not `=m`. As a module the driver did
     not load until udev got to it, so fbcon took over 6.5 s in and the whole
     early boot was already gone.
   - **`TTYVTDisallocate=no`** for `getty@tty1`, which was erasing what fbcon
     had just painted.
   - **aic8800 patch 0007**, because once the boot log survived, the WiFi
     driver's per-association chatter scrolled it away and buried the login
     prompt.

   An earlier version of this section claimed the kernel "replays its log to a
   late console, so the panel should show the boot from the beginning." That is
   wrong in both halves: `tty0` is registered in `con_init` like any other boot
   console and there is no replay at takeover — `do_take_over_console` just
   redraws the VT's own screen buffer. The console was never late. **The driver
   was**, and that is what the last two items fix.
2. **Patch 0063** — the driver reported `min_width == max_width`, which is legal
   and is what other fixed-panel tiny drivers do, but GStreamer's kmssink builds
   `GstIntRange(min,max)` from it and aborts every caps query. It opens the
   maximum instead of lowering the minimum: `min = 0` was tried on hardware
   first and moved the failure from negotiation to `-EIO` at commit.
3. **`kmssink` was never broken** — the standing claim was wrong. The original
   attempt asked for NV12, which this plane does not support. It does still need
   `driver-name=sun50i-h713-afbd`; see the correction below.

## Verified

Preboot runs unattended after `reset`; the AFBD card adopts 1280x720;
`/proc/consoles` lists tty0; criticals gone; un-sized pipelines negotiate;
720p playback unchanged.

**Boot text does reach the panel** — confirmed by eye, and the VT screen buffer
(`fold -w 160 /dev/vcs1`) reads back the same timestamped kernel lines that are
on the glass. Note that `/dev/vcs1` is the instrument for all of this: it dumps
tty1's characters, so "what is on the projector" is answerable over ssh with no
camera and nobody in the room.

## What the panel shows during a boot

Measured on the running board, 2026-08-24, from `dmesg`, `systemctl show`,
`/proc/iomem` and `/dev/vcs1`. **The first table is the state this session
started in; it was diagnosed, fixed, and the second table is where it landed.**

### Before (`CONFIG_DRM_SUN50I_H713_AFBD=m`)

| when | what is on the glass |
| --- | --- |
| U-Boot preboot | the vendor logo, from `h713_disp auto 0x34 logo` |
| 0 → 6.49 s | **still the logo, untouched.** `tty0` is a console from the start, but there is no display behind it yet, so kernel text only piles up in the VT's memory |
| 6.49 s | fbcon takes over (`Console: switching to colour frame buffer device 160x45`) and the logo is replaced by text |
| 7.83 s | `getty@tty1` starts and **wipes the screen**, then prints the Debian issue and `login:` |
| after | the login prompt, plus every kernel message that arrives — the timestamped lines that were on the panel when this session opened |

Three things follow, and they are the useful part:

1. **Nothing about the first 6.5 seconds is on the panel.** The console was
   never late — `tty0` is registered in `con_init` like always. The *driver* is
   late: `CONFIG_DRM_SUN50I_H713_AFBD=m`, so systemd/udev modprobes it at
   6.41 s and the takeover follows at 6.49 s. **410 dmesg lines have already
   printed by then.**
2. **What the takeover paints is the tail, not the log.** `do_take_over_console`
   redraws the VC's screen buffer; there is no printk replay involved at any
   point. Before fbcon the VC is dummycon-sized (80x25), so what survives to be
   painted is the last ~25 rows — around 15-20 messages, since kernel lines wrap
   at 80 columns. *(This step is mechanism, not observation; it was never pinned
   down directly, because the fix below made the question moot.)*
3. **The window is 1.34 seconds.** `getty@.service` ships `TTYReset=yes` and
   `TTYVTDisallocate=yes`, so at 7.83 s the boot text is wiped and the login
   banner replaces it. A person watching sees the logo, a flash of late boot
   log, then a login prompt.

The logo really is intact for those 6.5 s rather than corrupted: `/proc/iomem`
shows `6c100000-6c8fffff : reserved`, the `no-map` `uboot-scanout@6c100000`
carveout from patch 0024, so the kernel never writes there.

### After (`=y`, plus `TTYVTDisallocate=no`) — both landed and HW-verified

| when | what is on the glass |
| --- | --- |
| U-Boot preboot | the vendor logo |
| 0 → 1.25 s | the logo |
| **1.25 s** | fbcon takes over — **before `Freeing unused kernel memory` at 2.03 s**, so inside kernel init rather than five seconds into userspace |
| 7.8 s | `getty@tty1` starts and **appends** the login banner instead of wiping |
| after | boot log, banner, and live kernel messages |

**Lines printed before the takeover: 410 → 163.** The change is one line of
defconfig; `sun50i-h713-afbd` no longer waits on udev.

**What was and was not observed directly, because the difference matters.**
Measured from the boot itself: the 1.25 s takeover, its position before
`Freeing unused kernel memory`, and the 163-line count. Measured separately, by
the marker test below: that `getty@tty1` no longer wipes. *Not* caught in one
shot: the composite — a `/dev/vcs1` dump taken minutes after that boot showed
only WiFi spam, because the boot log had already scrolled away (see below).

**The composite was closed by eye, not by instrument.** The operator watched a
boot and saw the systemd `[ OK ]` lines scroll past on the panel. That is the
one part `/dev/vcs1` could not answer after the fact, because by the time
anything could be dumped the evidence had already scrolled.

The getty half was proven **without a reboot**, which is the reusable trick
here: write a marker to `/dev/tty1`, `systemctl restart getty@tty1`, then read
`/dev/vcs1` back. With the drop-in the marker survives and the banner lands
underneath it — so `TTYVTDisallocate=yes` is the wipe, and `TTYReset=yes`, the
other suspect, is innocent. The drop-in is now in
[`tools/rootfs/customize.sh`](../tools/rootfs/customize.sh) so a rootfs rebuild
keeps it.

### And then the WiFi driver scrolled it away — aic8800 patch 0007

First result of the above: the boot log reached the panel and was gone inside a
minute. The AIC8800 driver printed a six-line burst on **every** association,
and a client re-associating every few seconds is enough to fill 45 rows:

```
rwnx_cfg80211_del_station_compat: 68:ef:dc:2f:c3:95
wlan0: Del sta 1 (68:ef:dc:2f:c3:95)
deinit:macaddr:68,ef,dc,2f,c3,95
reord_mac:8,5b,d6,d9,c2,13
wlan0: Add sta 2 (...) flags=[SHORT_PREAMBLE][WME][AUTHENTICATED][ASSOCIATED]
done=1 retry_required=0 sw_retry_required=0 acknowledged=1
```

**The driver already had the knob and these sites ignored it.** `aicwf_dbg_level`
is a module parameter that the rootfs pins to `0x1` (LOGERROR) in
`/etc/modprobe.d/aic8800.conf` — commit `facd378` did that back in July — but
these ten call sites are bare `printk()` and `netdev_info()`, so they never
consulted it. Patch **`aic8800-0007`** routes them through `AICWFDBG(LOGINFO)`
like the rest of the driver. Raise `aicwf_dbg_level` to `0x3` and every line is
back. Logging only; no control flow touched.

Verified in the compiled `.ko` rather than the source, since a patch that
applies is not a patch that took effect:

```
$ strings build/out/modules/aic8800_fdrv.ko | grep "Add sta"
AICWFDBG(LOGINFO)	%s: Add sta %d (%pM) flags=%s%s%s%s%s%s%s
```

On hardware: **zero chatter lines in the whole boot**, one station associated,
and the panel ends on `h713-arm64 login:` with `[ OK ]` lines above it —
operator-confirmed on the glass. The last kernel message of any kind is at
11.1 s, so nothing pushes the prompt afterwards.

**This cost a wrong diagnosis, and the layout has since been fixed.** While
tracking the chatter down, `modules/aic8800/` was read as the driver source. It
was the superseded 2024_0109 copy that nothing had built from since 2026-08-17 —
its own README said so, and a full driver tree at an obvious path won anyway.
The trees had diverged: the stale copy lacks the
`rwnx_dbgfs_unregister_rc_stat()` call the shipping driver makes on station
delete, which produced a confident diagnosis of a bug that does not exist in the
running driver.

Fixed structurally rather than with a warning: the stale copy is deleted,
upstream is now the **`external/aic8800` submodule** (same repo, same commit —
the old tarball URL was codeload's endpoint for exactly it), and `build.sh`
sources from it and asserts its HEAD against `AIC8800_COMMIT`. The rebuilt
`aic8800_fdrv.ko` is byte-identical to the tarball-built one, so the switch
changed nothing but where the source lives. There is one readable tree now;
`build/aic8800-<commit>-<digest>/` remains the patched build artifact.

### What still limits it

The remaining 163 lines are a harder floor: the takeover cannot precede the
driver's own probe, and before fbcon the VC is dummycon-sized (80x25), so only
the last ~25 rows get painted at the switch. Earlier lines would need
`earlycon`-style scanout, which nothing here provides.

One smaller leftover, not hiding the prompt: **`get_txpwr_max:txpwr_max:18` /
`change_if:`**, 8 lines between 6.4 s and 8.6 s. Also bare `printk()`, but a
one-time init burst rather than a repeating one, so it lands in the boot log
where it belongs.

## The debugfs errors — fixed, after a wrong diagnosis worth recording

These survived patch 0007 and kept pushing the prompt up the panel, two lines
per re-association:

```
debugfs: '08:5b:d6:d9:c2:13' already exists in 'rc'
aicwf_sdio mmc1:6721:1: Error while (un)registering debug entry for sta 7
```

**The cause is a `#ifdef` on a macro that does not exist.** The register and
unregister calls are guarded differently:

```c
#ifdef CONFIG_DEBUG_FS           /* defined — the kernel has debugfs */
        rwnx_dbgfs_register_rc_stat(rwnx_hw, sta);

#ifdef CONFIG_DEBUG_FS_AIC       /* defined NOWHERE */
            rwnx_dbgfs_unregister_rc_stat(rwnx_hw, cur);
```

`CONFIG_DEBUG_FS_AIC` appears in no Makefile, no header and no kernel config.
Both AP-mode station-delete paths use it, so in AP mode the register compiles in
and the unregister compiles out. The MAC-named directory is created on first
association and never removed; every later association with that MAC collides.
The TDLS unregister a thousand lines away uses plain `CONFIG_DEBUG_FS`, which is
what marks this as a typo rather than a decision. Patch **0009** is two
characters of real change.

**The wrong diagnosis, because the shape of it will recur.** This was first
diagnosed as a workqueue race: register and unregister *are* the same function,
`rwnx_rc_stat_work()` *does* infer intent from whether `dir_sta[sta_idx]` is
NULL when it runs, and that really is fragile. A patch was written, built,
installed and booted on that theory — and the errors came back completely
unchanged, 6 for 6. The mechanism was read carefully and the one question never
asked was whether the code was compiled in at all. **A plausible mechanism is
not evidence that it is the mechanism in play.** What settled it in a minute,
after the theory had cost an hour, was looking at the filesystem instead of the
source: one directory under `rc/`, timestamped at boot, unchanged across ten
re-associations. Nothing was removing it, so nothing could be racing.

Patch **0008** is what came out of the wrong theory and is kept, with its claims
corrected: the one-entry-per-run queue drop is real (`schedule_work()` is a
no-op while a work is pending, so entries were silently dropped), and it also
fixes an out-of-bounds write — `dir_sta[]` and `rc_config[]` were sized
`NX_REMOTE_STA_MAX` (32) while the index is validated against
`NX_REMOTE_STA_MAX + NX_VIRT_DEV_MAX` (36) and the `bc_mc` pseudo-stations sit
above 32. 0009 turns the unregister path on and doubles the traffic through that
queue, so both had to be fixed alongside it rather than left latent.

**Verified on hardware**, same test before and after — ten forced
re-associations driven from the serial console so the WiFi link was not the
lifeline:

| | before | after |
| --- | --- | --- |
| `debugfs`/`debug entry` error lines | 12 | **0** |
| `WARN`s | 0 | 0 |
| `rc/<mac>` directory ctime across a cycle | unchanged since boot | **advances** — removed and recreated |

The ctime check is the one that proves the fix rather than merely the silence.

### The card renumbered: `card1` → `card0`

Building the driver in makes it probe before panfrost's module loads, so it now
takes DRM minor 0 and **panfrost is `card1`** — the exact reverse of every
`--drm-device=/dev/dri/card1` in [`kms-display.md`](kms-display.md) and
[`vaapi-scope.md`](vaapi-scope.md). Those older documents record runs on the
module build and have been left as written; what is true *now* is:

```
/sys/class/drm/card0/device/driver -> sun50i-h713-afbd    # the panel
/sys/class/drm/card1/device/driver -> panfrost            # the GPU
```

The tools survived it — `tools/display/drm-flip.c` probes `card0..N` and the
GLES tools open by driver, so nothing hardcoded the old number. Do not hardcode
the new one either; the numbering is an artifact of probe order.

One cosmetic leftover: udev still tried to modprobe the now-built-in driver and
logged `Error: Driver 'sun50i-h713-afbd' is already registered, aborting...` at
6.68 s. That was the previous build's stale `.ko` still sitting in
`/lib/modules/6.18.38/`; it has been deleted and `depmod -a` rerun. Harmless,
but it is the kind of line that costs someone an hour later.

## A correction: plain `kmssink` never auto-opened this driver

Found while regression-testing the renumber, and **it is not a regression** —
`gst-launch-1.0 ... ! kmssink` fails with `Could not open DRM module (NULL)`.
GStreamer's `kms_open()` walks a hardcoded list of driver names (`i915`,
`rockchip`, `sun4i-drm`, …) and calls `drmOpen()` on each. `sun50i-h713-afbd`
is not in that list, and neither is `panfrost`. `drmOpenByName` matches on the
driver *name* and scans every minor, so minor numbers are irrelevant — and the
pre-change boot log in this session shows the same two drivers under the same
two names. It failed identically before. **The working invocation is:**

```
kmssink driver-name=sun50i-h713-afbd
```

So the entry above claiming "`kmssink` was never broken" is right about the
NV12 diagnosis and wrong to imply the default pipeline works. The numbers in the
next table were taken with the device named explicitly; whoever recorded them as
"(default)" left the property out.

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

**Re-measured after the built-in change**, to check the renumber and the earlier
takeover cost nothing: the `n-threads=4` path gives **1000 rendered, 0 dropped,
14.93 fps** (`sync=false`, so QoS never drops — not identical conditions to the
4.4% row above, but the throughput is unregressed).

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
5. **Zero-copy for stock clients.** mpv needs `--hwdec=vaapi-copy` because the
   AFBD card has no render node; `gstreamer1.0-gl` is not installed and the
   board has no package mirror, so a stock GPU pipeline could not be tested.

## Board state

Kernel FIT on the FAT carries 0063 + 0064 (`console=tty0`) **and
`CONFIG_DRM_SUN50I_H713_AFBD=y`** — installed with
`tools/install-kernel-fit.sh` and booted. The outgoing module-build FIT is
backed up on the board at `/root/fits/replaced-20260824-161616.fit`; installing
it is the way back. Cedrus and VA driver are the shipping ones, stamped — run
`tools/video/check-video-stack.sh` to confirm. Panel is up, as `card0`.
`/root/video-test/` has every vector and gate, including `disp-720p.h265`
(1000 frames of 720p) used for the numbers above.

The `getty@tty1` drop-in is live at
`/etc/systemd/system/getty@tty1.service.d/10-keep-boot-log.conf` on the board
*and* in `tools/rootfs/customize.sh`, so it survives a rootfs rebuild.

**To get the panel back after a power cycle:** it is automatic now. If the env
is ever lost, `h713_disp auto 0x34 logo` at the U-Boot prompt, then `boot`.
`tools/serial/reboot-to-uboot.py /dev/ttyUSB0 60` catches the prompt;
`tools/serial/console.py --port /dev/ttyUSB0 --wait 60 "boot"` continues.
