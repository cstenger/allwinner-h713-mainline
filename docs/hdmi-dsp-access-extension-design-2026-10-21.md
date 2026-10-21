# DSP access extension design: domains, clocks, resets — October 21, 2026

**Status: implemented and tested offline; no live run yet.** Module, helper,
boot-v4 and checks: see [preparation evidence](hdmi-evidence/2026-10-21-dsp-access-ext/README.md).
This extends the [read-only prefix](hdmi-dsp-access-audit-2026-10-21.md), which
[passed live](hdmi-evidence/2026-10-21-dsp-access-prefix/README.md), through the
remaining power, clock and reset operations of the old monolithic setup
(`modules/hdmi-dsp-observe/h713-hdmi-dsp-observe.c`). It stops **before**
AudioTop is mapped or read. AudioTop, the DSP port, the shared lock window and
any DSP request remain later, separately reviewed stages.

Goals, in order:

1. Localize the October 21 stall to one operation, or show that every
   power/clock/reset operation before AudioTop completes in a cold logo-free boot.
2. Establish a verified power/clock/reset state from which the AudioTop
   stage can be designed, with each precondition read back from hardware
   rather than inferred from software state.

## Evidence that shapes the design

**E1. genpd's TVCAP state does not reflect hardware in the maintenance DT.**
With `allwinner,keep-tvcap-on` (patch 0128), `sun50i-h713-ppu.c` marks TVCAP
`GENPD_FLAG_ALWAYS_ON` and initializes it on without reading its status
register. The TVFE domain alone takes its initial state from hardware. The
property was added so Linux would not power-cycle TVCAP under a running
display MIPS. MIPS never runs in the maintenance boot, so that reason does not
apply there. Consequence: the old bench's `pm_runtime_resume_and_get()` on
TVCAP was a software no-op whatever the hardware state.

**E2. Both TV domains are physically off at a cold start.** 2026-09-02 (patch
0087, before `keep-tvcap-on` existed): `pm_genpd_summary` showed `TVCAP off-0,
TVFE off-0` with every TV clock gated. 2026-09-18
([resource isolation](hdmi-mips-resource-isolation.md),
`hdmi-evidence/2026-09-18-mips-isolation/`): PPU status read `00020000`
(off) for both TVFE (`0x070010a4`) and TVCAP (`0x07001124`). These status
reads were made directly from Linux and are known safe. The ON claim in the
PPU driver's header comment is contradicted by both.

**E3. A powered-off TV block hard-locks the SoC on access, with the October
21 symptoms.** 0087: a plain read behind the gate gave no output, then serial
went silent and the network dropped; only a power cycle recovered. No abort and no watchdog.
After powering both domains and enabling the TV clocks, the THDMIRX window
read structured values.

**E4. Linux can power both domains on without harming the ARM side.** 0087
did it cold; 09-18 did TVFE then TVCAP (status `00020000`→`00010000` each)
with ARM serial/SSH healthy. The MIPS stall in 09-18 is irrelevant with MIPS
stopped.

**E5. Before AudioTop, every old-bench write lands in the CCU (`0x02001xxx`)
or the PPU (`0x07001xxx`).** The first access to a peripheral that sits behind
a TV domain is the AudioTop read at `0x0614a000`. Its informative `pr_info`
comes *after* that read, and could not reach the console anyway.

**E6. The prefix's live samples.** Demod bus gated and in reset; display bus
`0x02001dd8` = `00010001` (open) although the display node is disabled;
display reset deasserted; MIPS and SCP stopped. Boot flags `clk_ignore_unused
pd_ignore_unused` mean nothing inherited is switched off at late init.

**E7. Clock-tree facts** (`ccu-sun50i-h713.c`, exact build):

