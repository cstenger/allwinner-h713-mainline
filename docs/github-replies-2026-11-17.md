# Responses to well0nez — 2026-11-17

**Posted 2026-11-17** at Chris's request; each body was read back and matches
this file (paragraphs unwrapped for GitHub):

- [Issue #1](https://github.com/cstenger/allwinner-h713-mainline/issues/1#issuecomment-6947719170)
- [Issue #2](https://github.com/cstenger/allwinner-h713-mainline/issues/2#issuecomment-6947719479)
- [Issue #3](https://github.com/cstenger/allwinner-h713-mainline/issues/3#issuecomment-6947719815)
- [Issue #4](https://github.com/cstenger/allwinner-h713-mainline/issues/4#issuecomment-6947720173)

These answer well0nez's comments of 2026-11-16 on issues #1–#4. Record links
are pinned to `e8e37ada`, which is on `origin/main`. The #4 reply also links
0211 (`158c30ff`) and 0212 (`146ca6d3`), both on `origin/main`.

Source comments:

- [#1, 6923703959](https://github.com/cstenger/allwinner-h713-mainline/issues/1#issuecomment-6923703959): project state, CPU_COMM notes, HDMI-RX/audio order
- [#2, 6923727513](https://github.com/cstenger/allwinner-h713-mainline/issues/2#issuecomment-6923727513): packing concession, 19 ACKs withdrawn, pulse, 0014f return, ge2d
- [#3, 6924731344](https://github.com/cstenger/allwinner-h713-mainline/issues/3#issuecomment-6924731344): LPDDR3 boot0 second source, 792 vs 624 MHz
- [#4, 6924775553](https://github.com/cstenger/allwinner-h713-mainline/issues/4#issuecomment-6924775553): CPU_COMM IRQ recipe, audit notes, NSI, amplifier pop

## What was checked before drafting

| Claim from well0nez | Our tree | Result |
| --- | --- | --- |
| cpu-comm should be SPI 46; watchdog shares SPI 46, should be 53 | 0198 (pushed 2026-11-15, after the `1c35fc8` snapshot they compared) | Already done |
| Request only bank 0; drain/clear status, enable after `request_irq()` | 0199, 0205 (clears our status bit and enables after the request; drains in the thread) | Already done, IRQ is the default (no backstop poll runs beside it) |
| 0014f's `-EBUSY` is dropped by `SendComm2CPUEx()` | 0208 propagates and unwinds it | Already done |
| Pulse against no pulse is unsettled | 0209: 20/20 no-pulse probes, pulse removed | Settled here |
| 0298 and 0305–0308 reset guard | 0210 resets `RST_BUS_VE3` only | Already done |
| 0312 drops errors; 0313 is wider than the H713 | 0207 checks each step; 0206 is H713-only | Already done |
| `sunxi-nsi` cannot bind (compatible mismatch) | True; driver is also off in our defconfig, and its probe resets the controller | **New 0211: node disabled** (DTBs differ only in `status`) |
| PA enable falling edge pops (PL2), so keep the amp on | Our PA is also PL2; our requirement is zero pops | **Not adopted.** Measured 2026-11-17: our stop pop is the module clock stopping at PCM close under a winding-down PA ([evidence](speaker-pop-evidence/2026-11-17/README.md)); fix in [speaker-power-plan.md](speaker-power-plan.md) |
| Above 672 MHz, `iw12_phy_train()` changes byte-lane pads | `dram_sun50iw12.c:657`; 624 and 792 MHz fall in the same `<= 800` timing bin | Confirmed |

---

## Issue #1 — Nice work Mate

Thank you for the detailed reply and for walking through the whole repository rather than the series alone. The
subsystem pages and the dated notes are the parts I was missing, and the HDMI-RX and audio ordering list answers my
question directly.

Two things line up with what we found independently:

- **Step 3 (attach to the running firmware without touching the queues).** We reached the same rule from the other
  side: an init path that cleared shared rings belonging to a running MIPS.
- **Step 4 (ARISC before any `0x0709xxxx` access).** We have a hard-lock on a read of `0x07091000` before ARISC init,
  and our HPD work stopped at `0x07091014` for the same reason. Your arisc.md gives the ordering that explains it.

On firmware identity: thank you for `16c74a28...` and for confirming that the `projector09220931` variant of
`hy200-qz713df-a1` is the `4380f1b3...` image on our bench. Since your bare-type CPU_COMM sender works on both
revisions, the encoding is no longer specific to one image.

Your "not measured" list has one item we can fill in. HDMI audio does reach ALSA here: we capture it through a
22-word DSP routing graph and play it to the speaker from userspace. The mixer gains and mute words were the
non-obvious parts. Our HDMI and display firmware are also started from U-Boot, so we have no data on a cold start with
the firmware launched from Linux.

Thanks for the build command for our board variant. Our bench is currently the reference for our own production
image, so I can't promise a side-by-side run soon. If I do one, I will use the installer's dump and restore and report
back here.

## Issue #2 — patch 0014 came from my Archived/ folder

Thanks for checking the call sites and for withdrawing the 19-ACK result explicitly. That settles the packing: bare
type on the wire, now confirmed on two `display.bin` revisions. Your four ACK-without-RETURN causes (wrong channel key,
no channel at `INSTALL_RT`, `THal_Vp_Init` with `Para[2] = 0`, a second NewCall reader) are a useful checklist next to
ours.

**The pulse is settled on our bench.** In the production `display.bin`, the firmware's own send waits on the count and
writes the data word, with no TX-IRQ enable write. On channel registration it arms its own RX interrupt for our FIFO
(`0x03003820` bit 2). It never handles the TX-room interrupt that our pulse enabled. A protocol-free probe drained
20 out of 20 no-pulse doorbell words (median 36 µs), so the data write alone is the doorbell. Kernel 0209 removes the
pulse. It passed our 6003-call qualification after both power-on and a warm reboot. Details are in the
[doorbell record](https://github.com/cstenger/allwinner-h713-mainline/blob/e8e37ada/docs/reviews/well0nez-2026-11-14/cpu-comm-doorbell.md).
That result is on `4380f1b3...` only. Your firmware may behave differently, but your spring arm32 data-only
observation points the same way.

**0014f.** We hit the same discarded return. Our 0208 reserves FIFO room under a lock *before* setting SENT in shared
memory, so a refusal leaves nothing published. It then propagates the error out of `SendComm2CPUEx()`, frees the
unpublished wait object, and returns the call slot to the cache. It also stops `SendAckLow()` from calling `BUG()` on a
still-published ACK. Details are in the
[TX record](https://github.com/cstenger/allwinner-h713-mainline/blob/e8e37ada/docs/reviews/well0nez-2026-11-14/cpu-comm-tx.md).
The ordering matters for your tree too: a count check after SENT is already set cannot undo the publication.

**ge2d.** Thanks for the pointer and for being clear that it has no plane-open sequence. The `doku/192` register
words (AFBD channel 2 at `0x05600140`, plane block `0x0524C000`, the corrected vblender words) are the useful part for
us. I have dropped `21959adc...` from my notes.

## Issue #3 — a third QZ713 board

Thank you for the independent LPDDR3 source. A vendor boot0 matching `hy200_qz713_v2_defconfig` word for word, with
only the flashing-tool pair and the per-board training template differing, is better provenance than our one capture.
That board is still unbooted on our side, as on yours.

The 792/624 history matches what we have. Our saved bench boot0 decodes as DDR3 at 624 MHz, and our `display.bin` is
the 2025-09 image, so our unit is the 2025-09 build. I also checked the driver point: in our U-Boot,
`iw12_phy_train()` sets the four byte-lane pad registers (`0x344`–`0x4c4`) with a different mask above 672 MHz, and
both clocks fall into the same `<= 800` branch of `iw12_set_timing()`. So 624 → 792 is a pad change as well as a
clock change. Our bench stays at 624 for the reason you give.

Thanks for confirming 0005a on the HY310 with the same omission. Together with our cold test, that is two boards
where the Linux SIDDQ clear is what makes the ports work.

## Issue #4 — HY310 fixes

Thanks for the correction on SPI 21, and for the patch offer. It isn't needed: the CPU_COMM interrupt correction
landed on `main` the day after the `1c35fc8` snapshot you compared against.

- **0198:** cpu-comm lists 46/109/108 in bank order, and the watchdog moves to SPI 53.
- **0199:** the driver requests only index 0 with a ONESHOT threaded handler. After `request_irq()` succeeds it
  clears our RX bit in `0x124` and sets `BIT(2)` in `0x120`. The thread drains, clears the status, then re-enables.
- **0205:** IRQ receive is the default. Without a usable line, the driver falls back to the poll.

On our bench the default configuration completed **6003 calls** (serial plus concurrent) with **12006 RX messages by
IRQ, none by polling** and no TX desync, after both warm and cold boots. That is not quite the parallel-poll check you
suggested: 0199 removed the old backstop poll, so no poll runs beside the IRQ and nothing could have rescued missed
interrupts. Our first IRQ trials did fail, but the cause was our own U-Boot: its comm-trace trampolines used MIPS
`$k0/$k1` and corrupted the firmware under interrupt load. U-Boot 0006 fixed that. The details are in the
[CPU_COMM handoff record](https://github.com/cstenger/allwinner-h713-mainline/blob/e8e37ada/docs/reviews/well0nez-2026-11-14/cpu-comm-handoff.md).
We never requested 109, so I have nothing on why it storms for you.

**Your audit items are also done here, as adaptations rather than direct imports:**

- 0298 and 0305–0308: kernel 0210 pulses only `RST_BUS_VE3` at a codec switch. AV1 does not use that reset, so no
  guard is needed. VP9+H.265 pairs became bit-exact, AV1 decoded bit-exact beside thousands of those pulses, and 30
  full-VE watchdog pulses during continuous AV1 left it exact as well. See the
  [decoder-reset record](https://github.com/cstenger/allwinner-h713-mainline/blob/e8e37ada/docs/reviews/well0nez-2026-11-14/decoder-reset.md).
- 0313: kernel 0206 enables the threshold for H713 eMMC only
  ([record](https://github.com/cstenger/allwinner-h713-mainline/blob/e8e37ada/docs/reviews/well0nez-2026-11-14/emmc-threshold.md)).
- 0312: kernel 0207 checks the reset, the host init, the IDMA reset and the clock restore before it issues CMD12. It
  recovered three natural read errors on our bench
  ([record](https://github.com/cstenger/allwinner-h713-mainline/blob/e8e37ada/docs/reviews/well0nez-2026-11-14/emmc-recovery.md)).

Your authorship and links are kept in those patch headers.

**NSI:** you're right that the node cannot bind. Our defconfig also leaves `CONFIG_SUNXI_NSI` off, so it never has
bound. I have not fixed the compatible string, because that driver's probe resets the live bus controller and writes
registers nobody has checked against stock. Patch 0211 ([158c30ff](https://github.com/cstenger/allwinner-h713-mainline/commit/158c30ff)) marks the node disabled, with a comment saying
why. Both board DTBs differ only in that `status`.

**Amplifier:** thanks for the microphone numbers; they made me measure ours properly. Our PA is the same PL2 line.
Our requirement is no audible pop at all, so keeping the amp on is not enough by itself for us. With a mic and the PA
line, the DAPM state and the PCM state logged every 2 ms, this is what we found on our board:

- Raising PA (700 ms after the analog power-up, 200 ms after START) is silent.
- Dropping PA on trigger STOP, with the codec still clocked, is silent.
- **Closing the PCM pops**, even with digital-zero samples and the DAC muted first. `sun4i_codec_shutdown()` stops the
  codec module clock a few microseconds after STOP drops PA, while the amp is still winding down. A raw-ALSA test that
  separates the two pops at 0–10 ms between STOP and close, faintly at 30 ms with the fan off, and not at 100 ms and up.

So on our board the stream-end pop is the clock stopping under a live amp. Kernel 0212 ([146ca6d3](https://github.com/cstenger/allwinner-h713-mainline/commit/146ca6d3)) now ties the module clock and
the analog path to one power state. PA comes up 700 ms after they settle, and goes down 300 ms before they stop.
The state stays up while the projector is awake and goes down for standby, suspend and shutdown, so a PCM close
no longer stops the clock. On our bench, 46 stop/close/power/standby events and a reboot from 0212 into itself now
show no flagged pop; a test impulse is still detected 3/3. Before 0212, every close popped. This may explain your mains-off pop
too, if PA is still on when the rails take the clock away.

**Focus motor and AFBD:** agreed on both. One correction on our side: we don't park the MIPS in production. U-Boot starts `display.bin` once and it keeps running (panel timing, the HDMI receiver, the audio DSP graph over CPU_COMM); parking was only a bring-up diagnostic. Our AFBD driver does program the video planes and geometry itself on top of the running firmware, so your 1080p pieces
are a reference for us rather than a drop-in.
