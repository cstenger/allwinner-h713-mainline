# H713 display/MIPS handoff for Claude

Last updated: 2026-08-03. This is the short operational companion to
`docs/mips-display-recovery.md`, which remains the detailed evidence log.

## Executive state

The MIPS coprocessor is fully booting, reaches application readiness, and has a
working bidirectional CPU_COMM transport. The panel power, backlight, raster,
LVDS PHY, and TCON-local hardware-pattern path are alive. The remaining failure
is downstream of framebuffer/AFBD/OSD for the hardware-pattern experiments:
the panel does not interpret the generated pixels or link boundaries correctly.

The DCLK sampling edge at `0x05800000[24]` remains the open lead, but it is
weaker than it looked. The A/B/A run showed a phase-locked effect: entering the
normal edge produced a fraction of a second of vertical lines and then removed
the persistent white artifact at the top, and restoring the prior state brought
it back. The follow-up run under a fixed normal edge (`test_14`) then came back
featureless in every phase -- but frame analysis placed the panel's last
structured output about thirteen seconds *before* the DCLK write, so that run
cannot separate "normal DCLK silenced the link" from "the link was already
silent". Treat the edge as untested, not as a candidate fix.

The next artifact and command are ready. Do not rerun the native/1080p timing
test or the broad animation tests first.

## Ready-to-run next experiment

Artifact:

```
build/out/u-boot-sunxi-with-spl-ddr3.bin
size:   919857 bytes
sha256: 338b21a7ec105b6b2b1cb044e49ca041a52aaccc72d04bf379ef993a0975da8e
```

Run the chroma sweep, not the DCLK test. The DCLK avenue is closed: `test_16`
compared both edges under an identical source on one boot and their column
profiles were indistinguishable.

```
h713_disp panel-test 0x33 tcon-chroma
```

Six chroma-blink markers label the phases; count the blinks:

```
1 blink   SOLID RED                6 s
2 blinks  SOLID GREEN              6 s
3 blinks  SOLID BLUE               6 s
4 blinks  CHECKER RED/BLUE 128px   6 s
5 blinks  CHECKER RED/BLUE 32px    6 s
6 blinks  restored                 5 s
```

Markers alternate red and blue rather than flashing white, because white
markers were never once detected in four videos -- the same luminance blindness
that voids the solid black/white history.

What each outcome means:

- **the three solids differ from each other** -- the link carries colour and all
  three components are separately controllable. This is the new positive
  control; if it fails the run is invalid and nothing after it counts.
- **either checker shows visible cells** -- the link carries spatial
  information after all, and the cell size that resolves puts a bound on it.
  This would be the first positive spatial result in the project.
- **both checkers arrive uniform** -- and their colour will land between red and
  blue. The link carries no positional content at all, which is the single most
  important thing left to establish. Every compositor-level theory becomes
  irrelevant and the fault is in pixel clocking or serialisation.

Record a single continuous video. Score by counting blinks; do not use serial
labels, photo order, or file timestamps for alignment.

This build also prints a four-point ownership probe on **every** `panel-test`
mode, at no extra bench cost:

```
H713 probe [ARM records applied  ] 051c0014=... 051c0028=... 05140054=...
H713 probe [MIPS ready           ] ...
H713 probe [MIPS quiesced        ] ...
H713 probe [after DE replay      ] ...
```

It settles who sets the three words the DE replay clears. If they already read
`18000005 / 1f300030 / 40000080` at **ARM records applied**, the ARM's own
LogoRegData blocks own them, the firmware is irrelevant to the clobber, and the
proposed "gate the replay out of the TCON modes" test is aimed at the wrong
layer. If they are empty there and populated at **MIPS ready**, the firmware
owns them and the replay is destroying firmware state.

Static analysis could not answer this: it resolves 604 of the coprocessor's 845
register-helper call sites, and none of the resolved ones touch these three --
but the unresolved remainder computes addresses from runtime tables, so absence
is not proof. Record the four probe lines before interpreting anything else in
the run.

