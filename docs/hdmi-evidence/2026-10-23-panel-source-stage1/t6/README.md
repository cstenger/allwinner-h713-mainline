# T6: the selector flip with NR's history on (10-23)

T6 from §10.16 of [the design](../../../hdmi-panel-source-design-2026-10-23.md):
T5 plus `memory_agent en 5/6` (NR temporal-NR history DMA) before agent 4.

## Setup

* Boot `34ee92bd-95ac-46cd-a066-628f389ad507` (T4 cold path, `0188` pool
  identity map).
* `t5-board.py --with-nr` (sha256 in `board-script.sha256`), run as the unit
  `h713-t5`. All 11 preconditions passed, including the NR history
  addresses equal to stock and the history off.
* Operator: the same test chart full-screen on HDMI-A-1, filming.
* `events.jsonl` also holds the earlier T5 run (same unit name);
  `events-t6.jsonl` is this run alone. The host runner now collects with
  `--since`.

## Register record (`events-t6.jsonl`)

| Board time (s) | Step | NR enables (`178 1b8 278 2b8`) | selector | gain | AFBD `0x10` | IOMMU | TCON | faults |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5821.75 | pre | `6… 6… 6… 6…` (off) | `29000000` | `04000000` | `03000200` | 0 | 720p | 0 |
| 5824.02 / 5826.30 | `en 5`, `en 6` | | | | | | | |
| 5826.84 | nr-on | **`e0020168 e00202d0 e0020168 e00202d0`** | `29000000` | `04000000` | `03000200` | 0 | 720p | 0 |
| 5829.17 | `en 4` | | | | | | | |
| 5832.23 | en4 | on | `29000000` | `04000000` | `03000203` | 0 | 720p | 0 |
| 5832.26 | **stage A**: selector → `39000000` | | | | | | | |
| 5847.47 | held 15 s | on | `39000000` | `04000000` | `03000203` | 0 | 720p | 0 |
| 5847.51 | **stage B**: gain → `144c0000` | | | | | | | |
| 5862.76 | held 15 s | on | `39000000` | `144c0000` | `03000203` | 0 | 720p | 0 |
| 5862.80 | revert: gain, selector | | | | | | | |
| 5865.09–5869.65 | `dis 4`, `dis 6`, `dis 5` | | | | | | | |
| 5869.69 | reverted | `6… 6… 6… 6…` (off) | `29000000` | `04000000` | `03000200` | 0 | 720p | 0 |

No abort; `done ok`.

## Operator observation

* "I didn't notice any change in the colour version from the previous run."
  Stage B looked the same as T5: chroma at half the vertical rate.
* **Result: H1 (NR history needed) is out.** Turning on the stock agents
  5/6 neither fixes nor changes the chroma. It's also harmless: no faults,
  and no visible artefact was reported.
