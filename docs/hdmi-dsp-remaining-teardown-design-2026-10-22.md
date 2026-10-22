# Remaining teardown versus reset — next diagnostic design, October 22

**Source-reviewed design and takeover instructions; not an executable candidate.**
The user confirmed the board is fully unplugged after matched boundary arm 2.
No capture is armed. No hardware access, new module build, board staging or
reset was performed while preparing this document. Claude must implement,
build and validate the next isolated bench before requesting power.

## What the completed batch establishes

[Sham](hdmi-evidence/2026-10-22-dsp-owner-sham-live/README.md) and
[matched boundary](hdmi-evidence/2026-10-22-dsp-owner-boundary-live/README.md)
each completed four `1/1` version pairs. The matched run verified all 22
normal graph restorations, cleared AudioTop config, then cycled control
`700 → 0 → 700`, without losing the version report. Exact initial register
census and saved graph words matched. No reset/warm logo occurred after
patching. This qualifies that controlled sequence, not the full teardown.

The previous warm control-only zeros still span additional operations.
In particular, **terminal MIPS parking is itself a reset intervention before
CPU reboot**: `h713_receiver_park_commit()` asserts three MIPS reset lines,
checks status zero, then drops two core clock holds. Do not call all prior
shutdown operations “no reset,” or attribute a subsequent zero to CPU reset
without excluding this earlier reset. `release_when_parked` is another
boundary: it releases receiver clocks/domains after parking. Keep it separate.

## Exact source map and normal order

Pinned production sources are unchanged; see the accompanying
[source manifest](hdmi-evidence/2026-10-22-dsp-remaining-teardown-preparation/source-review.json).

| Order | Source | Action to bracket |
| --- | --- | --- |
| 1 | `modules/hdmi-audio/h713-hdmi-pcm.c:606`, `release_resources()` | Free PCM/card; normal DSP graph restore/release |
| 2 | same, SPDI blocks | Restore saved CTL0, CTL1, AudIf IRQ mask; synchronize/free IRQ |
| 3 | same, bridge blocks | Restore bridge IRQ mask/global enable, inert stream words, sync and address-high; free IRQ/DMA |
| 4 | same, AudioTop block | Restore saved config then control (normally zero) |
| 5 | same, IHB/audio-clock blocks | Restore saved IHB word, drop only clocks enabled by driver |
| 6 | `modules/hdmi-audio/h713-hdmi-tvfe.c:80`, `h713_hdmi_tvfe_release()` | Gate demod bus while reset released; restore 15 CCU words in reverse order; drop parent holds; assert demod reset; restore saved bus word |
| 7 | `modules/hdmi-receiver/h713-receiver-power.c:256` | Audio's receiver client reference release only; does not itself release domains |
| 8 | `modules/hdmi-receiver/h713-receiver-park.c:109` | Terminal MIPS reset assertions, status zero, core clocks off |
| 9 | `modules/hdmi-receiver/h713-receiver-power.c`, `release_parked()` | Release receiver/EDID clocks and runtime domain holds |
| 10 | reboot / U-Boot / Linux | CPU reset, early boot, warm logo and observer preparation |

Current bench skips PCM in both arms and disables IRQs before measurement.
It deliberately pins resources. **Do not invoke normal `release_resources`,
session `stop/park/shutdown`, rmmod or reboot to simulate a single boundary.**
Those combine operations, unmap the observer and can reset/power down hardware.

## Next live batch: extend the same-owner observer, preserve normal ordering

Build a new isolated candidate in a new directory; do not mutate
`build/hdmi-dsp-owner-boundary-2026-10-22/candidate/` or its recorded assets.
Reuse its proven cold launch, sole owner, pinned resources, phase/raw-word
capture, stock ARM lock, immutable arm, checked ledger and export/poweroff.
Use a new schema/DT opt-in and new manifest binding the intervention plan.
The current 25-step module has no operations for the remaining boundaries.
The old successful sham is background evidence; it cannot qualify a changed
module, altered observation path or added clock/reset operation by hash bypass.

Prepare a new sham and intervention arm using the **same new module** and
identical cold startup/firmware/kernel, separate >=1-minute unplugged cycles.
The new sham must qualify every planned version checkpoint and every common
access-restoration action. Intervention arm must match baseline reads, saved
graph/SPDI/bridge/clock words and actual held-clock ownership. Dynamic DMA
addresses may differ: compare their range/alignment/inert configuration and
record exact values, rather than requiring equal allocator addresses.

### Phase A: remaining register teardown, while all access clocks stay held

This is the first implementation and live target. It introduces no reset or
clock removal and can reuse the established owner-health assumptions.

