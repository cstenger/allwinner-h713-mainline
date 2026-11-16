# H713 eMMC read threshold — November 16, 2026

Kernel **0206**, adapted from well0nez's pinned **0313**, is installed and
passes the bounded DDR3 comparison below. The unpatched kernel reproduced a
real eMMC stall under the read-only workload. The candidate completes the
same workload with matching data hashes and the threshold active.

**Subsequent recovery work:** [0207](emmc-recovery.md) adapts the separate
0312 reset-before-CMD12 path with checked errors and H713-only scope, and
qualifies three natural full-FIFO error recoveries. The original limits below
describe the threshold-only qualification.

## Scope and provenance

The original implementation and HY310 measurements are well0nez's; the patch
retains their authorship and pinned source link. Our adaptation adds an
explicit `emmc_read_threshold` configuration flag enabled only for
`sun50i_h713_emmc_cfg`. It does not select every non-v5p3x controller that
advertises HS400. H713 SDIO and other sunxi controllers keep their behavior.

HS200/HS400 reads with a 1–512-byte block enable the card read threshold;
writes, zero/oversized blocks and other timings clear its size/read-enable
fields while preserving unrelated THLD bits. The helper runs before DMA is
started. The separate **0312 CMD18 error-recovery reset is not imported**.

## Read-only workload and baseline failure

Board: HY200 QZ713DF_A1, DDR3; eMMC `4022000.mmc`, HS400 at 200 MHz,
eight-bit bus and 1.8 V. Each round opens the unmounted 2 GiB vendor system
partition `mmcblk0p9` with `O_RDONLY|O_DIRECT` and hashes all returned bytes.
There are no raw storage writes or timing/error injections. The normal HDMI
services remain running; ordinary OS logging remains enabled.

The mixed load combines 3840×2160 H.264 hardware decode with separate
3840×2160 offscreen Panfrost rendering at up to 30 fps. The GPU renderer and
pixel readback are checked, and every completed loaded round requires
positive VE and GPU interrupt deltas. Workload files/logs reside in tmpfs.
An initial GStreamer GL attempt produced no GPU IRQs and was rejected; a
GBM GL probe faulted in userspace. Neither counts as a valid combined run.

Runtime PM is temporarily held on during aligned, read-only STAS/THLD
sampling, then restored. This avoids MMIO reads from a clock-gated controller.
This workload is a bus-pressure comparison, not Kodi playback or a maximum
storage-throughput benchmark: SHA-256 and Python sampling consume resources.

On baseline boot `a269f15e`, the idle 2 GiB read passes at **78.87 MiB/s**
with THLD zero. During the first valid mixed round:

- At uptime **2083.744 s**, the driver reports a CMD18 data error with
  `RINT=0x20`, `STAS=0x02009109` (FIFO-full bit set), `THLD=0`.
- At **2084.775 s**, its stop command fails. The reader remains blocked in
  `mmc_wait_for_req_done`, with the partition read counters no longer moving.
- The test GPU is stopped and the blocked sampler frozen; the operator
  cold-cycles the board. The recovered boot completes ext4 journal recovery,
  reports `errors_count=0`, and verifies both installed manifests and startup
  health. This is not an offline filesystem-check claim.

No baseline mixed round completed, so there is no valid baseline mixed
throughput or completed-round FIFO sample rate to compare.

## Candidate results

The guarded FIT installer backs up the old FIT and both script/manifest
copies. The baseline build matches the installed FIT byte for byte. The
candidate uses the installed kernel's **clang/LLD 23.1.4**, extracted into an
isolated directory from cached packages; system tools are untouched. An
initial build with the updated host's 23.1.5 is rejected by the configuration
comparison and is not installed.

Candidate configuration, DTB, Module.symvers and kernel release match the
baseline. Its FIT is `796e1fb1…` (7,613,748 bytes). Warm reboot into boot
`c8ce1e43-f271-4eab-bdb1-b07ae0f5f490` completes normal startup and health
acknowledgement. Sampling observes **THLD `0x02000001`** during 512-byte reads.

| Test | Result |
| --- | --- |
| Idle, 2 GiB | Matching SHA-256; 78.92 MiB/s; zero FIFO-full samples |
| Mixed round 1, 2 GiB | Matching SHA-256; 73.80 MiB/s; VE/GPU IRQs advance |
| Mixed round 2, 2 GiB | Matching SHA-256; 73.31 MiB/s; VE/GPU IRQs advance |
| Mixed round 3, 2 GiB | Matching SHA-256; 73.99 MiB/s; VE/GPU IRQs advance |
| Mixed FIFO sampling | **0 full samples / 67,494**; maximum sampled thermal-zone-0 temperature 74.86°C |
| Seven pinned HEVC/VP9 vectors | **748 frames, all bit-exact**, with hardware IRQ evidence |
| Runtime PM | Normal `auto` restored; controller reaches `suspended`; a 4 MiB direct read resumes it successfully |
| Final health | Startup checker PASS; system running; zero failed units; ext4 error counter zero; both manifests verify; CPU_COMM IRQ-only/no desync |

All four full-partition reads match the baseline digest
`336a55d66d0dbdad6c2f05c75bdf8b6945a4d91133190755d3419329a5ac1c2d`.
There are no new kernel eMMC errors, IOMMU faults or oopses in the candidate
load window. Idle throughput is unchanged within this test's resolution;
the failed mixed baseline cannot support a speedup claim.

## Host validation and limits

The actual prepared eMMC/SDIO helpers pass **2754 ASan/UBSan cases** across
controller selection, timing, direction, block size and prior register state.
Tests also cover read-to-write and fast-to-slow transitions, preservation of
unrelated bits, H713-only configuration and programming before DMA. The final
production kernel/modules/both DTBs/FIT build passes. Checkpatch has zero
errors/warnings; eight bundle-builder and 18 installer tests pass.

This qualifies the bounded comparison on this DDR3 bench. It does not prove
long-duration reliability, HS200 hardware behavior, write performance,
injected-fault recovery or other boards. **0312 remains a separate review**:
the baseline demonstrated why recovery matters if a read error still occurs.

The [validation summary](emmc-threshold-validation.json) contains full hashes,
per-round measurements and evidence digests. Raw logs, prepared trees, the
isolated toolchain and the installation bundle remain ignored under
`local/recovery/2026-11-16-emmc-threshold/`. Reusable bench tools are in
[`tools/storage`](../../../tools/storage/README.md).

Installed backup:
`/var/lib/h713-hdmi-startup/kernel-fit-9b9c1b0ecbeb4c23b3dbd312d41d73e4`.
Use the guarded kernel-FIT installer's `--rollback` operation with the current
boot ID and boot partition mounted at `/mnt/boot` if restoration is needed.
