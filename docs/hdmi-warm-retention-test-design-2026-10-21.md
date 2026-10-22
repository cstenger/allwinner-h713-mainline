# MIPS-live warm-retention test design — October 21, 2026

**Status: design for review. Nothing here is implemented or run.**

## Question

Does the DSP's volatile patch survive a warm reset? Production loads it once
per cold boot: versions `0/0` → 724-pair patch → `1/1`. Today's warm path
fails closed through the GP6 launch latch without that being measured
([warm-reset investigation](hdmi-warm-reset-investigation-2026-10-20.md):
*"Whether an orderly or abrupt system reset restores DSP `0/0` is
unmeasured"*). The answer decides the recovery mechanism:

- **Patch erased (`0/0`) after warm reset** → a fresh-reset path is viable
  from the DSP's side. That is the investigation's preferred hypothesis;
  MIPS/GP6 policy still has to be solved separately.
- **Patch retained (`1/1`)** → warm recovery needs a validated retained-state
  adoption protocol, because production's `0/0` predicate would refuse.

The logo-free bench reproduced every prerequisite except a working DSP lock
([lock-word backing](hdmi-dsp-lock-word-backing-2026-10-21.md)). This test
therefore uses the **production path**, where the lock works, and asks the
question with as little added state change as possible.

## Principles

- **Production boot policy unchanged.** No GP6 clear, no GP7 reuse, no MIPS
  relaunch, no guard change, no boot-media or environment write. The only
  deviation from a normal boot is stopping at the U-Boot prompt to run
  read-only `md.l` commands, then `boot`, which runs the same `bootcmd` that
  autoboot would.
- **Read-only first.** Phases A–C send no DSP command and write no register.
  A version read (phase D) is designed only after A–C show whether it is
  needed and whether the lock works in the warm state.
- **Every read is justified by its domain state.** Never read CPUS/ARISC
  (`0x07091xxx`). Read the PPU only behind its open R_CCU gate. Read the
  lock window only behind verified TVTOP routing. Read AudioTop only with
  both TV domains ON.
- **Evidence chain.** The cold baseline's `1/1` comes from production's own
  journal lines (`DSP versions 0000/0000`, then `pinned 724-pair DSP patch
  verified versions 1/1`), correlated by boot ID with the UART trace.

## Read sets

**U-Boot preboot set (U)**, at the prompt before logo/workspace:

| Read | Why | Safety |
| --- | --- | --- |
| proper trace `H713 RESET`/`H713 DOMAINS` lines | existing 22 CCU/SCP controls incl. `tvcap_bus` | already printed by the installed proper |
| `md.l 0x070101ac 1` | R_CCU bus-r-ppu gate (b0) / reset (b16) | R_CCU always readable |
| `md.l 0x070010a4 1`, `md.l 0x07001124 1` — **only if `0x070101ac` has b0 and b16 set** | PPU TVFE / TVCAP power state | PPU gated behind its own bus clock/reset |
| `printenv bootcmd` | confirm `boot` equals autoboot | read-only |

**Linux set (L)**, read-only via `busybox devmem` or a read-only helper, in this order:
1. Boot ID; production state (handoff present or not, unit states, the
   journal's DSP lines, MIPS status `0x0306101c`); the existing
   [state collector](../tools/hdmi/collect-reset-state.py).
2. R_CCU `0x070101ac`; PPU `0x070010a4`, `0x07001124`. Linux's PPU driver has
   opened the gate, which `0x070101ac` confirms first.
3. TVTOP `0x05700000`, `+0x04`, `+0x40`, `+0x44`, `+0x80`, `+0x84`, `+0x88`.
4. **Only if both PPU domains are ON:** AudioTop `0x0614a000`, `+0xc`; DSP
   status `0x06144000`.
5. **Only if TVTOP `+0x40` reads `00011111` (routed):** lock words
   `0x05001530`, `0x05001534`. These are read only; the peer word is never
   written, and nothing writes the own word in A–C.

## Procedure

**Cold cycle 1 — orderly warm reset.**

- **A1, cold catch.** Operator does a full disconnected cold cycle. The
  catcher stops autoboot. Run set U (cold preboot baseline), then `boot`.
- **A2, production session.** The normal cold branch runs: logo, source-3
  MIPS launch, GP6 latch set, HDMI services. Wait for active units. Confirm
  the journal's `0000/0000` → `1/1` lines for this boot ID, and DSP failure N.
  Run set L (cold-live baseline).
- **B1, orderly reboot.** Arm the catcher (it waits for the next SPL). Run
  `systemctl reboot`. Production teardown runs (signal restore, 22 DSP graph
  words and 15 TVFE restored, MIPS parked, receiver released), and the guard
  sees no HDMI owner, so it permits the reboot. Record the teardown log
  lines.
- **B2, warm catch.** Run set U (**warm preboot: the key measurement**), then
  `boot`.
- **B3, warm Linux.** The warm branch runs: GP6 set, temporary logo MIPS,
  park, no handoff, HDMI units skipped. Run set L (warm-parked).
- **End.** Orderly poweroff. No HDMI owner is loaded, so this is a normal
  poweroff.

**Cold cycle 2 — abrupt reset.** Repeat A1–A2. Then:
- **C1:** arm the catcher and trigger SysRq-b with the existing guarded
  trigger (`docs/hdmi-evidence/2026-10-20-reset-controls/abrupt-reset-trigger.py.txt`:
  sync, recheck boot ID/services/PCMs/DSP failure, drain a UART marker).
- **C2:** run set U.
- **C3:** run set L.
- **End:** poweroff.

Two cold cycles in total. All steps are read-only apart from the normal
production boot/teardown and the SysRq trigger.

## Interpreting phases A–C

| Warm preboot (U) | Reading | Next |
| --- | --- | --- |
| `0x070101ac` closed, or both TV PPU domains OFF | The warm reset reset the R domain or powered the TV domains down. **The DSP patch is very likely erased** (if the DSP's RAM is in those domains). | Phase D confirms with a version read in warm Linux. Expect `0/0`. |
| Both TV PPU domains ON | The TV domains were not power-cycled. **The patch may survive.** | Phase D reads versions. A `1/1` result means retained-state adoption is required. |
| PPU readable but mixed | Partial reset; record it. | Phase D, with the domain state recorded. |

Set L in the warm-parked state also answers:
- whether the lock is functional after the warm logo path (zeros versus
  all-ones), which phase D depends on;
- whether AudioTop and TVTOP keep their values.

## Phase D — warm version read (designed after A–C)

Only if phase A–C results justify it. A one-shot module, reusing the version
stage's claim / `0x80ff` pair / release code and its timeout handling. It is
gated on:
- a warm boot (GP6 non-zero) with no handoff, HDMI units inactive and MIPS
  parked;
- both PPU domains ON, TVTOP routed, AudioTop at the production baseline;
- lock words not `0x55` and observed readable.

It performs **no power, clock, reset, AudioTop or TVTOP transition**. If a
prerequisite is missing, it reports and stops rather than reconstructing it
(that reconstruction is a separate, later design). An expected `0/0` or `1/1`
answers the question directly. A timeout means the DSP is not responsive in
the warm-parked state, which is itself a recovery constraint.

## What this will not establish

- The cause of any retention, or which reset domain is responsible.
- Watchdog-expiry behaviour (SysRq-b is an emergency reset, not a watchdog).
- That a warm source-3 relaunch is safe. MIPS/GP6 policy is separate.
- Anything with an HDMI source change between boots. Keep the same source
  connected throughout.

## Implementation outline

1. Host runner: after the catcher stops autoboot, send set U with paced
   serial writes, capture the replies, refuse to continue if `bootcmd`
   differs from the recorded value, then send `boot`. It skips the PPU reads
   when `0x070101ac` is closed. It never sends anything other than `md.l`,
   `printenv` and `boot`.
2. Linux read-only collector extension: the existing collector plus set L
   with its ordering gates, as a script streamed over SSH. It does no writes.
3. Offline tests: the gating logic (PPU behind the gate, lock behind
   routing, AudioTop behind domains), refusal of any non-allowlisted U-Boot
   command, and boot-ID correlation.
4. Pre-flight: confirm the installed proper/SPL/BL31/env and production
   modules match the recorded manifests. Confirm a normal production boot is
   healthy before cold cycle 1 (the last normal boot was 2026-10-20).