| Clock | Reg | Kind | Parent(s) |
| --- | --- | --- | --- |
| pll-video0 / pll-video2 / pll-adc | PLL | NM/NKMP, lock bit 28 | hosc |
| tvfe-1296m | `0xd20` | MP mux gate | pll-video0-4x, pll-adc |
| vincap-dma | `0xd74` | M mux gate | pll-video2-4x, pll-periph0 |
| bus-cap-300m / bus-hdmi-audio | `0xd80` b30 / b31 | gate | ahb |
| hdmi-audio | `0xd84` | M mux gate | pll-video3-4x, pll-periph0-2x |
| bus-tvcap | `0xd88` b0 | gate | ahb |
| audio-cpu / umac / ihb | `0xd48` / `0xd4c` / `0xd50` | gate | ahb |
| deint / panel | `0xdb0` / `0xdb4` | M mux gate | pll-video2-4x |
| svp-dtl / afbd | `0xdb8` / `0xdc0` | M mux gate | several |
| bus-disp | `0xdd8` b0 | gate | ahb |

Resets: demod `0xd64` b16, **tvcap `0xd88` b16**, disp `0xdd8` b16.
`clk_prepare_enable()` also enables the currently selected parent chain, so
enabling `tvfe-1296m` already starts its PLL. The old "PLL after demod reset"
stage is therefore largely a no-op. The old bench's 15 raw "stock" words
overwrite clocks the framework owns (`0xd10`…`0xd60`: tvfe-1296m, i2h, cip-*,
audio-cpu/umac/ihb, tsa432, mpg0/1), mux and divider fields included.
**No code in the repository ever releases `reset_bus_tvcap`**; its cold state
is unknown.

## Ranked hypotheses for the October 21 stall

1. **AudioTop read with TVCAP physically off** (E1–E3, E5). This matches every
   observed symptom and needs no other fault. It depends on AudioTop sitting
   behind TVCAP, which is not yet established.
2. AudioTop read with its bus still in reset or unclocked: `reset_bus_tvcap`
   asserted, or the AudioTop interface needing a clock the raw words did not
   open.
3. A PPU TVFE power transition that does not complete in this context. The
   driver polls with 10 ms timeouts, but a bus-level hang is not bounded.
4. A CCU operation: a PLL lock wait, the raw TVFE words, the demod reset
   release or a display-tree change. These are less likely because CCU writes
   on Allwinner parts do not normally wedge the interconnect.

The extension is ordered so that a hang identifies which of these it was,
and it verifies the two cheap preconditions (TVCAP power, TVCAP reset) before
anything else.

## Design decisions

**D1. Boot `boot-v4`: remove `allwinner,keep-tvcap-on` from the RAM-only
maintenance DT.** Add one guarded U-Boot command after the existing node
edits, `fdt rm /soc/power-controller@7001014 allwinner,keep-tvcap-on`, which
fails (stopping the runner) unless the property existed and was removed. Add
a distinct marker `h713,dsp-observation-v2` so module and helper can tell the
boots apart. Absence is verified in Linux against the DT the kernel actually
booted: module init disables the extension, and the helper refuses, if the
property is present. The
PPU probe performs the same three init writes either way. Only genpd's initial
state changes: it now comes from hardware, and `pd_ignore_unused` still
prevents any power-off. This is the proper fix for E1 rather than a
workaround in the bench, and it is no longer speculative given E1–E3. No boot
media, environment, SPL or proper changes. Production DTs keep the property.

**D2. One module, one continuous step table.** Steps 1–33 stay
byte-for-byte the prefix steps. The extension continues the same table from
step 34 under schema `h713-dsp-access-ext-v1`, so the prefix's resources and
clock handles carry over. The module keeps its name, so the installed guard
(`96f37655…`) already converts reboot/kexec to poweroff while it is loaded.
Init refuses extension mode unless the v2 marker is present and the PPU node
lacks `allwinner,keep-tvcap-on`.

**D3. No software restore once hardware changes.** `release_prefix` remains
available only while every completed step is read-only (step 40 or earlier). After the first state-changing step, the only supported end is an
orderly `systemctl poweroff` with the module still loaded. The guard permits
poweroff, and physical power-down restores everything. This avoids writing
and trusting untested restore code; the old bench's restore was never
exercised.

