# Checked H713 eMMC read recovery — November 16, 2026

Kernel **0207** adapts well0nez's pinned **0312** reset-before-CMD12 approach.
It is scoped to H713 eMMC and checks every restore stage. A controlled bench
run reproduced three natural full-FIFO read errors and recovered each one,
completing the 2 GiB read with its expected hash.

## Implementation

Only `sun50i_h713_emmc_cfg` enables `recover_read_errors`. The new path
requires a CMD18 request with read data. CMD17, writes, CMD53 and other
controllers keep their existing paths.

After the hard IRQ has stopped/unmapped DMA, the existing IRQ thread runs
outside the host spinlock and performs:

1. Require a reset controller and check `reset_control_reset()`.
2. Check `sunxi_mmc_init_host()` and verify that its IDMA soft-reset bit
   actually cleared; the existing initialization helper's bounded IDMA wait
   does not report expiration.
3. Restore bus width and clock/timing/HS400 strobe configuration, checking
   the result stored in `host->ferror`.
4. Issue CMD12 only after those steps succeed, and check its result.

The original transfer errors remain available to the MMC core for normal
recovery/retry after a successful stop. Failed restoration or CMD12 latches
`recovery_error`, sets the request errors, clears `manual_stop_mrq` under the
lock and completes the request once. Later requests fail before DMA mapping
or MMIO. An unrelated `set_ios` call cannot clear this terminal latch; it
requires reprobe or reboot. The manual-stop helper returns its result while
legacy callers retain their prior handling. Its CMD53 high-bit argument now
uses an unsigned shift, preserving the wire value without signed-shift UB.

Original authorship of the reset-before-stop approach and HY310 evidence
belongs to well0nez. H713-specific selection, checked failure handling,
terminal refusal, tests and bench diagnostics are our adaptation.

## Host checks

The actual prepared restore, manual-stop, completion and refusal helpers
compile under ASan/UBSan with sanitizer errors fatal. Tests cover missing
reset control, reset failure, host-init failure, IDMA reset stuck, clock
failure, CMD12 error and CMD12 timeout. They verify skipped unsafe stops,
ordered success, exact-once cleanup/completion, a cleared `ferror` not erasing
the terminal latch, later data/status requests failing without I/O, absent
stop requests, and unchanged non-target paths.

All six deliberately broken variants are rejected: ignored reset error,
ignored clock error, ignored stop error, missing controller guard, non-sticky
refusal and uncleared request ownership. The diagnostic generator's board,
controller, command, direction, size and sector-boundary gates also pass
ASan/UBSan tests. Existing 0206 threshold tests continue to pass 2754 cases.

## Bench diagnostics and recovery evidence

Diagnostics are outside the active kernel series and default off. The
normal image is restored on disk before any trial, while the diagnostic
kernel remains in memory. Root is read-only during fault trials; journaling
is moved to RAM and restored afterward. The hotspot lease file holds root
open for writing, so the kernel emergency remount is used. Physical recovery
is available.

An initial completion-time synthetic-error probe is **not counted as a
positive recovery test**. The transfer had already completed when the error
was synthesized; CMD12 failed, and the terminal refusal path correctly
returned I/O errors instead of hanging. This does not establish behavior for
an active full-FIFO read. Uncached root reads also failed, and ext4 reported
read/superblock-write errors while the controller was quarantined. The
operator cold-cycled; the normal image booted healthy with ext4's error
counter zero. The completion-error control was removed from the diagnostic
rather than used again. No offline filesystem check is claimed.

The revised diagnostic only bypasses 0206's threshold on bounded, plain
CMD18 reads wholly inside the pinned unmounted vendor partition
(`mmcblk0p9`, LBAs 599040–4793343). It never changes rootfs-sector requests,
writes or timing registers. On boot
`b92a0347-04a2-47cd-afd0-4a4d273e542e`, the verified 4K H.264 decoder and
4K offscreen Panfrost load ran alongside a direct 2 GiB read:

| Error uptime | FIFO status at error | Successful restore/CMD12 uptime | Interval |
| --- | --- | --- | --- |
| 103.358038 s | `0x02009109`, full | 103.392655 s | 34.617 ms |
| 113.843692 s | `0x02009009`, full | 113.880143 s | 36.451 ms |
| 115.605624 s | `0x02009009`, full | 115.642052 s | 36.428 ms |

All three are natural driver error interrupts with the threshold disabled
for the selected vendor reads, not synthesized completion errors. There is
no failed-stop or terminal-recovery message. The full read returns
`336a55d66d0dbdad6c2f05c75bdf8b6945a4d91133190755d3419329a5ac1c2d`,
matching the baseline partition hash. It completes at 73.16 MiB/s with
positive VE/GPU IRQ deltas, 100 FIFO-full samples out of 22626, and maximum
sampled thermal-zone-0 temperature 70.357°C. The diagnostic reports 1539
selected requests and three recoveries. Its remaining allowance is cleared
to zero. Startup health passes and ext4's error counter remains zero.

Root/journaling policy is restored and the board reboots into the normal
image. The diagnostic-free FIT is `845494c3…`; configuration, DTB, kernel
release and Module.symvers match the preceding 0206 installation. Production
rebuilds after removing each diagnostic reproduce that FIT byte for byte.

## Final production regression

Final production boot: `8371b96d-56a0-46d2-a0fe-b602791c8e5d`.
The diagnostic parameters are absent and startup health passes.
The normal image passes a 2 GiB idle read and three loaded 2 GiB rounds,
all with the pinned partition hash, no new kernel errors and zero FIFO-full
samples. The seven pinned HEVC/VP9 vectors remain bit-exact (748 frames).
A 4 MiB direct read successfully resumes the controller from runtime suspend
with the normal `auto` policy. Both installed manifests and the FIT hash
verify; the health acknowledgement dry-run passes without writes. The system
is running with zero failed units and ext4's error counter zero; CPU_COMM
remains IRQ-only with no desync. Full measurements and evidence digests are
in the [validation summary](emmc-recovery-validation.json).

This qualifies the observed natural-error recovery and the checked terminal
stop-failure behavior on the DDR3 bench. Other restore-stage failures are
host-tested, not deliberately induced on the mounted-root board. Other
boards, a hardware HS200 trial, writes and long-duration reliability remain
outside this bounded qualification. Keep 0206 enabled: 0207 is recovery for
an error that still happens, not a reason to reintroduce FIFO starvation.

Raw logs, diagnostic source patches, installation backups and exact test
scripts remain ignored under `local/recovery/2026-11-16-emmc-recovery/`.
