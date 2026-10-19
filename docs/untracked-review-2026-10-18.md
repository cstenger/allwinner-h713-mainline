# Remaining untracked-file review — October 18, 2026

Snapshot after speaker-split commit `5baedcb`: **1,214 initially untracked,
non-ignored files**. Every file has a category, size and SHA-256 in the local
`build/untracked-review-2026-10-18/inventory.json`; that directory also contains
the original path list and one path list per category. Already-ignored build,
firmware and recovery material was outside this inventory.

This is a disposition review, not validation that the remaining tools are ready
for hardware use. No hardware access, source execution, file deletion or media
conversion was performed. The checks below parsed source without importing it.

| Disposition | Files | Bytes | Action |
| --- | ---: | ---: | --- |
| Generated kernel module outputs | 79 | 1,875,515 | Scoped `.gitignore` rules added |
| Raw bench audio/video | 76 | 400,863,310 | Scoped `.gitignore` rules added; retain local originals |
| Local research/drafts/snapshots | 48 | 1,562,087 | Keep local; exact paths listed in `local-research.txt` |
| Speaker calibration follow-up | 6 | 12,472 | Small independent source/evidence commit after review |
| Capture test-helper follow-up | 2 | 2,667 | Consolidate reusable checks and their prerequisites |
| Panel validation support follow-up | 17 | 319,231 | Curate supporting evidence for the committed result |
| Panel bench/history follow-ups | 433 | 7,492,958 | Separate tool cleanup from historical evidence |
| Audio diagnostics/history follow-ups | 553 | 3,777,392 | Split the dependent diagnostic chain into focused commits |

## Ignore rules applied

Module outputs are ignored only under `modules/`: objects, modules, generated
`.mod.c`/`.mod` files, hidden Kbuild command files, `Module.symvers`,
`modules.order`, and `.tmp_versions/`. Source files and Makefiles remain visible.
There is no global `*.cmd` or `*.log` rule: U-Boot command sources and diagnostic
logs may belong in Git.

Raw `.wav`, `.nv16` and `.mkv` files are ignored only under
`docs/hdmi-evidence/`. Keep their analysis, sample counts, checksums and generation
recipes in the eventual evidence commits. The derived October 18
`live-media/video-first-frame.png` remains a follow-up candidate; it is a buffer
image, not proof of an operator's view of the panel. Three older tracked WAVs
remain tracked; the new ignore rules do not change existing Git history.

`git check-ignore` against the original inventory confirms exactly 155 matches:
79 build outputs and 76 raw media files. None of the candidate source files,
logs, JSON summaries or figures in that snapshot were hidden.

## Suggested follow-up order

1. **Speaker calibration source and evidence (6 files).**
   `tools/hdmi/make-speaker-calibration.py` plus the five files in
   `docs/hdmi-evidence/2026-10-15-speaker-calibration/`. Review the level/timing
   claims and regenerate the WAV under `build/`. Preserve the distinction
   between recorded acoustic observations and estimated boot-time correlation.
   The original phone recording and derived audio stay local.

2. **Residual capture test helpers (2 files).**
   `docs/hdmi-evidence/2026-10-13-alsa-driver/attempt3/check-continuity.py` and
   `docs/hdmi-evidence/2026-10-13-managed-dsp/resource-owner-test.c`.
   Move reusable source to an appropriate tool/test location, retaining links
   to its original run. The continuity script currently discovers sibling WAVs
   and can emit an empty trial set if no files exist: make input/empty-input
   handling explicit. Its periodic-tone screen is not a general proof of
   capture continuity. The resource-owner test reserves an MMIO range without
   mapping it; preserve that distinction and provide build/run instructions.

3. **October 18 panel validation support (17 files).**
   The remaining non-media, non-bookkeeping files in
   `docs/hdmi-evidence/2026-10-18-panel-initial-state-trial/`: per-trial logs and
   status, trigger/capture/install/test scripts, command records and the PNG.
   Compare them with the already committed README/result records and
   [current runbook](uboot-panel-initial-state.md). Keep only evidence that
   supports an identified run; mark installation/trigger copies as historical
   records rather than general-purpose deployment tools. Do not count these
   files as additional hardware trials.

4. **Panel bench tooling, then historical investigation evidence (433 files).**
   Tools: `modules/hdmi-tvfe-bench/`, `modules/r-wdog-reboot-bench/`,
   `tools/hdmi/bench-receiver-only.py`, the four `tools/display/*trial.sh` /
   `rdomain-snapshot.sh` scripts, and `tools/serial/catch-uboot-warm-path.py`.
   Review ownership, terminal restoration, timeouts, and bench-only guards
   before committing reusable entry points. The serial catcher writes the
   RTC launch latch; the PL6 trial cuts the core rails; the watchdog module
   installs a restart handler. They are distinct hardware interventions.

   Correction from the October 19 tooling review: the TVFE bench `.c` and
   `.h` entries are relative symlinks to `modules/hdmi-audio/`, rather than
   copied source. The original hash inventory followed the links. The tooling
   cleanup tracks those symlinks and tests their targets, so the bench shares
   the production source without introducing duplicate contents.

   Archive the selected October 16/17 logs and the updated
   `docs/review-2026-10-17-panel-black-chatgpt.md` separately, with a short
   chronology and links to the final runbook. Earlier failed controls remain
   useful evidence but should not read as current instructions. The two older
   handoff/next-step drafts are local-only below.

