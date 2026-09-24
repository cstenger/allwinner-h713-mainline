# Documentation index

115 files, ~50,000 lines, and until now no way in except `grep`. This is the
map. It is deliberately short: if a summary here grows past one line, the
detail belongs in the file it points at.

**Three things to know before reading anything else.**

1. **Most files are dated snapshots, not current truth.** A handoff or a
   `reference/` note records what was believed on the day it was written.
   Several were later falsified — by design, because the corrections are the
   useful part. Check §4 before trusting an old conclusion.
2. **The "closed" list in §3 is the highest-value section.** Each entry cost at
   least a session to establish. Re-opening one without new evidence is the
   single most expensive mistake available in this project.
3. **Where two files disagree, the one named in §2 wins.**

---

## 1. Start here

| file | what it is |
| --- | --- |
| [`status.md`](status.md) | What works today, per subsystem. The front page. |
| [`roadmap.md`](roadmap.md) | What comes next, ordered by dependency. |
| [`build.md`](build.md) · [`flash.md`](flash.md) | Build the firmware; write it to a board. |
| [`board-bringup-sequence.md`](board-bringup-sequence.md) | What runs in what order, boot to Debian. |
| [`bringup-notes.md`](bringup-notes.md) | Distilled lessons from U-Boot/TF-A/Linux bring-up. |

## 2. Current answers, by subsystem

These are the authorities. Prefer them over anything dated.

| subsystem | file | one-line state |
| --- | --- | --- |
| Video decode | [`video-decode.md`](video-decode.md) | H.264, HEVC, MPEG-2, VP8 all decode bit-exact on the VE. |
| Decode hardening | [`decode-production-readiness.md`](decode-production-readiness.md) | Soak, robustness, concurrency — what each gate is for. |
| 10-bit HEVC | [`hevc-10bit-findings.md`](hevc-10bit-findings.md) | Bit-exact internally; 8-bit output is the shipping behaviour **by decision**. |
| VA-API / players | [`vaapi-scope.md`](vaapi-scope.md) | What stock ffmpeg/mpv need to use the VE. Opening summary is annotated where stale. |
| KMS / panel | [`kms-display.md`](kms-display.md) | The DRM driver for the 1280x720 LVDS panel. |
| Display bring-up | [`claude-display-handoff.md`](claude-display-handoff.md) · [`mips-display-recovery.md`](mips-display-recovery.md) | The MIPS coprocessor path. `mips-display-recovery.md` is 7,900 lines — the deepest file here. |
| IOMMU | [`iommu-port.md`](iommu-port.md) | Real, at `0x2010000`; VE needs both master ports. |
| Audio | [`audio.md`](audio.md) | Playback works; speaker is on the headphone amp. |
| Backlight | [`backlight-investigation.md`](backlight-investigation.md) | Dimming is PWM-of-enable at PB5, not PB4. |
| WiFi | [`wifi-failure-2026-08-17.md`](wifi-failure-2026-08-17.md) | The "cannot carry a file" failure, characterised and fixed. |
| HDMI input | [`hdmi-in.md`](hdmi-in.md) | Blocked on HPD at an address that hard-locks the SoC. |
| Rootfs / boot | [`rootfs.md`](rootfs.md) · [`standalone-boot.md`](standalone-boot.md) · [`kernel-bump.md`](kernel-bump.md) | Debian 13 arm64, power-on to login, no host. |

## 3. Closed — do not reopen without new evidence

Each of these was expensive to establish. The reason is given so it can be
argued with, not just obeyed.

| question | answer | where |
| --- | --- | --- |
| Use GE2D as a 2D engine? | **No — it is the projector's display controller, not a blitter.** Zero scale/blit symbols. Re-proposed twice and re-killed twice. | [`kms-display.md`](kms-display.md), `status.md` |
| Get P010 out of the VE's second output? | **No.** All four `SECOND_OUT_FMT` arms byte-identical with the output armed and writing, against a positive control. | [`hevc-10bit-findings.md`](hevc-10bit-findings.md) §3 |
| Add a V4L2 fourcc for 10-bit output? | **Deliberately not pursued.** No fourcc describes 8+2 *and* the panel is 8-bit — either alone caps the result. | [`hevc-10bit-findings.md`](hevc-10bit-findings.md) §4 |
| Downscale in the display pipeline? | **No downscaler exists.** Census complete: exactly three ratio-carrying blocks, all ruled out. | [`reference/scaler-census-2026-09-11.md`](reference/scaler-census-2026-09-11.md) |
| Drive the CE crypto engine? | **No.** Descriptor format differs from mainline's; zero payoff (A53 SW crypto is faster). | ⚠ **not written up in `docs/`** — this conclusion exists only in project memory |
| Send frames to the MIPS over CPU_COMM? | **No.** The frame-submit routines are verified stubs. | [`reference/cpu-comm-call-table.md`](reference/cpu-comm-call-table.md) |