1. Fresh cold initialization, initial `0/0` → patched `1/1`; measured positive
   pair. Keep AudioTop `700/011a5e00`, MIPS live, both domains ON, no PCM.
2. Restore the exact 22 saved graph words in **both** new arms; obtain a
   patched pair. This common prefix preserves normal teardown ordering.
   If either arm loses access/version here, stop and review the contradiction.
3. Intervention: restore SPDI1 CTL0/CTL1, then saved AudIf IRQ mask in the
   exact normal order. Sham: no writes, same review/settling checkpoint.
   Keep IRQs disabled, IRQ objects/maps and DMA allocated, no route/status
   writes. Verify the saved register readbacks, then obtain one pair.
4. Intervention: restore bridge saved IRQ mask/global enable, then saved
   stream START/END/BLOCK/CONFIG/FLUSH, STREAM_SYNC and address-high, in exact
   normal order. Sham: no writes. Verify readbacks, then obtain one pair.
   Require initial `audbrg_stage_applied == 3` (no PCM streaming). Do not add
   the stage-4 flush pulse. Retain IRQ objects, disabled handlers and DMA;
   resource deallocation itself is not a hardware-register intervention.
5. Intervention: perform normal AudioTop config/control restoration followed
   by control-only `700/0` access restoration; sham uses its explicitly
   qualified counterpart. Pair after each separately reviewed AT transition
   if needed to distinguish an interaction introduced by SPDI/bridge.
   No DSP/AudIf/bridge/stock-lock read while control is off. Preserve exact
   full-state preconditions; do not blindly reuse old fixed 25-step numbering.
6. Terminal snapshot/export/checksum/poweroff. Stop at the first completed
   changed/mixed pair or timeout; do not advance to clocks on that cycle.

Register addresses and saved source fields:

| Register | Address | Restore source |
| --- | --- | --- |
| SPDI1 CTL0 / CTL1 | `06146034 / 06146038` | `spdi1_saved_ctl0 / spdi1_saved_ctl1` |
| AudIf IRQ mask | `06146004` | `audif_saved_mask` |
| Bridge IRQ mask / global enable | `06148388 / 06148384` | `audbrg_saved_irq_mask / audbrg_saved_global_irq_en` |
| Bridge stream START / END / BLOCK / CONFIG / FLUSH | `06148100 / 06148104 / 0614810c / 06148110 / 06148114` | `audbrg_saved_stream[0..4]` |
| Bridge STREAM_SYNC / address-high | `06148390 / 06142044` | `audbrg_saved_stream_sync / audbrg_saved_addr_hi` |

These are implementation references, not commands for an independent MMIO
client. Restore only values captured by the sole owner at normal setup.
Do not restore `audif_saved_route`: normal teardown does not write it.
Do not clear W1C status as a new experimental operation. Saved values,
active preconditions, applied flags and every write/readback belong in state
and UART. Treat readback mismatch or partial restoration as hard failure;
no rollback/retry. Keep the lifetime pin after terminal state.

### Phase B: clock restoration versus demod reset, only after Phase A passes

A clock-off version request can stall in MMIO; polling deadlines do not bound
that access. This phase needs **new observation logic and offline tests**,
not just another case in the current `owner_operation()` switch.

* Hold TVFE/TVCAP domains and receiver resources throughout. Maintain a
  software phase that prohibits DSP/AudIf/bridge and stock-lock access while
  clocks/bus/AT are unavailable. Use only proven CCU/status mappings then.
  Do not read debug clock/domain summaries whose providers touch disabled
  blocks until the access gate is qualified again.
* Separate IHB/audio-clock restoration, reverse 15-word TVFE restoration and
  parent-hold release from **demod reset assertion**. Retain mappings,
  references and saved values; preserve CCF counts and shared reset balance.
  Record which clocks were inherited versus enabled by this driver and
  restore only the latter through the correct provider API. Raw clock writes
  cannot silently replace CCF bookkeeping. Receiver holds can prevent a
  requested clock from actually stopping: require and report hardware state.
* Restore the known live access context without DSP patch/graph/SPDI/bridge
  initialization or source3 relaunch: correct parent/functional clock order,
  demod bus last, exact readbacks, AudioTop control-only. Qualify this
  restoration path on a patched no-reset control before attribution.
* A first changed completed pair after clock restore/reacquire localizes to
  that **round trip**, not to the off edge alone. If still `1/1`, separately
  assert the already-held shared demod reset through its balanced API,
  verify, deassert with the established settling/order, reacquire access,
  then pair. This is a reset boundary and must be labelled as such.