After a complete power cycle:

```
h713_disp panel-test 0x33 tcon-solid-dclk-normal
```

This command:

1. boots the authenticated MIPS firmware and waits for application readiness;
2. quiesces the MIPS core without gating the prepared display hardware;
3. restores the known-responsive 1280x720 TCON timing and Board-B DE block;
4. runs style 8 as a positive control under the stock inverted edge;
5. clears only `0x05800000[24]`, settles one second, and repeats that control;
6. runs the exact Board-B style-2 all-zero and style-3 all-one solid phases for
   7.5 seconds each under the normal edge, switching the generator off between
   them;
7. restores every TCON-pattern word and the complete saved LVDS lane word.

Every phase is preceded by a countable optical marker -- 1 blink before the
first control, 2 before the second, 3 before all-zero, 4 before all-one, 5
before the restore. Score the recording by counting blinks. Do not use serial
labels, filesystem timestamps, or photo ordering for alignment; both of those
methods have already produced a wrong reading on this hardware.

Scoring rules, fixed in advance:

- **control 1 blank** -- the run is invalid, nothing after it counts, and the
  fault is upstream of the generator on that boot;
- **control 1 banded, control 2 blank** -- the normal edge breaks the link, so
  inverted DCLK is correct (it is also what Board B's `panel_config.ini`
  requests) and the edge avenue closes;
- **both banded** -- the all-zero/all-one comparison is meaningful for the
  first time; report whether the two codes differ, and whether the top white
  line, left column, or central oval differ between them.

A single continuous video is the preferred record. Photograph sets are harder
to align and have already caused one wrong conclusion.

## Proven milestones

- Vendor `display.bin` SHA-256 is
  `4380f1b3ed7b62aa50582e7cb16a87bdface1b4300578fe3631a416354da30ce`;
  the recovery code authenticates it before applying firmware patches.
- MIPS execution, MIPS READY, and application readiness all pass. The live
  CPU_COMM header reports `deadbeef/deadbeef`, ARM state 5, MIPS state 5.
- CPU_COMM now completes the entire lifecycle: FreeCall allocation, CALL_ACK,
  RETURN, ARM ReturnCmd, firmware RETURN_ACK consumption, and FreeReturn
  recycling. `b66041d8` produced a clean zero-return round trip.
- Calls to `143ffc87` with parameters 0 through 3 completed correctly but made
  no visible change. Protocol completion is no longer evidence of a display
  effect, and CPU_COMM framing should not be reopened without new evidence.
- Source-transition tracing reached the firmware callback/worker path. It did
  not make a visible frame, moving that specific failure below command
  submission.
- The exact Board-B vendor boot logo was recovered and tried; lack of a visible
  logo means the hand-created bar frame was not the sole problem.
- The Board-B ge2d driver supplied the exact TCON checker register order and
  styles. Red/blue checker style 8 produced three visible color bands rather
  than the expected checker, proving the generator controls the optical output
  but that spatial/color interpretation is wrong.
- At 1280x720, exact solid style 2 (both color words zero) appeared lighter;
  exact solid style 3 (both words `0x3fffffff`) appeared darker, yellowish, and
  nonuniform with a central oval. Both retained a far-left column and jittering
  white line at the top. Uniform sources rule out AFBD data, framebuffer format,
  and checker-cell geometry as causes of those boundary artifacts.
- Preserving the firmware's final 1920x1080 TCON timing was clearly worse:
  mostly white with a dark left column, gradual blue drift, a white oval with
  dark edges, and no change during zero/one phases. Keep the explicit 720p
  relatch for diagnostics.
- DCLK A/B/A with a fixed all-zero source showed a synchronized link change.
  Inverted DCLK had the white top artifact. Entering normal DCLK briefly showed
  many vertical lines, then settled dark blue without the top artifact. The
  previous state after restoration again had the top artifact.
