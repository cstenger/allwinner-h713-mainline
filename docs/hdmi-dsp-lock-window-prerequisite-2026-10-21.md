# Lock-window prerequisite: TVTOP routing — offline investigation, October 21, 2026

**Status: offline analysis; no hardware access.** Follows the
[AudioTop stage run](hdmi-evidence/2026-10-21-dsp-access-at-live/README.md),
where a plain read of the DSP lock word at `0x05001530` hard-locked the SoC.
At that point both TV domains were powered, the TVCAP and demod resets were
released, and all 17 clocks, including the display tree, were enabled.

## Conclusion

The `0x05000000` display/composition region is gated by **TVTOP routing at
`0x05700000`** as well as by CCU clocks. This was already established on
2026-08-07 for the display path. The old DSP bench copied the display *clock*
tree (`h713_display_clocks_on`) but not the *routing* writes of
`h713_display_prepare`, repeating that failure mode. The AudioTop extension's
stage D did the same. The leading candidate for the missing prerequisite is
therefore the TVTOP routing sequence that U-Boot performs cold in every normal
boot. This is a strongly supported inference, not yet a hardware result.

## Evidence

1. **The same hang, recorded before.** `external/u-boot/arch/arm/mach-sunxi/h713_mips.c`
   (teardown path):
   > *The clocks alone are NOT enough, which cost a hang on 2026-08-07:
   > h713_display_clocks_on() ran, and the very next AFBD read still took the
   > board … the TVTOP routing at 0x05700000 is part of what makes these
   > blocks reachable, not merely part of configuring them.*
2. **The proven cold primitive.** `h713_display_prepare()` runs
   `h713_display_clocks_on()`, then writes TVTOP `+0x04 = 00000001`,
   `+0x44 = 11111111`, `+0x88 = 11111111`, `+0x00 = fff11111`,
   `+0x40 = 00011111`, `+0x80 = 00001111`, `+0x84 = fff000ef`, waits 12 ms,
   then writes the mixer word `0x0525c038 = 00000100`. Its comment reads:
   *"the initial SPL values open only part of the display fabric."* U-Boot
   calls it cold in every normal boot before any display access.
3. **What a logo-free cold boot has instead.** SPL (`dram_sun50iw12.c`,
   `iw12_bus_init`) treats `0x05700000` as the "NSI" register file. That file
   needs the MBUS clock: with MBUS off, the first NSI read hangs the bus. SPL
   only sets bit 4 (read-modify-write) at `+0x40`, `+0x44` and `+0x80` after
   bringing MBUS up. Nothing else writes TVTOP before Linux when the catcher
   stops autoboot.
4. **Every successful `0x05000000` access followed `prepare`.** The September
   scan of `0x05000000` (16 populated blocks, including `0x05001500` next to
   the lock word; `docs/hdmi-in.md`) and all 75 recorded TVTOP captures
   (`+0x00 fff11111`, `+0x04 00000001`) come from boots in which U-Boot had
   run the display path. There is no capture of TVTOP from a logo-free state.
5. **The audio blocks are not behind it.** In `cold-at-01`, AudioTop
   (`0x0614a000`) and the DSP status port (`0x06144000`) were readable with
   SPL-only TVTOP, so the routing requirement is specific to the
   `0x05xxxxxx` display fabric that holds the lock window.
6. **The old bench's own comment** says it reproduced "h713_display_clocks_on's
   complete tree before accessing that window." That is the clocks-only state
   that hung on 2026-08-07.

## What this changes

- **October 21 stall.** The old bench had two missing prerequisites on its
  path: TVCAP power and reset before AudioTop, and TVTOP routing before the
  lock window. It most likely hung at the first, the AudioTop read. It could
  not have passed the second.
- **The lock-window stage.** Steps 83–93 are unaffected. Before any
  `0x0500xxxx` access, the bench must perform the TVTOP routing.

## Proposed next stage (design input, not yet designed in full)

Insert a **TVTOP stage** before the lock-window map/read:

1. **Read-only census of TVTOP** at cold, recording the SPL-only state.
   `+0x40`, `+0x44` and `+0x80` are proven readable at this point, because
   SPL read-modify-writes them. `+0x00`, `+0x04`, `+0x84` and `+0x88` are in
   the same MBUS-clocked file but their cold readability is unproven, so each
   gets its own step. Note too that the 2026-10-16 trace never sampled TVTOP.
2. **The seven routing writes**, one per step, in `h713_display_prepare`'s
   order and values, each with exact readback. `+0x00` reading back
   `fff11111` is expected, since that is what it wrote.
3. **The mixer word `0x0525c038 = 00000100`:** recommended **not** to be
   included. It lies inside the gated fabric, `prepare` writes it for the
   MIPS's sake, and the lock window does not need the mixer. Include it only
   if the lock read still hangs with routing in place.
4. Then the existing lock-window steps (map, peer, own) and the final
   recheck.

**Interpretation:** if the lock read completes after routing, the
prerequisite is confirmed. If it hangs with routing in place, the remaining
candidate is the mixer write, then a comparison of the full `prepare` effect
against a MIPS-live register snapshot. The TVTOP writes touch only the
routing file, so they are reversible by power-off, consistent with the
bench's poweroff-only end.

## Open points

- Whether reading TVTOP `+0x00`/`+0x04` at cold is safe (unproven; split
  into separate steps for that reason).
- Whether `prepare`'s 12 ms settle times matter for the lock window
  (keep them).
- Warm-reset relevance: TVTOP is in the MBUS/NSI domain. Whether a warm reset
  restores SPL-only routing is a reset-contract question for later.