**Hardware hazards, same category:** a plain *read* of `0x07091000` wedges the
SoC (power cycle only); never hold PB5 low for long (shared with fan power);
warm reboots kill the display — power-cycle between display tests.

## 3a. Looking up an address

[`register-index.md`](register-index.md) — **start here for any `0x…`**, before
grepping. Hazards first (two of them cost a power cycle or a board), then every
catalogued register with its meaning, known values, confidence, and the document
that justifies it.

It is **generated** from [`re/registers.yaml`](re/registers.yaml), which is the
source of truth for addresses. Narrative stays in the journals; facts live there
once. Add a register by editing the YAML and running
`tools/docs/gen-register-index.py`; `--check` fails if the markdown has drifted.

Its last section lists addresses the docs discuss in three or more files that
nothing has yet defined — that is the backlog, and it is recomputed every run.

## 4. Corrections — claims that were wrong

This project has a habit of recording falsified claims rather than deleting
them, because the failure modes repeat. The two collections worth reading
before trusting an old document:

- [`handoff-2026-08-24.md`](handoff-2026-08-24.md) §5 "Claims retired, with
  their evidence" and §7 "How the eight retired claims died — all the same
  way". The §7 framing is the more useful half: the mechanism repeats.
- [`reference/hevc-unaligned-chroma-2026-09-23.md`](reference/hevc-unaligned-chroma-2026-09-23.md) —
  a defect found *and* two of its own hypotheses falsified in sequence; kept
  because the elimination order is the instructive part.

## 5. Handoffs — dated snapshots, newest first

Session-end summaries. **Each is superseded by the ones after it**; they are
kept for the reasoning, not the conclusions. If you only read one, read the
newest in the area you care about.

- **Video / scaler:** `2026-09-23-retire-display-scaling`, `2026-09-17-scaled-playback`,
  `2026-09-17-shared-scaler`, `2026-09-16-h265-scaler`,
  `2026-09-15-compliance-and-upstream`, `2026-09-14-video-scaler-and-rotation`,
  `2026-09-12-driver-on-hardware`, `2026-09-12-ve-scaledown`,
  `2026-09-08-video-playing`, `2026-09-04-video-scaling-and-display`,
  `2026-09-03-video-playback`, `2026-09-03-video-decode`, `2026-08-24`
- **Display / MIPS:** `2026-09-08-mips-callback-trace`, `2026-09-06-composition-block`,
  `2026-09-04-mips-window-layer`, `2026-09-01-decd-kms-shape`,
  `2026-09-01-iommu-runtime`, `2026-08-31`, `2026-08-30`, `2026-08-29`,
  `2026-08-25`, `2026-08-24-display`
- **Other:** `2026-09-02-audio-hdmi`, `2026-09-02`, `2026-08-22`, `2026-08-17`,
  `wifi-sdio-2026-08-17`

## 6. `reference/` — single-experiment records

58 files, each a dated write-up of one experiment: what was run, what came out,
what it does and does not prove. They are primary evidence, not narrative, and
most are superseded by the subsystem doc in §2. Grouped by arc:

- **Scaler investigation** (~20 files, `scaler-*`, `two-axis-scaler-*`,
  `composition-*`, `proc-scaler-*`, `ve-decode-time-scaledown-*`,
  `ve-input-crop-*`) — resolved; the answer lives in §2's video docs.
- **DECD / scanout** (`decd-*`, `nv12-scanout-*`, `linux-decd-*`,
  `afbd-*`, `colour-*`, `lvds-*`) — resolved; video reaches the panel.
- **MIPS / firmware RE** (`mips-*`, `viddec-*`, `vp-init-*`, `videoinfo-*`,
  `event8-*`, `dispatch-trace-*`, `firmware-*`, `cpu-comm-*`).
- **Codec / uAPI** (`hevc-unaligned-chroma-*`, `inherited-codecs-*`,
  `h265-*`, `chroma-422-*`, `v4l2-compliance-*`, `upstream-survey-*`).

---

*Adding a document? Put a line here. An index nobody updates is worse than no
index, because it silently misrepresents what exists.*
