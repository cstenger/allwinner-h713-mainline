# Phase 1: our side of the stock comparison (10-23)

§10.21.3 Phase 1 of [the design](../../../hdmi-panel-source-design-2026-10-23.md).
Boot `34ee92bd…` (T4 cold path, `0188` identity map), host at 1280×720
on HDMI-A-1. Every read went through `display-sweep.py` (read-only
`/dev/mem`), streamed in over ssh stdin. The only board-side files were in
`/run/h713-sweep` (tmpfs), deleted after the pull.

| Sample | State | Board uptime | Selector | Gain | AFBD `0x10` | IOMMU `0x108` |
| --- | --- | --- | --- | --- | --- | --- |
| O1-a / O1-b | console, source 0 off (capture config from `win rn 2`) | 9013.0 / 9019.2 | `29000000` | `04000000` | `03000200` | 0 |
| O2-a / O2-b | T5 stage B (`--hold-b 60`, run `../phase1-o2/`) | 9068.4 / 9074.5 | `39000000` | `144C0000` | `03000203` | 0 |

* Each sweep: lists A (5504 words), A′ (188), B (272) and C (the MIPS
  image, 14 946 304 bytes; hashes in `mips-image.sha256`, the images
  themselves in `local/panel-source-t5/sweeps/`). A sweep takes about
  0.3 s on the board.
* T5 run: `ok`, no aborts. Stage B started ≈9064 and ended ≈9124, and both
  O2 sweeps fell inside it. Then the full revert (console, gain idle,
  `dis 4`).
* `diff-O1-O2.txt`: 5964 common words, 205 of them statistics (they
  differ between a state's own two samples), 49 CONFIG.
  * Beyond the expected selector, gain and AFBD source words, the full
    composition page shows words the older 1182-word set never read.
  * `comp+ac0–ad4` hold luma- and chroma-sized counts
    (`0xe100`/`0x38400` vs `0x70d0`/`0x1c360`). The chroma ones are about
    half the luma ones, which would fit 4:2:0 accounting at the
    composition input. That's a lead to compare against stock in
    Phase 3, not a conclusion.
* Node walker: every window-layer object found by vptr (NR `8b89bfc0`,
  Cap, Proc, Panel, MemoryAgent `8b89d37c`, frame buffers), with fields as
  in §10.16. No node field differs between O1 and O2.
