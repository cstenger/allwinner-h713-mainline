# Phase A teardown bench — sham (arm 1), October 22

**Sham qualified: all six version pairs `1/1`, no SPDI/bridge/AudioTop writes.**
Bench: [preparation](../2026-10-22-dsp-teardown-a-preparation/README.md).
This qualifies the new module, observation path and common graph prefix for
the matched teardown arm; by itself it attributes nothing to any boundary.

| Pair | Preceding operation (sham) | DSP 0 / DSP 1 |
| --- | --- | --- |
| 0 | Normal pinned patch/graph initialization | `1 / 1` |
| 1 | 22 saved graph words restored, reverse order (common prefix, real writes) | `1 / 1` |
| 2 | SPDI checkpoint: identical reads, no writes | `1 / 1` |
| 3 | Bridge checkpoint: identical reads, no writes | `1 / 1` |
| 4 | AudioTop config checkpoint: no write | `1 / 1` |
| 5 | AudioTop control checkpoint: no writes | `1 / 1` |

All twelve responses `00000001`, statuses `00000120`, phase 5, sent/outcome 1.
No echo, skip, timeout, hard failure or uncertain ledger. Terminal step 37:
lock released, graph_remaining 0, AudioTop `700/011a5e00`, write counters
SPDI/bridge/AudioTop `0/0/0`. Census = post-SPDI = post-bridge readback:
`0, 3000, 300052, 0, 1, 6c6000, 6c6fff, 40, 2207, 0, 0, 70` (stage 3, flags
31, DMA `0x76c60000`). All saved teardown words are zero; saved route 0;
AudioTop saved `0/0`. Arm 2 will therefore restore zeros, as normal
teardown does on this board.

## Identity

* Fresh cold catch: OPEN 23:50:25 UTC, one SPL, `gp6=gp7=0`, MIPS parked,
  one autoboot interrupt at 23:50:47 UTC. One cold launch: source 3, 720p
  re-latch, single handoff, production kernel `#1 SMP Fri Oct 16 15:44:49 PDT 2026`.
* Boot `7397c984-778a-455a-925d-44f060e5ad33`, distinct from earlier batches.
  Manifest `1950e8ee…`, module `cffa83e6…`, cold script `f92ed23f…`.
* Initial DSP `0/0` → pinned patch `1/1`. Guard and original backup verified.
* Canonical sham SHA-256 (sorted JSON + newline) of
  `board-export/snapshot-37.json`:
  `8b6a068ae306a9a90561147365a3a6ed92521fc95b26560099aaa2bc72e1e370`.

## Evidence

`cold-catch/`, `cold-boot/`: raw cold origin, transfer and boot UART.
`step-*.json`/`snapshot-*.json`: host records; `*.log`: raw SSH output
each was parsed from. `board-export/`: board snapshots, ledger,
initialization and final journal/state. `steps-uart.log`: sole reader from
before initialization to Power down (OPEN → CLOSE in events).
`run-steps.py`: the sequencer used (stop on first error, no retry).
`validate.py` (run from repository root) → `validation.json`: classifier,
host = board state, ordered 37 BEGIN/DONE, 12 complete requests, 22 graph
restores, no SPDI/bridge restore lines, no failure/timeout/skip, single cold
handoff, initial zero then patch, verified export.

Export 388,825 bytes, SHA-256
`4f4678b740f9c5b9f2f4339e4efc6d510b239469a00cead16b064e0d2e877c49`, verified
on host before checked poweroff. UART: hold guard retained HDMI holds;
`reboot: Power down` at 246.17 s. Recorder closed. Next: matched teardown
arm on a separate fully unplugged cold cycle.
