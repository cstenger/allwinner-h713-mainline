# Second-opinion brief: getting a video plane on an Allwinner H713 projector

Self-contained. Assumes no access to our repo. Written to be handed to someone
who knows Allwinner display hardware and might spot something we have missed.

---

## 1. The goal

Play video without the CPU or GPU doing colour-space conversion.

The decoder (`cedrus`, mainline V4L2 stateless) outputs **NV12**. Our display
driver scans out **XRGB8888 only**. So today something must convert.

| path | result |
| --- | --- |
| CPU `videoconvert` | 3.15 fps default, 14.93 fps with `n-threads=4` |
| GPU (GLES, `samplerExternalOES`) | **59.71 fps, zero copy — works today** |

The GPU path already saturates the panel (vsync ceiling ~58.9 fps), so this is
**not** about throughput. It is about freeing the GPU and letting stock clients
(`mpv`, GStreamer `kmssink`) work without a GLES pipeline.

The vendor's own stack does neither: it decodes into a buffer and hands the
display the physical addresses, letting the **display hardware** do YUV→RGB at
scanout. We want that path. It requires a second display plane — a video plane
alongside the RGB one currently showing the console.

**The question we cannot answer: why can we not bring up the second plane?**

---

## 2. The hardware

**SoC:** Allwinner H713 / sun50iw12p1, Cortex-A53, Mali-G31. Projector product
(HY300-class). Android 11 stock; we run mainline Linux 6.18.

**The display is not a normal Allwinner DE.** There is no `DE2`/`DE33` mixer
driver path and no `sun4i-drm`. Instead:

- A **MIPS co-processor** runs vendor firmware `display.bin` (1.2 MB) and owns
  the display pipeline: VBlender timing, LVDS PHY.
- U-Boot loads that firmware, replays a register table (`LogoRegData.bin`),
  releases the MIPS, and finalises LVDS.
- Linux **adopts** the already-running display. Our KMS driver never touches
  timing, PHY or the display reset — it only changes which buffer is scanned
  out and when.

Note the DT calls the display block `ge2d`, `compatible = "trix,ge2d"`. This is
**not** Allwinner's G2D 2D engine — it is the projector's display controller
(OSD planes, LVDS FIFO, backlight, TI DLPC3435). There is no G2D on this SoC:
the stock kernel binary contains no `g2d` string at all (verified against a
calibration showing clock names *are* readable in it), and the vendor DTB has
zero `g2d|mixer|rotate|blit` nodes.

### Register map (all verified by reading a live board)

| block | plane 0 | plane 1 (live) |
| --- | --- | --- |
| AFBD channel | `0x05600100` | `0x05600140` |
| OSD | `0x05248000` | `0x0524c000` |
| "window" regs | `0x05280040` | `0x05280080` |
| unknown pair | `0x05288000` | `0x0529c000` |
| VBlender-ish | `0x0520002c` | `0x05200034` |
| LVDS pair | `0x051c0060` | `0x051c006c` |
| LVDS pair 2 | `0x051c0180` | `0x051c019c` |

Fixed blocks: AFBD global `0x05600000`, LVDS base `0x051c0000`,
GE2D core `0x05240000`, **mixer `0x0525c000`**.

AFBD channel stride is `0x40`. Within a channel: `+0x00` ctrl, `+0x04` READY
latch, `+0x08`, `+0x0c`, `+0x10` size-1, `+0x20` size, `+0x24`, `+0x28`,
`+0x2c`, `+0x30` stride, `+0x38` source address.

### Live state of the working plane (plane 1)

```
0x05600140 = 0x03001901   ctrl
0x05600144 = 0x00000000   READY latch -- consumed every vsync
0x05600178 = 0x76D00000   source (framebuffer)
0x0524c01c = 0x79860601   "plane open" word
0x0525c004 = 0x00001402   mixer, low bits 0b10
0x0525c01c = 0x0500003C   width 1280, x-offset 60
0x0525c020 = 0x02D00016   height 720, y-offset 22
0x0525c030 = 0x02D00016   identical pair
0x0525c034 = 0x0500003C   identical pair
```

Plane 0 at rest: AFBD ctrl `0x00010000` (idle), OSD block all zeros,
`0x0524801c = 0`.

---

## 3. The single most diagnostic fact

```
0x05600144   plane 1 READY latch   reads 0   -- hardware consumes it every vsync
0x05600104   plane 0 READY latch   reads 1   -- written, NEVER consumed
```

Writing 1 to a channel's READY latch is how a commit is armed (our own KMS
driver does exactly this on plane 1 every page flip, and it clears). On plane 0
the write sticks and is never taken, under **every** configuration we have
tried. Writing 0 to it does not clear it either; only a reboot does.