5. **Older audio firmware diagnostics, in dependency order (553 files).**
   The 23 `tools/mips/` files and October 7 evidence form a dependency chain:
   monitor/readback/dispatch tracing, metadata retry/init, then PLL word-write
   and byte-read shims. Pair each layer's generator/reader/tests with its own
   profile and selected result/restoration evidence. October 8 audio-safety
   and rate-test records can follow as evidence commits after the tools they
   reference are present. Preserve failed/aborted outcomes and later
   corrections to earlier PLL/cache interpretations.

   Concrete blockers: `verify-audio-pll-word.py` and
   `verify-audio-pll-byte-read.py` load missing sibling files named
   `audio-pll-word-profile.json` and `audio-pll-byte-profile.json`. The generators
   instead emit `audio-monitor-profile.json` into the chosen output directory;
   matching historical profiles exist in their evidence directories. Make
   profile input/deployment explicit rather than copying unnamed state into
   the source tree. Tests also read private firmware and prebuilt `shim.bin`
   files: document inputs and generate shims from the `.S` sources.

   `install-audio-monitor-trace.py` is a withdrawn RAM installer: its CLI
   refuses before opening serial because the hardware attempt faulted on a
   read-only mapping. Retain it only as clearly disabled historical code/test
   material. Do not restore it as an active installation path.

## Keep local

The 48 entries in `local-research.txt` comprise:

- Two superseded drafts: `docs/handoff-2026-10-17-panel-black-for-chatgpt.md`
  and `docs/panel-black-root-cause-plan-2026-10-17.md`. Their current results
  belong in the existing panel runbook and curated chronology.
- Twenty-five generated `.asm` disassemblies. Keep selected necessary excerpts
  with the eventual diagnostic explanation, rather than committing the entire
  scratch collection by default.
- Six `tested-probe.c` / `tested-completion.h` snapshots from DSP completion
  experiments. Preserve them locally; use hashes/diffs for provenance where
  needed. The attempt-3 completion header is identical to the tracked
  `modules/hdmi-dsp-probe/h713-dsp-completion.h`.
- Two TVFE symlink entries originally classified as duplicates; see the
  October 19 correction above. They are promoted with the bench tooling.
- Ten serial byte-offset files and three aggregate capture/session logs.
  Retain them to map raw captures to the per-trial excerpts; commit the
  identified trial records instead.

These local-research files remain present and visible as untracked files.
No repository-wide ignore rule was added for drafts, source snapshots or
assembly. Their exact disposition is recorded so they are not mistaken for
unreviewed reusable source in a later blanket add.

## Checks and limits

All 78 untracked Python files parse, and all six untracked shell scripts pass
`sh -n`. Those are syntax checks, not imports, unit tests or hardware passes.
The two TVFE duplicates and the duplicate completion header were compared
byte-for-byte with their tracked counterparts. Every original file is hashed
in the local inventory. No follow-up sources or evidence have been staged or
committed as part of this review.

## October 19 audio tracing follow-up

The first audio group is now curated in
[audio-trace-diagnostics](audio-trace-diagnostics/README.md): monitor, RTT
readback and dispatch generators/readers/tests, with the RAM installer reduced
to an unconditional refusal and its prototype archived as text. Exact-image
candidate regeneration matches all three historical profiles and hashes.
The four October 7 baseline/trace directories have curated summaries,
non-executable script/notes snapshots and normalized logs with source/export
hashes. Their raw log/script originals and binary/media/disassembly inputs
remain local; see the manifest for dispositions. Later metadata retry/init,
PLL word/byte tools and October 8 evidence remain follow-ups. This cleanup
performed no hardware access.

## October 19 metadata retry / PLL initialization follow-up

The next audio group is curated in
[audio-pll-experiments](audio-pll-experiments/README.md): metadata retry and
init-on-zero generators/verifiers/tests, plus the supporting tracked stock
PLL model with explicit private input and mandatory identity checks. Both
candidates and complete profiles reproduce their historical identities.
The two October 7 evidence directories have curated summaries, exact text
script/notes snapshots, normalized logs and source/export hashes. The later
scalar-byte correction is retained; collapsed-byte-store and missing-upper-byte
hypotheses are withdrawn. PLL word-write/byte-read tools and October 8 records
remain follow-ups. No new hardware trials were performed.

## October 19 PLL access follow-up

The remaining MIPS PLL word-write/byte-read sources are curated in
[pll-access-experiments](pll-access-experiments/README.md). Shims build from
committed assembly in unique temporary directories and must match reviewed
hashes. Candidate guards use exceptions; verifiers take explicit profile paths
and authenticate all 96 records before opening device memory. Existing real
stock-epilogue/access-width tests now take explicit private firmware and build
fresh shims. Both historical candidates and full profiles reproduce exactly.
The two October 7 evidence directories have curated summaries, text-only script
snapshots, normalized logs and source/export hashes. The word-write DSP timeout
is not a valid capture result; the byte-read correction does not establish lock
or recovered PCM. All MIPS tool groups from this inventory are now handled.
Older October 8 audio safety/rate evidence remains a separate follow-up, and
raw sources/images/media/dumps/disassemblies remain local as documented.
No hardware was accessed in this cleanup.