* Resolve and document access readback masks, expected MIPS state, provider
  reference accounting and failure handling before building/running this
  phase. Never call full TVFE release then normal prepare: that combines
  demod reset and clocks and invalidates the intended split.

### Phase C: MIPS parking versus domain release versus CPU reset

Only needed if earlier qualified observations remain `1/1`.

1. Separate the three existing terminal MIPS reset assertions/core-clock
   shutdown from receiver/domain release. The production parking API refuses
   live audio clients and is terminal; do not bypass it or decrement client
   counts just to admit a pinned owner. A new explicit bench ownership
   transfer/observer contract is required. Retain domains and record reset
   lines/MIPS status; **do not restart MIPS/source3** for measurement.
2. A parked observer must expect MIPS status zero; current owner health
   requires one and cannot be reused. Qualify DSP access/completion under
   parked MIPS before interpreting a timeout as patch loss. Do not claim a
   CPU-reset boundary from any local-reset or domain-transition experiment.
3. Treat receiver/domain power release as its own destructive retention
   boundary, if later tested. It must not be silently included in a purported
   “MIPS reset only” test. Existing TVFE-ON controls should remain effective
   until an explicit domain test is designed.
4. Only then consider one captured CPU warm reset and a **pre-warm-logo**
   observer. Intercept proper U-Boot before logo/source3 and retain GP6/GP7.
   Validate any RAM-only boot/DT path and inherited routing/clocks without
   bootstrapping the normal audio driver or patching again. Do not clear the
   one-launch latch or use `boot`/normal startup as recovery. A post-reset
   read still includes reset/early boot and its qualified access preparation;
   warm logo is a later independent boundary.

## Implementation acceptance gates for Claude

Before arming Phase A:

* Add the fixed SPDI/bridge restoration entry points inside the isolated PCM
  translation unit and a software-only state record. Production files remain
  unchanged. Add monotonic one-shot checkpoints/acknowledgments and bounded
  host calls; new plan explicitly enumerates each operation and max requests.
* Require the correct new DT marker/arm/proof and exact loaded build ID.
  Baseline must expose saved/current SPDI/bridge values, stage 3, no active
  stream, disabled IRQs, pins and domain/access checks. New sham must pass.
* Native tests cover exact restore order/values, no writes in sham, no route/
  W1C/flush pulse, negative preconditions, partial failure, bad readback,
  timeout → skip/release/terminal only, changed pair → no later operation,
  and exact command-echo ambiguity. Python tests bind manifest/plan/sham,
  fresh boot/ledger and baseline/saved context; reject old-schema sham reuse.
* Real W=1 build against unchanged production kernel/config/Symvers; verify
  module/vermagic/build ID, firmware and cold-script hashes/payload CRC.
  Run relevant current 14 owner tests plus existing startup/boot/minimum
  regressions as appropriate. Old tests passing does not validate new code.
* Preserve one UART reader and fixed host deadlines (20 s steps, 60 s init).
  Never retry uncertain steps/launches. Software snapshots only after hard
  failure; no forced cleanup. Busy/done/peer waits stay bounded; exact echo
  `80ff0000` is ambiguous, never a completed zero. Preserve all raw 32 bits.
* Export/host checksum before checked poweroff, UART Power down then close
  recorder. User physically unplugs between cycles. No new capture currently
  exists; announce power-on only after the new sole catcher reports OPEN.

Additional invariants: no GP7 writes or GP6 clear; no CPUS/ARISC `07091xxx`
reads; PPU bus `070101ac` bits 0/16 before PPU reads; TVFE/TVCAP ON mask
`30000 == 10000` and idle bit 3 clear; no `0500` lock reads before TVTOP
routing; sole stock lock owner, peer never written; own `55/aa` only.
No firmware relaunch or arbitrary DSP writes, and no patch reload after
initialization. Guard/original backup remain unchanged.

## Starting point and remaining work

Start with commits `d57d21e` (old candidate preparation), `119be31` (sham),
`57c6328` (matched boundary). Current user explicitly requests preparation and
Claude takeover; **the next bench is designed here but not built or armed**.
Claude's first task is Phase A implementation/offline verification. Then arm
new sham, ask for power, complete/export/poweroff, cold-cycle matched arm.
Do not re-run the completed 25-step experiment as if it tested the new gaps.

The planned first two arms are finished. Next Phase A needs two new cold
cycles if the module changes; Phase B/C may require further matched cycles.
The earlier 2–4 remaining-run estimate was provisional and is not a hard
limit. There is no source-backed fixed run count until access restoration
and reset observation are qualified. Stop when a discriminating result is
obtained, then plan one independent confirmation of that result.