Our reading: **channel 0 is not being serviced by the pipeline at all.** Not
misconfigured — unserviced.

---

## 4. What the vendor driver does (recovered by RE)

We extracted the stock display driver `ge2d_dev.ko` from the Android vendor
partition — **ARM 32-bit, unstripped, 926 symbols, relocations intact**.

Findings:

- MMIO goes through an external helper,
  `io_accessor_write_reg(space=2, addr, value, mask)`, from a `trix,io-accessor`
  driver whose DT node maps exactly the display windows.
- `init_osd_plane()` (the plane configuration) is reachable at runtime: it is
  called by `tgd_init_planesetting()`, an exported symbol with no in-module
  callers (so, an ioctl entry), and by `ge2d_resume_operation()`, which re-runs
  it against already-live hardware with **no display reset asserted**.
- `tgd_is_plane_open()` reads OSD base `+0x1c` bit 0. That word is **written**
  by bring-up, not set by hardware — it is not a status bit.
- `osd_ready_for_update(plane)` indexes a rodata table
  `OSD_AFBD_REG_OFFSET = {0x05600100, 0x05600140}` and writes 1 to
  `base + 4` — i.e. the READY latch above.
- `tgd_put_plane_info()` (11 KB, the largest function) does 42 writes / 35 reads
  and calls `osd_ready_for_update` + `osd_wait_update_finish`.

### The bring-up register table

U-Boot replays `LogoRegData.bin`, which is indexed by project ID into a
consistent triple: prologue variant (3 exist), timing variant (11), **DE/mixer
variant (8)**. Records are `{addr, value, mask, type}` u32 with 4-byte resync.

Order: prologue → timing → LVDS FIFO reset → mixer write → DE table →
clocks/INCAP/LVDS → MIPS release → LVDS finalise.

**Critical: parsing every block of that file, across all 8 DE variants, all 3
prologues and all 11 timing variants, there is not one record touching
`0x056001xx` (channel 0) or `0x05248xxx` (OSD plane 0).** Every shipped
configuration programs exactly one plane.

DE variant 1 (our 1280x720 panel) writes, in order:
`0x05600000=0x80000020` (AFBD global, bit 31 set), then 13 channel-1 records,
then `0x05240000`, `0x0524001c`, then 14 mixer records
(`0x0525c000`–`0x0525c034`), then 14 OSD-1 records, then `0x05280080/84/88/8c`,
then **`0x05600144 = 1` with mask `0x1`** (the ch1 latch), then LVDS
(`0x058c0000`, `0x051c0014/24/28`, `0x05140054`, `0x051c006c/70`).

---

## 5. What we tried, and what happened

All negative. Each was verified by register readback, and by an operator
watching the physical panel where visual output was possible.

| # | attempt | result |
| --- | --- | --- |
| 1 | Set bit 31 on ch1 ctrl (`0x83001901`), the one value differing from live | Sticky, not a trigger. Nothing latched. A page flip carrying it changed nothing. |
| 2 | Apply `init_osd_plane`'s 15 literal writes to plane 0 from Linux | All landed. Open word never set (we had not yet realised bring-up writes it). |
| 3 | Full DE-table mirror ch1→ch0 (`-0x40`) and OSD1→OSD0 (`-0x4000`), **including** the open word `0x79860601`, then the latch | Open word reads back correct. **Latch never consumed.** |
| 4 | Sweep AFBD global low bits: `0x80000030`, `0x800000f0` (theory: bit 5 gates ch1, bit 4 ch0) | No effect. |
| 5 | Mixer layer-enable: live `0x0525c004 = 0x1402` vs table `0x1003`; set bit 0 → `0x1403`, with plane 0 fully configured and ch0 source pointed at a real framebuffer | Write takes. Latch still unconsumed. **Operator: no flash, no change, two 15-second holds.** |
| 6 | `h713_disp teardown`, pre-set all ch0/OSD0 registers while pipeline is down, then `h713_disp init` | **The prologue zeroes them.** Nothing survives. |
| 7 | **Flashed a modified U-Boot** injecting the 26 mirror writes + latch *inside* the bring-up sequence, immediately after the DE table, before clocks/INCAP/LVDS | Config **survives** into live scanout — first time. `ch0 ctrl=0x03001901`, `open=0x79860601`. **Latch still `1`, never consumed.** Operator: panel shows console only, no logo, despite ch0 source = logo buffer. |

Attempt 7 is the important one: it controls for *placement*, which was the last
plausible confound. Channel 0 entered live scanout fully and correctly
configured, and the hardware still ignores it.

---

## 6. What we believe, and how confident

**High confidence (direct measurement, reproducible):**
- Channel 0's READY latch is never consumed; channel 1's is consumed each vsync.
- No shipped vendor configuration opens a second plane.
- The plane set is not changed by any register we have written, at any time.

