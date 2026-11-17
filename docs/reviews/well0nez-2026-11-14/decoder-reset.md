# Coupled decoder reset (0298, 0305–0308) — November 16, 2026

**Status: the 0298 failure reproduces on our tree. A `RST_BUS_VE3`-only
pulse at a codec switch fixes it in a diagnostic module, and AV1 decodes
bit-exact beside 5064 such pulses. Kernel **0210** carries the VE3-only
reset. It is installed and qualified on the bench.**

## Assessment

well0nez's group fixes three things:

- **0298:** VP9 leaves state in the shared H.265 engine, so concurrent
  VP9+H.265 decoding fails. Their fix is a `RST_BUS_VE` pulse at every
  codec switch.
- **0305–0307:** that bus pulse, landing while an AV1 frame is in flight,
  stalls the AV1 core and then the SoC. They add a hold/pulse guard, about
  430 lines, which forces the pulse anyway after 3 s.
- **0308:** releasing the VE's IOMMU ports next to AV1 also stalls it, so
  they skip that recovery while an AV1 stream is open. 0310 then disables
  AV1.

How this maps onto our tree (0209 release, boot `2cfc0d6c`):

- **Sequential streams are clean.** `cedrus_stop_streaming()` drops the
  runtime-PM reference with a plain `pm_runtime_put()`, so the VE suspends
  and is reset between back-to-back streams. Both failures need concurrent
  decode: two cedrus streams, or cedrus beside AV1. While an AV1 stream is
  open, its runtime-PM device link keeps the VE active, so sequential cedrus
  streams then skip that reset too.
- **Our concurrency gate never covered this.**
  [decode-concurrency-test.sh](../../../tools/video/decode-concurrency-test.sh)
  pools H.264, H.265 8/10-bit and MPEG-2 only. VP9 (0143), VP8 and AV1
  have never been decoded concurrently with another codec.
- **We already carry the AV1 hazard, in a rare form.** `cedrus_watchdog()`
  pulses `RST_BUS_VE` and calls `sun50i_iommu_reset_masters()` (0158) with
  no AV1 interlock. That is reachable only when a cedrus job times out
  while an AV1 frame is in flight.
- **0298 alone would make the hazard routine.** It adds a bus pulse to
  valid-stream operation, so any codec switch beside AV1 would trigger it.
  It must not land on its own.
- **A narrower candidate exists.** Our VE has a second reset,
  `RST_BUS_VE3` (CCU `0x69c` bit 18), which the AV1 node does not name. If
  a VE3-only pulse at a codec switch clears VP9's residue, it fixes 0298's
  failure without touching the line AV1 depends on. Untested.

## Reproduction

[`tools/video/decode-codec-pair-test.py`](../../../tools/video/decode-codec-pair-test.py)
decodes the pinned vectors (`/root/kernel-followups-20261114/vectors`, with
manifest software references) through stock GStreamer
`v4l2slvp9dec`/`v4l2slh265dec`. It hashes NV12 straight from a pipe and
records VE interrupts and new kernel lines per phase.

Boot `2cfc0d6c-17d6-44db-a5cf-874770f7a947`, cedrus module `1c8c87ba…`
(0209 production). The HDMI-in display pipeline was running; it does not use
cedrus.

| Phase | Result | VE IRQs | Kernel lines |
| --- | --- | ---: | --- |
| VP9 alone (300 frames) | exact | 308 | none |
| H.265 alone (300 frames) | exact | 300 | none |
| H.265 + H.265 at once | both exact | 325 | none |
| VP9 + H.265, round 0 | VP9 exact, **H.265 wrong** | 308 | `Failed to setup decoding job: -22` |
| short VP9 + short H.265, round 0 | VP9 exact, **H.265 wrong** | 52 | same |
| VP9 + H.265, round 1 | VP9 exact, **H.265 wrong** | 311 | same |
| short VP9 + short H.265, round 1 | VP9 exact, **H.265 wrong** | 52 | same |
| H.265 alone afterwards | exact | 300 | none |
| VP9 alone afterwards | exact | 308 | none |