**D4. One operation per step, with an inner marker.** Each state-changing step
logs `BEGIN`, performs its single operation, logs `OP-DONE`, then re-reads
any listed post-condition and logs `DONE value=…`. This tells a hang in the
operation apart from a hang in the post-read. Post-reads are limited to
registers the prefix or 09-18 already proved readable: PPU status, CCU words,
and MIPS/SCP stopped.

**D5. Clock steps record inherited state and implied parents.** Before
enabling, the step records `__clk_is_enabled()`. Like the old bench, it skips
the enable if the clock is already on and records `already-on`. At each
stage boundary the helper saves a read-only `/sys/kernel/debug/clk/clk_summary`
and `pm_genpd_summary` snapshot, which shows implicit parent enables (e.g.
`pll-video3` from `hdmi-audio`). Both files only read CCU and genpd state,
and both were used routinely in 2026-09.

**D6. Hardware read-back gates, not software state.** Domain steps pass only
when the PPU status word reads `00010000`. Reset steps pass only when
`reset_control_status()` matches the request. Raw-word steps pass only on
exact readback. Delays keep the old values (12 ms display, 10 ms demod and
audio) inside the step that needs them.

**D7. Stage boundaries are explicit stops.** The helper refuses to cross a
stage boundary without `--stage-ack <name>`. I review the boundary snapshot
before giving it. Within a stage each step is still one acknowledged call;
there is no loop.

**D8. Stop before AudioTop.** No AudioTop, DSP port or lock window mapping or
read. Claims from the prefix stay held.

## Step table (continues the prefix)

As implemented in `h713-hdmi-dsp-access-audit.c` (82 steps; `steps.json` in
the preparation evidence is generated from the helper and tested for parity
with the C table). Stage boundaries are after steps 33, 40, 45, 53, 69, 74
and 81.

Stage **C — census** (read-only; `release` still allowed through step 40):

| # | Operation | Touches | Pass condition |
| --- | --- | --- | --- |
| 34 | map-ppu-status | ioremap `0x070010a4`, `0x07001124` (unclaimed, as the PPU driver) | software only |
| 35 | read-ppu-tvfe-status | read `0x070010a4` | readable; record |
| 36 | read-ppu-tvcap-status | read `0x07001124` | readable; record |
| 37 | get-tvcap-reset | handle lookup | handle |
| 38 | read-tvcap-reset | CCU `0xd88` b16 | 0 or 1; record |
| 39 | census-clock-enabled | 17 × `__clk_is_enabled` (CCU reads) | record bitmask |
| 40 | read-tv-ccu-words | 15 CCU words `0xd10`…`0xd60` | record (`tv_words`) |

**Decision rule at the census boundary:** with boot-v4, genpd
(`pm_genpd_summary`) and PPU status must agree for both domains. If they
disagree, stop: the premise is wrong. If TVCAP reads ON at cold, record it
and continue; the domain steps then become no-ops.

Stage **P — power domains** (first state change; `release` refused from here):

| # | Operation | Pass condition |
| --- | --- | --- |
| 41 | attach-tvfe: root device, `of_genpd_add_device` (idx 1), notifier | software only |
| 42 | resume-tvfe: genpd power_on, PPU ctrl write and polls | OP-DONE; status `00010000` |
| 43 | attach-tvcap (idx 2) | software only |
| 44 | resume-tvcap | OP-DONE; status `00010000` |
| 45 | recheck-stopped-after-power | MIPS 0, SCP b0 clear |

genpd notifiers print each power event from inside the transition.

Stage **R — TV resets and receiver clocks:**

| # | Operation | Pass condition |
| --- | --- | --- |
| 46 | deassert-tvcap-reset-if-asserted (no-op, `last_value` 0, if step 38 read 0) | status 0 |
| 47–50 | enable-clock bus-tvcap, bus-cap-300m, vincap-dma, tvfe-1296m | enabled (`last_value` 1 = already on) |
| 51 | deassert-demod-reset, 10 ms | status 0 |
| 52–53 | enable-clock pll-video0, pll-adc (expected already on via tvfe-1296m) | enabled |