**Moderate confidence (inference):**
- The plane count is fixed by the MIPS firmware's VBlender programming, before
  any of these registers matter.
- This product only ever uses one plane; the plane-0/plane-1 duality in
  `ge2d_dev.ko` is generic vendor code for a family of products.

**We have been wrong repeatedly in this investigation**, so treat the inferences
with suspicion. Specific corrections we had to make: "GE2D is a 2D engine"
(false); "the open word is a hardware status bit" (false, it is written);
"plane-open cannot be applied to a running pipeline" (false, it is a callable
function); "bit 31 is a commit enable" (false).

---

## 7. Avenues we have NOT chased

This is the section we most want reviewed.

1. **`display.bin` (1.2 MB MIPS firmware) has never been disassembled.** If the
   VBlender/plane topology is programmed there, this is where the answer is.
   MIPS32, loads at `0x4b100000`, VMA `0xbfc00000` for the boot stub. We have
   the binary and a memory map from `display_cfg.xml`.

2. **CPU_COMM — the ARM↔MIPS RPC interface — is live and we never asked it to
   open a plane.** There is a call table with ~1224 entries, working
   magic/handshake (`deadbeef`), and our U-Boot already has a `commcall` command
   that sends arbitrary calls. If the firmware owns plane topology, *asking it*
   is the natural route and we went straight to register poking instead.

3. **`display_cfg.xml`, `panel_config.ini`, and the `.TSE` data files** are read
   by the firmware. We read the memory-layout header of the XML and never
   examined the panel/plane sections, the `ProjectID_*.TSE` files (13 of them,
   matching the 13 LogoRegData descriptors), or `database.TSE`.

4. **The `ge2d_dev.ko` ioctl surface was never exercised**, only mined for
   register sequences. `tgd_init_planesetting` and `tgd_put_plane_info` are
   entry points. We could load the vendor module under Android and call them.

5. **We never checked whether stock Android actually has two planes.** We can
   boot the vendor stack (`run switch_vendor`) and read `0x0524801c` there. If
   stock also shows one plane, the whole thing is settled; if it shows two, our
   model is wrong and something in the Android boot opens it.

6. **Three LVDS read-modify-write operations in `init_osd_plane` were skipped**
   (runtime-computed values against `0x051c001c`/`0x051c0010`). Probably
   irrelevant, but untested.

7. **Mixer registers beyond the table's range**: `0x0525c038 = 0x00000040` and
   `0x0525c03c = 0` are live but not written by any DE variant. Never probed.

8. **Only DE variant 1 was mirrored.** Variants 2, 5 and 6 also carry 1280x720
   geometry and differ in ways we did not diff.

9. **Is the second AFBD channel physically present on this die?** H713 may be a
   harvested/reduced variant. We have no datasheet. A fused-off channel would
   explain every result exactly, and we have no way to distinguish that from
   "present but not enabled".

10. **`decd.ko`** — a separate vendor driver for AFBC-compressed video playback,
    with its own frame-submit ioctl and register file at `0x05600000`-ish. Prior
    work concluded it is dead code for the HDMI-RX path, but our use case is
    video playback, which is exactly what it was built for.

---

## 8. Questions we would most like answered

1. On Allwinner display hardware of this generation, what actually gates a
   scanout channel being *serviced* — as distinct from configured? What makes a
   READY/commit latch get consumed?
2. Is a never-consumed commit latch a known signature of a specific condition
   (clock gated, channel fused off, mixer not routing, missing enable elsewhere)?
3. Given the mixer has two window slots both programmed with identical
   geometry, does that indicate two usable layers, or is that pairing something
   else (e.g. double-buffered registers for one layer)?
4. Is there a plausible reason a vendor would ship a display controller with
   two plane register banks and use only one — beyond simple product
   segmentation?
5. Are we wrong that this needs a second plane at all? Is there a way to make a
   single scanout channel fetch two-plane YUV (NV12) directly? We found a format
   selector (`0x05600011`, table row 3 = 8-bit YUV420) and two plane-address
   registers (`0x05600070` Y, `0x05600084` C) in the vendor decoder path, but
   writing them had no effect — they belong to a separate frame-submit register
   file that is not in the scanout path.

---

## 9. Constraints

- No datasheet for H713 display, no vendor source for `display.bin`.
- FEL recovery works, but `sunxi-fel uboot` does **not** on this SoC (SPL loads,
  post-SPL handoff fails), so U-Boot changes require flashing.
- The panel is brought up by U-Boot; Linux cannot re-initialise it, so a broken
  display needs a reboot.
- We have full stock firmware, both eMMC images, and can boot vendor Android.
