# MIPS callback stalls by Linux sampling; SetSource executes

The temporary bootloader trace ran successfully. The callback and CheckSignal
executed during bring-up, but their counters were stationary throughout the
Linux experiment. SetSource reached both its firmware adapter and HAL, with
argument 1, without restarting the callback or changing composition/AFBD.

## Measurements

Counters are MIPS KSEG1 writes to ARM physical 0x4e340080..0x4e34009c.
They were not reset while live. Each snapshot reads words sequentially.

| Sample | event8 entry | callback | CheckSignal entry / return | last return | RPC / HAL | last source |
|---|---:|---:|---:|---:|---:|---:|
| U-Boot after readiness | 0 | 997 | 997 / 997 | 0 | 0 / 0 | 0 |
| Linux idle start | 0 | 3928 | 3928 / 3928 | 0 | 0 / 0 | 0 |
| Linux idle +2 seconds | 0 | 3928 | 3928 / 3928 | 0 | 0 / 0 | 0 |
| One frame, before RPC | 0 | 3928 | 3928 / 3928 | 0 | 0 / 0 | 0 |
| After SetSource(1) | 0 | 3928 | 3928 / 3928 | 0 | 1 / 1 | 1 |
| After another 2 seconds | 0 | 3928 | 3928 / 3928 | 0 | 1 / 1 | 1 |

RPC returned successfully in 75,537 microseconds, nret=0. The ring remained
frozen at one write. Composition and AFBD snapshots before/after RPC match
exactly. Last return zero does not establish that every earlier return was zero.
ARM-cached firmware object snapshots remain subject to the earlier cache caveat.

This rules out a completely inactive detector since release and a SetSource
call that never reaches firmware. It does not locate the callback stall: it
occurred between the U-Boot snapshot and the first Linux snapshot, which was
after replacing the DECD module. It could precede Linux or occur during boot
or module setup. RPC execution shows the whole MIPS core is not stopped.

The event8-filtered DoMessage entry count is zero despite callback activity.
Do not infer missing event8 production from this alone: the callback may use
another dispatch route, or instrumentation coverage needs correction. Capture
callback caller PC and message ID in the next trace to resolve that discrepancy.

## Deployment and recovery

User authorized a temporary persistent flash after two failed RAM-only attempts.
Installed second-stage bytes matched the original frame-trace image exactly.
Installed SPL differed from that combined image, so it was preserved unchanged.
Backups of both components were copied to the host before any write.

Only 1790 sectors at LBA 4828160 (the established second-stage location) were
written. The candidate preserves original sector-tail bytes and changes only
the 6256-byte trace table. Candidate padded second-stage SHA-256:
`4e11fb9d748a0711a88b16bb848b4705424f7113ffa2756c8a5b8bf1e66aa0a6`.
Readback matched before reboot. `h713_disp mips-comm-trace 0x34` installed hooks
and reached application readiness. The established 0076v3 kernel was booted
with AFBD init blacklisted; budgeted DECD and CPU_COMM modules were loaded.

After evidence retrieval, the original second stage was restored and compared
byte for byte. SPL was independently read back and matched its backup.
Restored second-stage SHA-256:
`b65bd629c43fc48034a7e32e686bbc735b2e7067f56cd6b77da6eddf75fde208`.
Unchanged installed SPL SHA-256:
`cb9da87448a57aa1cafbc7ebf66200b5183304cef1eafe23d0818b99696a49ec`.

Restored U-Boot subsequently booted normal Linux 6.18.38. SSH recovered,
the default command line was confirmed, and MIPS reset read 0x00000000
(core parked). See restored-boot.txt and restored-linux.txt in the evidence.

## Next experiment

Repeat with callback caller/message capture, and sample counts twice while
still in U-Boot. Then sample at early Linux milestones before loading or
replacing DECD, after its probe, and after CPU_COMM load. If counts stop before
Linux, investigate firmware scheduling first; if they stop at a Linux milestone,
inspect the clocks, interrupts, resets, and shared state changed there.

Raw logs, experiment script, register snapshots, and exact recovery copies:
[event8-instrumented-2026-09-08](event8-instrumented-2026-09-08/).