- **4 of 4 pair runs fail, exactly as well0nez reported.**
- In each failing pair, H.265 delivers the full byte count with exit status
  0, but none of its frames is decoded: the pair's VE interrupt count equals
  VP9's alone, and the kernel logs a setup `-EINVAL` per job (639 this
  boot). The wrong frames are distinct, non-zero stale buffer contents.
- There are no timeouts or IOMMU faults, and single streams afterwards are
  exact. So this concurrency failure is contained: it is not a VE wedge and
  carries no SoC risk.

Raw evidence (SHA-256): `repro-results.json` `b72fffec…`, `repro.log`
`d21953dc…`, in `local/recovery/2026-11-16-decoder-reset/`.

## Codec-switch reset arms (diagnostic module)

A diagnostic cedrus (`switch-reset-diagnostic.patch`, not in the series),
built out of tree from the 0209 release sources with matching vermagic,
adds a runtime `switch_reset` parameter to `cedrus_device_run()`. When a job's
codec differs from the previous job's, it pulses:

- `0`: nothing;
- `1`: `RST_BUS_VE3` only;
- `2`: `RST_BUS_VE`, as in 0298.

The pulse happens before any of that job's register writes. m2m serializes
jobs, so the engine is idle at that point. A `switch_pulses` counter
records the pulses.

**Setup.** Loading it required unloading production cedrus. The driver core
then unbound `hantro-vpu` from `1c0d000.av1` through the VE device link, so
**AV1 was absent for all three arms**. Boot `2cfc0d6c`, diagnostic module
`517c9c63…`. Each arm ran the same pair test as the reproduction, two rounds.

| Arm | VP9+H.265 pairs | VE IRQs, long pair | Pulses | Long pair time | Kernel errors |
| --- | --- | ---: | ---: | ---: | --- |
| 0, none | H.265 wrong, 4/4 | 310–312 | 0 | 13.6–13.8 s | setup `-EINVAL` |
| **1, VE3 only** | **all exact, 4/4** | 608 | 1034 | 12.0–12.1 s | none |
| 2, VE (0298) | all exact, 4/4 | 608 | 1036 | 12.1 s | none |

- **Unaffected phases.** In every arm the single-stream controls (about
  10.8 s each), the H.265+H.265 control and the recovery singles were
  exact. There were zero timeouts and zero IOMMU faults for the whole run.
- **Arm 0 noise.** Arm 0's recovery H.265 phase lists 12 kernel lines; the
  previous pair's errors fall inside its one-second journal window, and the
  decode itself was exact.
- **Cost.** About 1000 pulses over the four pairs cost nothing measurable;
  the failing pairs were slower than the fixed ones.
- **No side effects.** HDMI capture stayed `RUNNING`, and the system
  stayed `running` with no reset or oops lines.
- **Restored.** A reboot restored production: boot `a88c5e28`, startup
  PASS, production cedrus `1c8c87ba…` without the diagnostic parameters,
  AV1 bound again, clean capture teardown.

**What this shows.** VP9's leftover state lives behind `RST_BUS_VE3`, the
reset our DT gives cedrus alone. A VE3-only pulse is as effective as 0298's
full bus pulse for this failure.

**What it does not show yet:**

- whether the AV1 core is truly independent of `RST_BUS_VE3`;
- other codec pairs (H.264, MPEG-2, VP8). The board's pinned vector set is
  H.265/VP9 only, and VP8 pairing was one of well0nez's passing cases.

Evidence (SHA-256, `local/recovery/2026-11-16-decoder-reset/`):

| File | Digest |
| --- | --- |
| `diag/switch-reset-diagnostic.patch` | `14e59348…` |
| `arms/arms.log` | `49889f9c…` |
| `arms/arm0.json` | `96021f13…` |
| `arms/arm1.json` | `b3253b4f…` |
| `arms/arm2.json` | `b750b22f…` |

## AV1 beside VE3 codec-switch resets

