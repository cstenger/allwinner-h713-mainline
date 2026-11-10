# Phase A teardown bench — preparation (Claude, October 22)

**Offline only. No board access, staging, capture or power request.**
Implements Phase A of the
[remaining teardown design](../../hdmi-dsp-remaining-teardown-design-2026-10-22.md):
normal-order graph → SPDI1 → Audio Bridge → AudioTop teardown, with
every access clock, domain, IRQ object, mapping and DMA buffer held by the
sole pinned owner. No reset, clock removal or warm logo after patching.

Candidate: `build/hdmi-dsp-teardown-a-2026-10-22/candidate/` (new directory;
the qualified `hdmi-dsp-owner-boundary-2026-10-22/candidate/` is untouched).
[Manifest](manifest.json), [verification](verification.json),
[build log](build.log), [tests](tests-summary.json),
[cold script](cold-teardown.cmd), [PCM patch](h713-hdmi-pcm.c.patch),
[DSP patch](h713-hdmi-dsp.c.patch).

## Plan (37 one-shot steps, 6 version pairs, at most 12 requests)

| Steps | Operation | Sham (arm 1) | Teardown (arm 2) |
| --- | --- | --- | --- |
| 1 | Census: 12 SPDI/bridge words, stage 3, flags, DMA | same reads | same reads |
| 2–6 | Pair 0 (positive control, must be `1/1`) | | |
| 7 | 22 saved graph words, reverse order | **writes (common prefix)** | **writes (common prefix)** |
| 8–12 | Pair 1 | | |
| 13 | SPDI1 CTL0, CTL1, AudIf mask (saved values) | reads only | writes + readback |
| 14–18 | Pair 2 | | |
| 19 | Bridge mask, global, START/END/BLOCK/CONFIG/FLUSH, SYNC, addr-high | reads only | writes + readback |
| 20–24 | Pair 3 | | |
| 25 | AudioTop saved config (0) | none | write |
| 26–30 | Pair 4 | | |
| 31–32 | AudioTop saved control (0), then `700` | none | writes; no AudIf/bridge/DSP access while off |
| 33–37 | Pair 5 | | |

Each pair is claim → device 0 → device 1 → release → checkpoint. A changed,
echoed or timed-out pair is terminal at its checkpoint: no later operation
is admitted by the kernel. Both arms perform identical reads and settling
waits; only arm 2 writes SPDI/bridge/AudioTop. Arm-2 restore is refused
unless the current 12 words equal the step-1 census (no drift), and every
written word must read back exactly; mismatch is a hard failure with no
rollback/retry. Never written: `audif_saved_route`, AudIf/bridge W1C status,
the stage-4 flush pulse. IRQs stay disabled; no `free_irq`, DMA free or
unmap.

Kernel state (`owner_state`, schema `h713-teardown-a-v1`) adds the plan,
request count, saved values, census and post-SPDI/post-bridge readbacks,
write counters and applied flags. It is built from cached values only, so
reading it while AudioTop control is off touches no MMIO.

## Host gating

`dsp-teardown-a.py` (board) keeps the proven ledger/proof/export model with
a new schema, DT marker `h713,dsp-teardown-a-v1 = 0x54445241` and bootarg
`h713_teardown_a=1`. It requires a snapshot acknowledgment by stage name
after every claim, device-0 request, checkpoint and intervention. Arm 2
additionally requires the exact qualified new-schema sham (other boot,
same manifest, canonical hash), matching baseline reads, graph words, plan
and saved values at initialization; census equal to the sham's before
step 2 (only allocator DMA words may differ); and a patched common-prefix
pair 1 before step 13. The old `h713-owner-boundary-v1` sham is rejected.

`analyze-dsp-teardown-a.py` classifies each boundary separately
(`version_change_after_{common_graph_restore,spdi_restore,bridge_restore,audiotop_config_restore,audiotop_control_cycle}`,
`tested_teardown_boundaries_preserved_patch`), never treating a timeout or
`80ff0000` echo as a zero. `compare()` gives `matched_*` only for an exact,
distinct qualified sham; DMA addresses may differ only consistently.

`tools/hdmi/dsp-teardown-a-host.py --run <dir>` performs each host action
once (health-stage, initialize, uart, step/snapshot, export, poweroff), with
fixed 20 s / 60 s deadlines that record an uncertain log and never retry.
`tools/serial/run-dsp-teardown-cold.py` is the proven owner cold runner
with the new script and schema.

## Verification

* W=1 build against unchanged production kernel/config/Image/Symvers: zero C
  diagnostics (only the known clang 23.1.1 vs 23.1.3 Kbuild notice).
  Vermagic `6.18.38 SMP mod_unload aarch64` matches. No new undefined
  symbols versus the qualified owner module; no exports.
* Module `cffa83e665594461e20fcfe8fb142ecd4ac14d0386b501f6adca1ff3f2394419`,
  build-ID note `1f909fb6…`. Cold script 4,355 bytes,
  `sha256` in manifest; legacy header/data CRC and payload verified; differs
  from the qualified owner script only in marker, bootarg and refusal echo.
* 26 new tests: all 25 native modes run the real includes on fake MMIO
  (which aborts on any AudIf/bridge/DSP/lock access while control is off);
  analyzer cases use the actual C state output. 13 mutations were caught;
  two checks are documented as redundant defense. 43 regressions pass
  (owner-boundary 14, startup 11, managed boot 7, minimum 11).

No live claim. The new sham must qualify this module before arm 2.