- The DE block 5 replay clears three LVDS PHY and routing bits, identically on
  two consecutive boots: `0x051c0014` `18000005`->`18000000`, `0x051c0028`
  `1f300030`->`00000030`, and `0x05140054` `40000080`->`40000000`. A fourth
  candidate, `0x0560030c`, moved differently on each boot (`00804258`->
  `0080c258`, then `008042d8`->`00804258`) and is dynamic, not a clobber; do not
  cite it. `quiesce` is set for every TCON mode, so the replay has run before
  every generator test to date. The generator needs nothing from the OSD/AFBD
  path, so gating the replay out of the TCON modes is a cheap single-variable
  test.
- The Board-B `panel_config.ini` requests single-port, VESA mapping, 8-bit
  color, inverted DCLK, 1360x760 total, 1280x720 active, and 62 MHz DCLK.
- The panel-setting bit positions were rechecked against the recovered stock
  U-Boot calls: DCLK is `0x05800000[24]`, DE is bit 18, HSync is bit 16, and
  VSync is bit 17. An older note used a differently ordered intermediate array;
  the current recovery implementation is correct on these four positions.
- I2C scan on PH2/PH3 found only address `0x18`, the known STK device. There is
  no responding optional DLPC controller on this bus and Board B's stock DT has
  no corresponding node. Do not send speculative DLPC writes.

## Results that are closed or should not be repeated

- AFBD enable/disable, OSD plane gates, DE replay, repeated animations, and
  repeated bar publications did not expose a usable image.
- The MIPS does not tear down the authenticated DE block; before/after dumps
  were identical where relevant.
- FIFO/PLL sequencing, including the LogoRegData `0xfe` pulse records and
  microsecond delays, is implemented and the display PLL locks.
- The native 1080p TCON timing is not a candidate fix.
- Do not infer timing from converted-photo timestamps. Use serial phase labels
  and the operator's contemporaneous description.
- Do not broaden the I2C search into guessed peripheral initialization.
- Do not change timing, DCLK, mapping, and dual-port mode in one run. The DCLK
  result is valuable because it changed exactly one variable.

## High-value avenues for Claude while waiting for more board runs

### 1. Determine the required latch/reset semantics for `0x05800000[24]`

The live DCLK write caused a visible deserializer resynchronization and was not
perfectly reversible. Trace stock code around every write to `0x05800000` and
answer whether a lane-config change is followed by a TCON configuration latch,
LVDS FIFO reset, PHY disable/enable, PLL pulse, or panel reset. The next cold
implementation should reproduce that sequence rather than assume a live word
write is sufficient.

Useful recovered binary and assets:

```
local/mips-display/research/uboot_real.bin
local/mips-display/board-b-mips/panel_config.ini
local/mips-display/board-b-mips/runtime-toc1.dtb
local/h713-lab/captures/board-b/bench_emmc_full.img
local/h713-lab/captures/board-b/board-b-mmcblk0-20260705T072349Z.img
```

The local stock binary is Thumb code loaded at the `0x4a000000` region. The
panel LogoRegData patch loop is recognizable around the comparisons with
`0x05800000`, `0x058c0020`, `0x058c0024`, `0x0588000c`, and `0x058c0014`.
Use the literal register comparisons and helper-call argument shifts rather
than decompiler field names.

### 2. CLOSED: the Saleae cannot decode this LVDS stream

An earlier version of this section proposed recovering lane words, sampling
edge, and VESA/JEIDA mapping from:

```
local/mips-display/h713-lvds-ch0-ch1-active-20260730.sal
local/mips-display/h713-lvds-full-run-ch2-unknown-20260730.sal
```

That is not achievable, and the arithmetic is not close. Both captures are
analog, from a `LogicPro8`, at `analogDownsampledRate` 31250 -- 10.03 s per
channel, confirmed against the file sizes. The link runs at 62 MHz DCLK with
7:1 serialization, so each lane carries 434 Mbps. The capture rate is short by
a factor of roughly 14,000.