Boot `a88c5e28`, with the UART logged. The run unloaded `hantro_vpu` and
production cedrus, loaded the diagnostic cedrus with `switch_reset=1`, and
reloaded `hantro_vpu`, so `1c0d000.av1` was **bound** again. AV1 was scored
by `av1-gate.sh` against host libdav1d per-frame MD5s; cedrus by the pair
runner's software references. Any AV1 failure stopped the run.

| Phase | AV1 | Cedrus | VE3 pulses | AV1 kernel errors |
| --- | --- | --- | ---: | --- |
| AV1 alone (720p stock, 1080p, error-resilient, film grain) | 4/4 exact | — | 0 | none |
| AV1 ×20 beside H.265+H.265 (no switches, 62 s) | 20/20 exact | 20/20 exact | 0 | none |
| **AV1 ×40 beside VP9+H.265 switching (138 s)** | **40/40 exact** (36 × 720p, 4 × 1080p) | **40/40 exact** | **5064** | none |
| AV1 alone afterwards | exact | — | — | none |

- There were zero timeouts or faults for the whole run. A reboot restored
  production cleanly: boot `53018056`, startup PASS, production cedrus, AV1
  bound, `reboot: Restarting system` on the UART.
- For comparison, well0nez's unguarded `RST_BUS_VE` pulse stalled the AV1
  core within 0.4 s of a codec switch.
- **Conclusion.** The VP9 residue is behind `RST_BUS_VE3`, and pulsing that
  line does not disturb the AV1 core. A VE3-only codec-switch reset needs
  none of 0305–0307's guard.

**Limits:**

- One board and short clips, looped: 600-odd AV1 frames overlapped by
  continuous switching.
- No H.264, MPEG-2 or VP8 pairs yet.
- The **existing** watchdog path (full `RST_BUS_VE` pulse plus the 0158
  IOMMU master reset beside AV1, reached only after a cedrus timeout) is
  unchanged and untested beside AV1.

Evidence (SHA-256, `local/recovery/2026-11-16-decoder-reset/av1/`):

| File | Digest |
| --- | --- |
| `run.log` | `b7336101…` |
| `storm-switch.json` | `38333928…` |

The UART capture and scripts are listed in `digests.txt` alongside.

## Next steps

1. ~~Narrow fix first.~~ Done above: a VE3-only pulse fixes the pairs.
   Still to do: stage the H.264, MPEG-2 and VP8 vectors on the board and add
   those pairs.
2. **AV1 interplay, with the operator present and UART connected:**
   - ~~AV1 beside cedrus codec switching under the VE3-only pulse~~: done
     above, 40/40 exact;
   - ~~AV1 beside a damaged cedrus stream (watchdog and 0158 exposure)~~:
     done, 30/30 clean.
3. **Arbitration only if step 2 shows it is needed,** and without a forced
   pulse after a timeout. The codec-switch reset does not need it.
4. **Series patch: done as 0210, installed and qualified** (see below).

## 0210

`0210-media-cedrus-reset-the-decode-engine-on-a-codec-switch.patch` adds
`cedrus_reset_on_codec_switch()` to `cedrus_hw.c`:

- It acts only when the optional `ve3` reset exists. It pulses
  `RST_BUS_VE3` when a job's codec differs from the last recorded one, and
  never touches `RST_BUS_VE`.
- A failed pulse leaves the codec unrecorded, so the next job retries.
- `cedrus_device_run()` calls it before request setup or any register
  write. `cedrus_hw_resume()` clears the record after releasing VE3.

**Host checks.**
[`test-cedrus-codec-switch-reset.py`](../../../tools/video/test-cedrus-codec-switch-reset.py)
runs the real helper under ASan/UBSan and checks its placement. It rejects
8 mutants: shared-line pulse, pulse on the first job, pulse on the same
codec, no pulse on a switch, recording after a failure, no VE3 guard, call
after request setup, and resume keeping the record. The 0209 tree fails it.
The sources build with `W=1` and no warnings, checkpatch is clean, and the
patch applies with zero fuzz.