Step 46 is new relative to the old bench. It is included because production
always runs after MIPS, which may release that reset, and nothing in our code
does. Its no-op branch keeps the old behaviour when the reset is already
deasserted.

Stage **T — TVFE CCU words** (raw, as stock; framework state goes stale for
these clocks, which is acceptable because no restore follows, D3):

| # | Operation | Pass condition |
| --- | --- | --- |
| 54–68 | write-tv-word-d10 … d60, one stock word each | exact readback |
| 69 | set-demod-bus-gate `0xd64` b0, 10 ms | b0 and b16 set |

Stage **A — audio clocks:**

| # | Operation | Pass condition |
| --- | --- | --- |
| 70–74 | enable-clock bus-hdmi-audio, hdmi-audio, audio-cpu, audio-umac, audio-ihb | enabled |

Stage **D — display tree** (the old bench did this *first*; moved last
because only the later lock-window stage needs it, and E6 shows it largely
open already):

| # | Operation | Pass condition |
| --- | --- | --- |
| 75 | enable-clock pll-video2, 12 ms if enabled now | enabled |
| 76–80 | enable-clock deint, panel, svp-dtl, afbd, bus-disp | enabled |
| 81 | deassert-display-reset-if-asserted (prefix saw deasserted), 12 ms | status 0 |
| 82 | final-recheck: MIPS/SCP stopped, both PPU status words ON | pass |

Then the boundary snapshot, the `extension-end` state, and orderly poweroff.

Reordering the display tree after the TV stages departs from the old
sequence. If the extension passes completely, the old order is not
separately excluded; that is acceptable because the goal is a verified
state, not a byte replay. If localization of the old order specifically is
wanted, run stage D directly after stage C in a second boot.

## Interpreting the outcome

| Result | Reading |
| --- | --- |
| TVCAP status `00020000` at step 35 | E1 confirmed live: the old bench reached AudioTop with TVCAP off. Hypothesis 1 becomes the leading explanation, still to be confirmed at the AudioTop stage. |
| Hang in 41 or 43 (BEGIN, no OP-DONE) | Hypothesis 3: PPU transition. Stop. Compare with 09-18, which differed only by a live MIPS. |
| Hang at a clock, reset or raw-word step | Hypothesis 4 at that exact operation. |
| All steps pass | Every pre-AudioTop operation is cleared in a cold logo-free boot. The stall was at or after AudioTop, and the next stage starts from a hardware-verified powered, clocked, released state. |

## What this will not establish

- Which domain AudioTop belongs to, or whether its read is safe. That is the
  next stage's first question. It needs this verified state and probably a
  TVFE-only versus both-domains comparison.
- Anything about DSP state retention across warm reset, or a warm-recovery
  mechanism.
- The safety of these operations with MIPS running. Production follows the
  logo path, and 09-18 shows TVCAP cycling breaks MIPS.

## Implementation work (items 1–4 done offline; item 5 pending)

1. `tools/hdmi/prepare-dsp-observe-boot.py`: emit `boot-v4` (property
   removal, its check, and the v2 marker); regenerate the reference DTB and
   offline `fdtget` audit; new manifest and hashes.
2. Module: append the extension steps; init checks for D1; stage-boundary
   refusal; release limited to read-only progress; notifiers; `OP-DONE`
   markers.
3. Helper: new schema; `--stage-ack`; boundary snapshots; refuse release
   after the first state change; keep the console/panic preflight.
4. Offline tests: step-table parity with the C source, stage-ack refusal,
   release refusal after step 40, the v1-marker refusal, and the
   keep-tvcap-on refusal. Build W=1 against the exact kernel and check imports
   (now expected to include genpd/runtime-PM, clk enable and reset deassert).
5. Live run: one cold boot, same protocol as `cold-prefix-02`, with stage
   stops for review and an orderly poweroff at the end.
