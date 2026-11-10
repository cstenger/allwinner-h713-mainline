# Phase A teardown — matched arm 2, October 22

**Every tested Phase A boundary preserved reported patched versions `1/1`.**
Classification `matched_tested_teardown_boundaries_preserved_patch` against
the [qualified sham](../2026-10-22-dsp-teardown-a-sham-live/README.md)
(canonical `8b6a068a…`). One matched trial; not a reset-retention result.

| Pair | Preceding operation (arm 2) | DSP 0 / DSP 1 |
| --- | --- | --- |
| 0 | Normal pinned patch/graph initialization | `1 / 1` |
| 1 | 22 saved graph words restored, reverse order (common prefix) | `1 / 1` |
| 2 | SPDI1 CTL0/CTL1 and AudIf mask restored to saved `0/0/0` | `1 / 1` |
| 3 | Bridge mask, global enable, stream START/END/BLOCK/CONFIG/FLUSH, SYNC, address-high restored to saved zeros | `1 / 1` |
| 4 | AudioTop config `011a5e00 → 0` (saved) | `1 / 1` |
| 5 | AudioTop control `700 → 0 → 700` | `1 / 1` |

All twelve responses `00000001`, statuses `00000120`; no echo, skip,
timeout or failure. Readbacks: census
`0, 3000, 300052, 0, 1, 6c6000, 6c6fff, 40, 2207, 0, 0, 70`, identical to the
sham's (same DMA `0x76c60000`); after SPDI `0,0,0` with bridge words
unchanged; after bridge all twelve words zero. Writes SPDI/bridge/AudioTop
`3/9/3`. Terminal: lock released, graph_remaining 0, AudioTop `700/0`,
IRQs disabled, IRQ objects/DMA/mappings/clocks/domains/receiver held.
No reset, clock removal, demod reset, MIPS park, warm logo or repatch.

**Interpretation.** With graph, SPDI, bridge and AudioTop teardown all
applied in normal order and every access clock held, the DSP still reports
the patch. The earlier post-shutdown zeros therefore lie in later brackets:
IHB/audio-clock + TVFE clock restoration and parent-hold release, demod
reset, terminal MIPS reset, receiver/domain release, or CPU reset/early
boot/warm logo — or an interaction of these with Phase A state. Next is
Phase B (clock round trip, then demod reset separately), which needs new
observation logic per the design before any hardware run.

## Identity

Cold catch OPEN 2026-10-23 00:03:33 UTC, one SPL, `gp6=gp7=0`, MIPS parked,
interrupt 00:03:53. The catch log bytes (`06b318be…`) are identical to the
2026-10-22 boundary run's: U-Boot output is deterministic and the log has no
timestamps; fresh event times and boot ID establish provenance. One cold
launch with source 3, re-latch, single handoff, production kernel. Boot
`835e0bf5-fc43-4269-9740-58d153feef99` (sham `7397c984…`). Same manifest,
module and script as the sham; staged sham bytes equal the exported sham.

## Evidence

Same layout as the sham directory; `validate.py` (repository root) →
`validation.json`, `matched-analysis.json`. Export 391,402 bytes, SHA-256
`4aa24e68dbe837d96e7b64ac33c39cf536ebbe99c7c5c100e10683d03aed41e9`, verified
before checked poweroff. UART: hold guard retained HDMI holds;
`reboot: Power down` at 223.11 s; recorder closed.