**Release build.** 172 patches apply. Config, `Module.symvers`, the kernel
release, every DTB and the FIT `845494c3…` are unchanged. Only
`sunxi-cedrus.ko` changes, `1c8c87ba…` → `f820dffa…`, and the 0209 baseline
reproduces the installed module.

**Bundle.** The module-only bundle
(`local/recovery/2026-11-16-cedrus-0210/bundle/`, manifest `adb821ec…`)
passed a fake-root rehearsal: preview, apply changing only the cedrus
module, and exact rollback.

### Installation and qualification

**Install.** On boot `53018056`, the guarded installer ran preview
(`baseline`) then apply, with the FAT mounted read-only. Cedrus became
`f820dffa…`, the FIT/scr were unchanged and both manifests verified. The
backup is `/var/lib/h713-hdmi-startup/kernel-fit-0da4837ecc22464c9da0b04ba9c5cf57`,
holding `1c8c87ba…`.

**Qualification**, on boot `5c23f8c0` with the UART logged. The loaded
build ID `9c460a60…` matches the release module, and AV1 is bound.

| Check | Result |
| --- | --- |
| All 7 pinned HEVC/VP9 vectors as singles | 7/7 exact, full VE IRQ counts |
| Pair test: controls, 4 VP9+H.265 pair runs, recovery | **all exact**, no kernel lines |
| AV1 alone | 4/4 exact |
| AV1 ×20 beside H.265+H.265 | 20/20 exact; cedrus 20/20 |
| AV1 ×40 beside VP9+H.265 switching (138.9 s) | **40/40 exact**; cedrus 40/40 |
| AV1 afterwards | exact |
| Timeouts / IOMMU faults | 0 |

**Reboot check.** A reboot after this traffic printed `reboot: Restarting
system` on the UART. Boot `ff0aa58f` then passed startup with 0210 loaded,
AV1 bound and a clean capture teardown. Evidence digests are in the
[validation summary](decoder-reset-validation.json).

**Remaining limits:**

- Cross-codec pairs were added afterwards; see below.
- The watchdog path beside AV1 was tested afterwards; see below.

## Watchdog path beside AV1 (0158 + full `RST_BUS_VE` pulse)

This is the path `cedrus_watchdog()` already had before this work: on a job
timeout it pulses `RST_BUS_VE` and calls `sun50i_iommu_reset_masters()`.
well0nez measured this class of pulse stalling the AV1 core and then the
SoC.

**Phase A: the trigger alone.** Boot `ff0aa58f`, 0210 installed, no AV1
activity. `b03-h-bitflip-payload.h265` (damaged slice payload) still reaches
the watchdog: 1–2 `frame processing timed out!` per roughly 2 s run, and a
good H.265 vector is bit-exact after every run. `b08` (halved NALs) times out
occasionally. `b04` (damaged headers) only produces setup errors. No IOMMU
faults occurred: the HEVC validation patches appear to stop the stray reads
seen in October.

**Phase B: beside continuous AV1.** Setup:

- Root was made read-only first: journal relinquished to RAM, `sync`, then
  a SysRq emergency remount, verified `ro`. All output went to `/run`, with
  the run log and `dmesg -w` streamed live to the host and the UART logged.
- A background loop decoded `stock.ivf` on the AV1 core continuously to
  fakesink.
- In the foreground, 30 runs of `b03` each fired the cedrus watchdog. After
  each run, an AV1 gate decode (scored against libdav1d per-frame MD5s) and
  a good H.265 decode were checked.

| Measure | Result |
| --- | --- |
| Cedrus watchdog firings (full VE pulse + IOMMU master reset) | **30** |
| AV1 interrupts during the 30 runs | 7157 |
| AV1 gate after each run | **30/30 exact**, plus 1080p at the end |
| Cedrus good-vector check after each run | 30/30 exact |
| hantro errors / IOMMU faults / stall | **none** |

**Restore.** The board was rebooted to bring root back read-write. On the
UART, `reboot: Restarting system`. Boot `a2cb8f4b` has root `rw`, startup
PASS, ext4 error counter zero, manifests verified and AV1 bound.

