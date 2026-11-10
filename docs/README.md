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
| [`First HDMI advert: cause and event-driven fix — November 8`](hdmi-first-advert-root-cause-2026-11-08.md) | Source reads EDID but our slave NAKs until an HPD edge; SCP DDC-line watch + failed-read pulse (`hpd-event-v1`): lock owner +2.12 s; qualification table; AFBD green stall closed as a rare known limit (1/9 boots). |
| [`Claude board-completion handoff — November 6`](handoff-2026-11-06-claude-board-completion.md) | Current live/disk state, single-launch and EDID/DDC boot work, retry evidence, remaining optimization and DDR3 completion gates before LPDDR3. |
| [`Early HDMI boot review — November 6`](hdmi-early-boot-review-2026-11-06.md) | U-Boot's two firmware launches, resource ordering, stock comparison and prepared-only observation checkpoints. |
| [`Rebuilt-candidate hardware qualification`](production-evidence/2026-11-03-candidate-installation/README.md) | Exact install/readback, boot/HDMI/decoder/control checks and non-writing recovery entry; tested scope and GF1 disposition recorded. |
| [`Guarded frame-discard disposition`](production-evidence/2026-11-04-guarded-discard-disposition/README.md) | Reviewed protective drop; actual-source race/guard-bypass tests, strict failure retained, unchanged installed binary. |
| [`Exact installation/rollback packet`](production-evidence/2026-11-03-installation-packet/README.md) | Sealed bounded installation/rollback inputs and protected readback; preparation record, with live results below. |
| [`Offline rollback backup`](production-evidence/2026-11-03-offline-backup/README.md) | Two complete direct eMMC reads match; Linux/files/pins verify; existing boot FAT inconsistencies preserved; no installation or repartitioning. |
| [`Production reproducibility result`](production-evidence/2026-11-03-reproducible-build/README.md) | Two complete source builds produce identical boot/firmware/rootfs bytes; production test payloads excluded. |
| [`Rebuilding the production system`](reproducible-production.md) | Source-built candidate workflow, pinned private inputs and production image contents; hardware qualification remains required. |
| [`Rebuilt-system qualification plan`](production-qualification-plan.md) | Backup, exact installation scope and hardware acceptance gates for the DDR3 board. |
| [`HDMI final regression checks`](hdmi-evidence/2026-11-02-hdmi-regressions/README.md) | Host reboot, 3 h 38 min input session and functional physical reconnect pass; exact reconnect latency unmeasured. |
| [`U-Boot native save-path validation`](hdmi-evidence/2026-11-02-uboot-savepath/README.md) | PASS: corrected-slot native save, marker reload and cleanup; protected storage and 59 file checks pass. |
| [`Claude HDMI second-opinion handoff`](handoff-2026-11-01-hdmi-detection-for-claude.md) | Current evidence/code map, both cold controls passed, latest unrecorded abrupt cycle, review questions and live-work constraints. Offline review first. |
| [`HDMI zero-control cold validation`](hdmi-evidence/2026-11-01-zero-control-cold/README.md) | 0 ms cold control also passed: correct EDID, 720p lock, host desktop and healthy Linux. Both delay conditions passed once; two-second causal benefit unproven. Recordings sealed; zero override remains installed. |
| [`HDMI matched zero-control staging`](hdmi-evidence/2026-11-01-zero-control-stage/README.md) | 0 ms control staged with verified backups; only the delay argument changed. Running two-second boot untouched; no reload, restart, shutdown or reboot. |
| [`HDMI delayed cold-start validation`](hdmi-evidence/2026-11-01-startup-delay-cold/README.md) | Passed one power-off startup: measured 2.0217 s wait, expected host EDID, 720p lock, normal desktop/Linux and 56 pins/ten storage regions verified. Recordings sealed; staging subsequently switched to matched 0 ms control. |
| [`HDMI delayed warm-boot validation`](hdmi-evidence/2026-11-01-startup-delay-boot/README.md) | One ordinary reboot passed: measured 2.021 s wait, matching host EDID, 720p lock, normal desktop and Linux. Recorders stopped; temporary override remains installed. |
| [`HDMI delay startup staging`](hdmi-evidence/2026-11-01-startup-delay-stage/README.md) | 2,000 ms variant staged for next boot with verified backups; 56 production pins and ten storage regions pass before/after. No reload, restart or reboot. |
| [`HDMI delay-only startup package`](hdmi-evidence/2026-11-01-startup-delay/README.md) | Temporary 2,000 ms variant and matched control prepared; 55 offline tests, six mutation checks and both unit checks pass. Offline preparation record. |
| [`HDMI startup timing comparison`](hdmi-startup-timing-analysis-2026-11-01.md) | Known-good startup has nearly identical readiness timing; propose a controlled delay-only board startup test. No live changes. |
| [`Board boot HDMI recheck`](hdmi-evidence/2026-11-01-board-boot/README.md) | No-detection reproduced on fresh boot; UART/environment/startup/56 pins pass. Board on, no recovery attempted. |
| [`NVIDIA live attempt`](hdmi-evidence/2026-11-01-nvidia-cache-live/README.md) | Device allocation denied; own client freed, no display snapshot. Control-only lifecycle is not viable; no retry. |
| [`NVIDIA cached reader v2`](nvidia-cache-reader-2026-10-31.md) | Real transport prepared/tested; no live ioctl. Board powered off; old preserved HDMI/SCP session ended. |
| [`Live SCP analysis`](hdmi-scp-capture-analysis-2026-10-31.md) | Sampled controls match handoff; active EDID zeros also occur with successful detection. Next: audit host cache-only hotplug reader. |
| [`Guarded SCP capture`](hdmi-evidence/2026-10-31-scp-capture-live/README.md) | One live capture passes; current bad state unchanged, owner lock/guard/scratch retained. Do not rerun or unload. |
| [`SCP sampler v2`](hdmi-evidence/2026-10-31-scp-capture-v2/README.md) | Replacement qualified offline and packaged for a guarded capture; unloaded, current bad state unchanged. |
| [`SCP sampling safety review`](hdmi-evidence/2026-10-31-scp-capture-safety/README.md) | First probe fails live safety gates; bad state preserved, no insertion/reset/restart. |
| [`uboot-savepath-validation-2026-10-31.md`](uboot-savepath-validation-2026-10-31.md) | Fresh preflight held for no HDMI detection; bad state preserved for software diagnosis. UART unarmed, no save/reboot. |
| [`uboot-environment-migration-2026-10-30.md`](uboot-environment-migration-2026-10-30.md) | Latest cleanup: cold and one ordinary warm boot pass corrected environment load/Linux checks; desktop return confirmed. |
| [`handoff-2026-10-30-guard-sync.md`](handoff-2026-10-30-guard-sync.md) | Shutdown guards synchronized; both copies and full manifest verified. |
| [`handoff-2026-10-28-production-cleanup.md`](handoff-2026-10-28-production-cleanup.md) | Latest shutdown checkpoint: production audit, recovery files and next work. |
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
| Decode VP9 in hardware? | **No — the silicon is not on this part.** H6 has 8 VP9 clocks in its CCU; the H713 has zero and an AV1 block instead. Mainline's `sun50i-h6-vpu-g2` driver binds clocks that do not exist here. | [`reference/vp9-av1-codec-scouting-2026-09-24.md`](reference/vp9-av1-codec-scouting-2026-09-24.md) |

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

- **Video / scaler:** `2026-09-27-hdmi-lessons-for-video-decode`,
  `2026-09-23-retire-display-scaling`, `2026-09-17-scaled-playback`,
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

59 files plus 15 directories, each a dated write-up of one experiment: what was run, what came out,
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
- **Codec scouting** (`vp9-av1-codec-scouting-*`) — which codecs this part
  actually has silicon for. VP9 closed (absent); AV1 identified as Google IP
  (`allwinner,sunxi-google-ve`) with no driver in any tree.

---

*Adding a document? Put a line here. An index nobody updates is worse than no
index, because it silently misrepresents what exists.*