Raising the rate does not rescue it either. The Logic Pro 8 tops out at
500 MS/s digital and 50 MS/s analog, with about 100 MHz digital input
bandwidth and 5 MHz analog. Reliable edge recovery on a 434 Mbps stream wants
2 GS/s and several hundred MHz of front-end bandwidth. The instrument cannot
see the signal, let alone sample it.

These captures therefore carry only coarse presence/absence of activity. Do not
attempt lane, edge, or mapping inference from them, and do not re-capture the
LVDS pixel stream with this hardware.

Decoding the stream electrically needs a real-time scope of >=1 GHz with a
differential probe, or an FPGA with a hardware deserializer. Until such an
instrument exists on this bench, the TCON pattern generator plus bracketed
positive controls is the available substitute: it changes one link variable at
a time and reads the answer optically.

### 3. Audit stock panel fields not represented by the current compact model

`PanelNoiseDith = 1` appears in Board B's INI but is not represented in
`struct h713_panel_cfg`. Prove whether stock consumes it in the fast-logo path,
where it lands, and whether a LogoRegData record is patched. Do not add it based
only on the INI string. Also verify that the table's PLL/divider sequence really
produces the requested 62 MHz `PanelDCLK`; the current model relies on the
project table for clock programming rather than recomputing the divider.

### 4. Resolve TCON pattern color-word packing

Reverse the Board-B `tgd_set_checkboard_style()` callers and any definitions of
the two 32-bit color words. Confirm whether `0x3fffffff` is logically white at
the LVDS serializer, how RGB components are packed, and whether the style names
refer to logical LCD transmission or final projected intensity. This matters
because all-zero appeared optically lighter than all-one under inverted DCLK.

### 5. Prepare one-variable mapping/port diagnostics, but do not run them yet

If the pending normal-DCLK solid test still misdecodes pixels, prepare an A/B/A
test for the next most likely field while retaining normal DCLK and 720p:

1. VESA versus JEIDA/mapping field at `0x05800000[7:6]`;
2. only then single/dual-port at `0x0588000c[13:12]`;
3. color-depth field at `0x05800000[4:3]` only after confirming its hardware
   encoding, because the INI value 8 is masked to zero by stock's helper.

Each test must keep the TCON source and all other fields fixed, print complete
before/after register values, include an A restore phase, and restore the full
saved word. If a live change needs resynchronization, reproduce the stock latch
sequence found in avenue 1.

### 6. Obtain a stopped stock register snapshot if practical

The highest-value external comparison remains Board B running its stock logo
path, stopped without destroying display state. Capture at least:

```
0x05800000..0x0580002c   lane/map
0x05880000..0x05880040   TCON/timing/pattern
0x058c0000..0x058c002c   display PLL/current
0x051c0000..0x051c00e0   LVDS PHY
0x0525c000..0x0525c03c   mixer
0x0524c000..0x0524c03c   DE/OSD
```

Compare full words, not selected fields. Board B is the authoritative source;
use Board A only to identify shared code or register semantics.

## Code and documentation locations

- Main recovery implementation:
  `external/u-boot/arch/arm/mach-sunxi/h713_mips.c`
- Detailed chronological evidence and register analysis:
  `docs/mips-display-recovery.md`
- This operational handoff:
  `docs/claude-display-handoff.md`
- Board-B assets:
  `local/mips-display/board-b-mips/`
- Operator photographs:
  `local/lcd-photos/test_8` through `local/lcd-photos/test_13`, plus later test
  directories as created. Interpret them using the operator's phase mapping.

The worktree is intentionally dirty and contains the cumulative recovery work.
Do not discard or reset unrelated changes. Build with `./build/build.sh uboot`;
the persistent `.bss` alignment warning from `ld.lld` is pre-existing and the
current build otherwise succeeds.