**What this shows.** With 30 full-VE watchdog pulses landing while the AV1
core was continuously busy, there was no AV1 stall, error or loss of
exactness on this board. well0nez reported the opposite (stall within 0.4 s,
SoC down about 15 s later). Our AV1 DT node is identical to theirs (theirs
was taken from ours), so the difference lies elsewhere: driver, clocking,
timing, or their measurement conditions. It is not explained here.

**Limits:**

- The AV1 frames decoding at the moment of each pulse came from the
  unverified fakesink loader. Exactness was checked by the gate *after*
  each pulse, together with the absence of hantro errors or stalls.
- Whether a given pulse hit an AV1 frame in flight is probabilistic,
  though very likely across 30 pulses with the core continuously loaded.
- One board, 30 pulses.

Evidence digests (SHA-256, `local/recovery/2026-11-16-watchdog-av1/`) are
in `digests.txt`. The key files are `phase-b.log` `af7ac503…` and
`dmesg-stream.log` `02c1f7e4…`.

**Conclusion.** No AV1 arbitration is needed for the watchdog path on this
bench either. If it ever shows up, the guard design is still available, but
there is no evidence here to justify importing 0305–0308.

## Cross-codec pairs on 0210 (H.264, MPEG-2, VP8)

**Vectors.** `tools/video/make-test-streams.sh` regenerated the ladder into
`local/video-test-gen-20261116`, a fresh directory, so the originals were
untouched. The run is deterministic:

- the H.264 streams are byte-identical to the August originals;
- the H.264 and VP8 NV12 references match the pinned MD5s in
  `reference-md5.txt` and `vp8-reference-md5.txt`;
- MPEG-2's IDCT is not bit-defined, so its references are the hardware's own
  pinned MD5s (`mpeg2-reference-md5.txt`), and the board's single decodes
  match them.

Staged on the board: `v03` (H.264 Main 720p, 60 frames), `v05` (H.264 High
1080p, 60), `p02` (VP8 720p, 25), `p06` (VP8 partitions, 25), `m02` (MPEG-2
progressive, 50) and `m04` (MPEG-2 interlaced, 50), plus `h01` (H.265) and
`vp9-short-gop`.

**Runner.**
[`decode-codec-pair-test.py`](../../../tools/video/decode-codec-pair-test.py)
gained `.h264`/`.m2v`/`.ivf` (VP8) pipelines, MD5 scoring for rows that
carry `raw_md5`, and a plan file
([`codec-pairs-plan.json`](../../../tools/video/codec-pairs-plan.json)).

**Result.** Boot `a2cb8f4b`, 0210 installed (cedrus `f820dffa…`), two
rounds:

| Pair | Rounds exact |
| --- | --- |
| H.264 `v03` + H.265 `h01` | 2/2 |
| MPEG-2 `m02` + H.264 `v03` | 2/2 |
| VP8 `p02` + H.265 `h01` | 2/2 |
| VP8 `p02` + VP9 | 2/2 |
| MPEG-2 interlaced `m04` + VP9 | 2/2 |
| H.264 1080p `v05` + VP9 | 2/2 |
| VP8 `p06` + MPEG-2 `m02` | 2/2 |
| H.264 `v03` + VP8 `p06` | 2/2 |
| VP9 + H.265 `h01` | 2/2 |

- **All 34 phases exact:** 8 single-stream controls, 18 pair runs and 8
  recovery singles.
- **No kernel lines.** Each pair's VE interrupt count equals the sum of its
  streams' frames, so both streams decoded in hardware.
- **Scope.** This confirms that 0210's codec-switch reset does not disturb
  any other codec combination. It does not show which of these pairs would
  have failed without 0210; the production module has no switch to disable
  the reset, and well0nez found only the VP9/H.265 combinations failing.

Evidence (SHA-256, `local/recovery/2026-11-16-codec-pairs/`): `run.log`
`91820969…`, `results.json` `82e46d0c…`, `manifest.json`
`dafdafbd…`.
