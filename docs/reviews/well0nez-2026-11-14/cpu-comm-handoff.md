# CPU_COMM shared-memory handoff — November 14, 2026

This follows the [failed IRQ trials](cpu-comm-irqs.md). Patches **0200–0201** fix
independently reproducible ownership and bounds defects before retrying IRQ
operation. IRQ remains opt-in in the kernel module; the DDR3 bench uses an
explicit module option for the trial. Results below distinguish source
proof from hardware qualification.

## Defects and fixes

1. **Counter claim was not atomic.** The packed semaphore helpers waited
   until a counter was positive, then decremented it without exclusion.
   Multiple ARM CPUs could acquire the same lock or lose increments. A
   global spinlock now protects test/decrement and increments; waitqueue
   conditions claim the count while testing it. The void `down()` uses an
   uninterruptible wait rather than proceeding after an ignored signal.
   Native atomic instructions are avoided because some packed counters
   live in uncached mappings. A recycle timeout no longer writes without
   owning the lock.
2. **Reference translation escaped its mapping.** After checking private
   arenas, `cc_deref()` translated any remaining peer word by subtracting
   the shared physical base and adding its kernel virtual base. It now
   requires membership in the reserved shared region. An arbitrary peer
   word cannot name unrelated kernel virtual memory.
3. **Empty marker was accepted as a slot.** `FIFO_DEFAULT_CAP` is 21,
   including one unused ring entry; message slots are 0–19. The receive
   path accepted index 20, the protocol's empty marker, and wrote at
   `sequence + 360 + 104*20`, which is the next 2440-byte sequence header.
   The corrected bound rejects it before any write. This is a concrete
   out-of-pool shared-memory write, independent of a cache-barrier theory.
4. **Caller wake preceded ACK completion.** The RETURN handler woke a
   caller before finishing shared-header reads and acknowledgement. The
   caller could recycle its return/wait objects on another CPU. Completion
   now snapshots sender-owned metadata, holds the active-wait list lock
   shared with timeout cleanup, queues the return, publishes its ACK, then
   signals the caller. It resolves an active ARM wait by session, never by
   dereferencing an embedded sender-owned pointer. Late replies are ACKed
   without waking recycled waits; duplicate recycling is refused.
5. **ACK ownership was underspecified.** An echoed word could be decoded
   as any registered/shared address and signalled as a semaphore. ACKs now
   match the current CPU's pending session and exact ARM-owned counter
   handle, under a lock shared with timeout cleanup. Foreign, stale and
   nonzero-upper-word ARM handles are rejected. The sender-owned 64-bit
   RETURN_ACK metadata is echoed unchanged, instead of truncating it to
   one word. That opaque peer handle is not an ARM pointer.

6. **ACK timeout did not cancel peer ownership.** The sender cleared SENT
   after a missing CALL_ACK and permitted the next caller to overwrite
   the outstanding publication. Patch 0201 preserves it and quarantines
   subsequent sends with `-EPIPE`. The check runs before and after the
   send semaphore; a pre-existing SENT flag also refuses publication.
   Read-only `tx_desynced` exposes the MIPS quarantine. A clean firmware
   and driver startup is required; module reload alone cannot revoke
   firmware ownership.

The receive thread remains sleepable and owns only the ARM inbox interrupt.
No arbitrary delay, polling rescue in IRQ mode, firmware replacement, or
blind copy of a flag-clearing loop is used to make tests pass.

These defects provide real corruption paths. The old UART alone cannot
establish which interleaving produced every word of the earlier crash;
the changes and repeated hardware tests must be evaluated together.

## Host regressions

`tools/mips/test-cpu-comm-handoff.py` extracts the actual prepared kernel
functions, compiles them with ASan/UBSan and pthread/MMIO stubs, and checks:

- Four competing callers cannot own the same semaphore; interruption and
  timeout do not consume unowned counts; void acquisition still waits.
- Valid arena/shared references resolve; out-of-region peer words do not.
- A return with a MIPS-looking embedded handle completes only its live ARM
  session, preserves both opaque words, and sends ACK before wake.
- Late, duplicate and malformed-list returns cannot signal unrelated waits.
- A stale/foreign ACK cannot signal the next session's reused counter.
- A slot already recycled cannot be enqueued into the free ring twice.
- Index 20 does not write the following sequence header.
- Missing ACK quarantines that CPU's sends; a queued sender or an already
  outstanding publication cannot overwrite the shared header.

The same harness reproduces failures in the old semaphore, reference and
slot-boundary code. Header capacities are read from the actual header.
An initial added recycle check confused 21 ring entries with 20 usable
slots and emitted a warning in three polling control calls. That attempt
is preserved; the check and its regression were corrected before any IRQ
retry. The final production build and the actual built-source tests pass.

## DDR3 hardware validation

The test routine is the firmware's existing zero-parameter
`THal_Vp_GetSignalInfo_1_000` control stub (`0x24b17fb7`) through the CALL
ioctl. This tests transport, not a useful signal-information implementation.
Per-mode RX counters, completed calls, kernel logs and startup health are
checked together. Four clients each make 50 calls in the concurrent trial.

| Mode | Boot | Calls | Result |
| --- | --- | ---: | --- |
| Corrected polling control | `46d598d9` | 3 + 200 concurrent | PASS; 406 RX messages by polling, zero by IRQ; no handoff warnings/faults |
| IRQ-only retry, 0200 | `68f46015` | 3 + 200 serial; then 200 concurrent requested | Serial PASS, 406 IRQ RX / zero polling; concurrent stalls after 37 completions, Linux remains healthy |
| Matched polling, 0200 | `59a327f0` | 203 serial; then 200 concurrent requested | Same approximately 240-call stall; 482 total polling RX, Linux remains healthy |
| 0201 initial polling | `b95e47b4` | 3 | PASS, six polling RX; subsequent firmware register query loses SSH/UART before long test output, operator power-cycle required |
| 0201 quiet polling | `84835e4d` | 603 serial + 600 concurrent requested | Serial PASS; 595 concurrent complete, two RETURN-only timeouts; 2398 polling RX, zero IRQ; Linux healthy, firmware normal-task progress stalls |
| 0202 polling | `7528a362` | 603 serial + 600 concurrent | PASS, exact 2406 polling RX / zero IRQ; native level 2, no transport/fault warnings or failed units |
| 0202 IRQ | `80cdc8dc` | Three initial calls pass; long serial attempted | FAIL: kernel paging fault at uptime 38.79 s, address `0015bd448baa0000`; auto-restarts |
| 0202 IRQ with `zero_wait_ptr=Y` | `528704e1` | Three initial calls pass; long serial attempted | FAIL: loses SSH/UART during serial attempt; SysRq recovery fails, operator cold-cycle |
| Recovered 0202 polling | `91014151` | Three calls | PASS and full startup check PASS; IRQ override removed |
| One-boot allocator diagnostic | `adfc7177` | 600 serial + 600 concurrent + 837 more serial | FAIL after 2037 completions; exact 2400 IRQ RX / zero polling after first 1200; paging fault `0015bd448baa0018` at 102.32 s, no earlier allocator report captured |

### Firmware logging backpressure

The original short polling comparison was not matched: it made 203 total
calls, whereas the failing IRQ run had already completed 203 before the
concurrent phase. The longer polling control reproduces the stall. It is
therefore not evidence that IRQ reception caused this timeout.

The captured firmware ELOG buffer is exactly 2 MiB full. Disassembly of
its actual writer shows that reaching that boundary synchronously prints
all 2 MiB through UART before resetting the write pointer. The final
records are the stalled session `0xf1` preparing its RETURN. That session's
RETURN subsequently arrives at uptime 174.59 seconds, long after its RPC
timeout near 81 seconds. The guarded driver rejects it as late/duplicate,
ACKs it, and does not wake a recycled wait. This explains the observed
long transport stall; it does not establish the precise cause of the
older kernel fault.

After draining, three recovery calls and 600 serial calls pass. A later
400-call concurrent request again outlasts the log space and times out;
this is not a successful stress qualification. A per-tag logging command
was insufficient to establish a quiet test condition. Before the next
stress run, use the firmware's native `elog -l 2` global filter and observe its effect;
ARM physical readback of cached MIPS globals may initially be stale. Executing the pinned firmware's actual CLI handler under MIPS
emulation confirms that this command changes the global filter from 5 to
2 without substituting its setter. On boot `84835e4d`, the native command returns and later ARM physical
readback shows level 2. The 1200-call attempted workload leaves the ELOG
write count at `0x696cf`, far below 2 MiB, confirming that this later stall
is separate from log flushing. An attempted MIPS `regr` command on the
previous boot stopped all host access; that diagnostic is not retried.

The driver's historical hardcoded ELOG control offsets are 0x14 bytes
stale for this firmware. Its printed mode is not reliable evidence of
actual logging mode. Do not use those offsets to modify firmware globals.
The next tests must record the native logging filter as a bench condition;
no firmware binary is replaced. IRQ remains default-off.

Raw builds, source-derived test output, firmware disassembly, UART and
per-client logs remain ignored under
`local/recovery/2026-11-14-cpucomm-handoff/`. No proprietary binary or raw
capture belongs in the public patch series.

## Quiet-run spinlock assertion and patch 0202

After the level-2 run, the saved MIPS context at `0x8b954450` contains
PC `0x8b125a54`, the infinite assertion loop after `tridspinlock.c:326`.
The surrounding saved words identify `ASSERT FAILED`, `spinLock`, and line
326. The actual pinned firmware's acquisition code at `0x8b125674`
requires thread ID 255 when the software owner is free. Its entry helper
at `0x8b1250e8` gates **byte 0** under hardware lock `id + 2`; software
ownership is **byte 1**, count is +4 and thread ID is +8. Byte 2 is policy.

Our old driver used byte 3 for both entry and persistent ownership and
unconditionally claimed it after a hardware timeout. ARM could mutate
count/thread while the firmware held the actual gate, or leave a free
software owner with a nonfree thread ID. Shared lock 2's captured gate is
owned by MIPS, consistent with assertion inside the gated path. This is
an independently reproduced ABI conflict, not a speculative cache delay.

Patch 0202 separates the gate and owner, refuses forced entry, publishes
cleared metadata before freeing ownership, checks the actual ARM thread
(`pid`), and preserves recursive acquisition only in mutex mode. A failed
try against a MIPS-owned lock or a hardware timeout leaves metadata intact.
The old dynamic-slot allocation bookkeeping is preserved separately;
its use is not exercised by these fixed-lock transport tests.

`tools/mips/test-cpu-comm-spinlocks.py` extracts the real ARM functions and
runs 3000 critical sections across four ARM threads and one firmware-ABI
peer under ASan/UBSan. It checks peer ownership, entry arbitration, hardware
timeout refusal, same-thread recursion, foreign-thread unlock rejection and
shared-process thread separation. The same test deterministically exposes
the old free-owner/nonfree-thread conflict. The production build and guarded installation pass. The corrected polling
run completes all 1203 calls, including the four-client workload that failed
on 0201. No corruption or transport warning is observed. The subsequent IRQ run still faults, and suppressing outbound ARM wait
pointers does not cure it. The changes fix independently demonstrated defects;
they do **not** establish that IRQ corruption is resolved. IRQ remains
unqualified and default-off. The long serial files did not retain results
across the failure, so only the three initial completions are counted.

The HDMI shutdown hold guard refuses warm reboot with its receiver hold
retained, including after this healthy polling run, and powers down. This
behavior is separate from the CPU_COMM stall and is not proof of firmware
failure. Operator cold cycles are required for the upcoming mode changes.

## Next diagnostic

The existing kernel supports SLUB allocator consistency checks, red zones,
poisoning and allocation tracking. A narrowly validated script-only bundle
prepends `slub_debug=FZPU oops=panic` to the existing boot arguments without
changing FIT/module bytes or the saved U-Boot environment. The installer
requires the exact prefix, the original remainder hash, matching script
payload/CRC, and unchanged kernel/module/configuration. Eighteen transaction
tests pass, including diagnostic rollback and refusal of unrelated changes.
The normal files and IRQ override must be restored/removed after diagnostic
boot verification and **before** calls. This keeps a subsequent reboot on
normal polling. Host-streamed call output avoids losing every long-test
completion to the target's page cache as happened in the failed IRQ trials.

Comparison after implementing 0202 also found well0nez's prior 0259 matching
spinlock analysis; provenance now links it and the reserved-thread-sentinel
0261 follow-up. No claim that the shared-memory fix uniquely explains the
remaining kernel fault is made.

The allocator diagnostic verifies `slub_debug=FZPU oops=panic` in the
running command line and red-zone/poison/store-user flags in sysfs. Normal
scripts and the IRQ override are restored/removed before calls. All 600
concurrent calls pass; a later serial run still faults. This shows that a
single successful concurrent run is insufficient. The UART stops at the
first fault-address record without an ESR or register dump, even under
allocator diagnostics. Patch 0203 adds raw PC/LR/SP/ESR and initial argument
registers to that same first record; it changes reporting only and remains
a diagnostic, not a corruption fix. The full production diagnostic build
and a guarded bundle must pass before its next board run.

## Early-frame trial and isolated-reference witness

Early-frame boot `f96d7136` completes 12 IRQ calls, then PID 1 exits with
segmentation-fault status and the kernel panics at 63.80 seconds. Its trace
includes `get_signal`, `el0_undef` and `do_exit`; no `die_kernel_fault`
register record is triggered in this failure. Normal files and polling
settings were already restored, so it restarts automatically into healthy
polling boot `2b8543ca`. Three recovery calls and full startup health pass.

0204 is an **opt-in diagnostic**, not a corruption fix. It replaces private
arena references with addresses in a separate poison-filled reserved window;
ARM `cc_deref` still resolves the actual local objects. Read-only status
scans for changed words and prints the first changed-word sample. A positive
write is useful evidence; absence of a write or a passing diagnostic workload
would not by itself qualify the normal protocol. Firmware reads can see
poison, so initial control calls must precede stress, with traffic stopped
on any detected write.

A temporary allocator probe could not obtain the required MIPS direct-address
mask (rc -5); that DMA implementation was not deployed. The final diagnostic
grows the existing DDR3 no-map trace reservation from 4 KiB to 128 KiB and
keeps its first page intact. Driver setup requires that exact reservation.
The kernel never returns its backing to normal allocation during driver
teardown; retained peer references remain inside reserved memory until reboot.
Source-extracted ASan/UBSan tests check default references, local decoding,
peer-write isolation/detection, first-page preservation, invalid reservation
refusal, capacity exhaustion and cleanup. The bundle validator accepts only
the exact reservation `reg` change and rejects unrelated DT edits.

## Witness diagnostic results — November 15, 2026

The first 0204 build reserved 128 KiB and capped each arena at 64 KiB.
The device-state arena is `CPU_COMM_DEV_SIZE` = 119648 bytes, so probe
failed with `-ENOSPC` on boot `c02ca457`: no CPU_COMM, no diagnostic.
The earlier host test registered 96-byte arenas and could not see this.
That bundle (FIT `d37b6a91…`) **was** installed despite the earlier
"not installed" wording above; it has been rolled back.

Corrected 0204: 256 KiB reservation (`0x4d980000..0x4d9bffff`, still below
U-Boot's `0x4e000000` logo), no per-arena cap, and a `BUILD_BUG_ON` over
the real sizes. The firmware image builds no `lui` address in
`0x4d960000..0x4dffffff`; U-Boot touches only the first trace page.
`tools/mips/test-cpu-comm-witness.py` now registers both arenas at their
real sizes, read from `cpu_comm.h`, in probe order. A 128 KiB variant of
the test fails the old source at the device-state registration, matching
the board. Bundle tests (8) pass; config identical, module reproduced.

| Step | Boot | Result |
| --- | --- | --- |
| 256 KiB witness, IRQ-only | `db484cbe` | Probe OK; arenas at tokens `0x4d982000` (9984 B) and `0x4d987000` (119648 B), zero changed words |
| Normal files restored, override removed | `db484cbe` | Before any call; running witness module unchanged |
| `elog -l 2`, 3 control calls | `db484cbe` | PASS, 6 IRQ RX / 0 polling, zero changed words |
| 600 serial (witness-guarded) | `db484cbe` | PASS, zero changed words |
| 4 × 150 concurrent | `db484cbe` | PASS, zero changed words |
| Second 600 serial | `db484cbe` | **Silent SoC reset after 442 calls** (1645 total incl. 3 control), uptime ≈ 180 s |
| Recovery | `19e45dd2` | Normal 0202 polling; 3 calls PASS; no failed units |

The reset left no kernel fault, Oops or panic text on UART: the last lines
are rate-limited CPU_COMM trace summaries at 178.28 s, then SPL. Linux
exposes no watchdog device and the previous boot's journal was not retained.
The witness reported no write in any status read, including immediately
before the failing round; it is polled every 50 ms, so a write in the final
interval cannot be excluded.

Interpretation, kept narrow: with peer-visible private references diverted,
the IRQ failure changed from kernel paging faults with MIPS-looking words
to a silent reset, after a similar call count (2037 under SLUB, 1645 here).
No peer write to a diverted private reference was observed. This weakens,
but does not exclude, "firmware writes through a stale ARM private pointer"
as the corruption path. The reset source (firmware/ARISC watchdog, hang,
or stray reset-register write) is not established. IRQ remains unqualified
and default-off.

Raw output: `local/recovery/2026-11-14-cpucomm-handoff/witness-256k-run/`.

## Root cause of the corruption signature — firmware exception recursion

The silent-reset run also damaged the root filesystem. Inode-table block
1962 (inodes written during boot `db484cbe`) carries `{0x8baa0000,
0x8b15bd44}` at offsets 16/20 of every 32-byte stride, which read as one
little-endian u64 is `0x8b15bd448baa0000`: the value in every IRQ-trial
kernel fault address.

In the pinned firmware (`display.bin` SHA-256 `4380f1b3…`, matching the
board), the general exception vector `EBase+0x180` (`0x8b101180`) jumps to
the "Display Dump" fatal handler `0x8b15bd28`. That handler pushes a
32-byte frame (`s0` at +0x18, `ra` at +0x1c), disables interrupts and calls
the register saver `0x8b15bbd8` with `lui s0,0x8baa` in the delay slot
(`ra = 0x8b15bd44`). The saver stores every register to `0x8ba99dc8`, then
executes `sw $k1, 0x8a($k0)` at `0x8b15bc70`: a misaligned word store. That
raises an address error, re-enters the vector and the handler, and pushes
another identical frame. The recursion never ends; the firmware stack pointer
walks down through physical DRAM, writing the pair every 32 bytes into Linux
memory. Page-cache pages dirtied at the time reach disk.

The kernel faults, the silent reset and the disk damage are therefore
consequences of a **firmware fatal exception** under IRQ-mode traffic. They
are not an ARM-side memory-safety bug, which is why the witness saw no write
and SLUB reported nothing first. The first exception is still unknown. With
`Status.EXL` set, nested exceptions do not update EPC, so the saver's EPC slot
(ARM `0x4ba99e50`) should still hold the original faulting PC after a crash.

A one-shot U-Boot halt (`witness-uart/uart.py`, armed by a file) was verified
with a SysRq reset: firmware runtime state survives into U-Boot.

Filesystem repair (operator-approved): emergency read-only remount,
`e2fsck -fy` (43 fixes, only inodes 26769–26779), clean recheck, reboot.
e2fsck had grown the damaged files to 9.5 TB sparse through stomped extents,
so they were deleted. `/usr/lib/h713-hdmi/h713-hdmi.cmd` was restored from the
identical health copy (`a9161a86…`). Both bundle SHA256SUMS, the CPU_COMM
module (`abb731ff…`) and the FAT FIT/script verify; the board runs normal 0202
polling with no failed units. Further IRQ crash trials should keep root
read-only during traffic.

### Crash capture with the U-Boot halt (boot `05d676ab`)

Root was read-only and the halt armed. The board crashed in the four-client
phase after 3 + 600 serial calls; an IOMMU page fault (`0xff43c000`, master
2, read) preceded the reset. U-Boot halted with firmware DRAM intact:

- The recursion pattern covers the dump handler's own code and the
  **BG-Task0** stack.
- The register saver's area is all zero: its kseg0 line never left the
  MIPS data cache, so the original EPC cannot be recovered from it.
- The witness window differs only by seven single 1→0 bit flips (DRAM
  decay across reset): no peer writes, again.
- The first handler frame gives the faulting context: `s0 = 0x8b1f0000`,
  `ra = 0x8b123e00`, `sp = 0x8b954558`. That is the BG-Task0 CALL
  dispatcher just after its routine lookup (`jal 0x8b11c5e8`); its stack holds
  the copied CALL (routine `0x24b17fb7`, zero parameters). The code between
  that return and the next call only touches the stack, so the exception is
  not a bad task instruction. The RTOS current-context pointer equals
  `sp − 0xa0`, the interrupt vector's frame, which points to a corrupted
  interrupt return or an interrupt-nesting fault in the vector at
  `0x8b101a00`. This is a lead, not yet established.

Booting on from U-Boot after this crash hung the kernel at 1.79 s and
required an operator power-cycle. Normal 0202 files were already restored.
After the power-cycle the board runs normal 0202 polling (boot `185817b0`).
A read-only `e2fsck -fn` is clean: keeping root read-only during the crash
kept the disk intact. Bundles, module and FAT files verify; three polling
calls pass.

### Interrupt-path analysis

A correction to the lead above: the RTOS context pointer is stale (its
frame's saved Status reads zero, and the area holds the routine lookup's
saved registers). This was not a corrupted interrupt return. Static review of
the pinned firmware found:

- The interrupt vector (`EBase+0x200` → `0x8b101a00`) is internally
  consistent: interrupt-stack switch at nesting zero, frame published for
  task switching, EPC/Status restored under `di`. One oddity is harmless
  here: it derives the new Status from the saved Cause register.
- Every runtime `mtc0 Cause` is a read-modify-write of software interrupt
  IP0 that preserves `Cause.IV`. Interrupts are not being misrouted to the
  fatal vector.
- The firmware's msgbox send (`0x8b12199c`) waits while the target FIFO
  holds eight messages before writing, so a full FIFO cannot fault.

Because the faulting window contains only stack accesses, the most plausible
trigger is an **imprecise (asynchronous) data bus error** from an earlier
store. Its source cannot be identified from DRAM: the dump handler's saved
EPC/Cause/BadVAddr never leave the MIPS data cache.

Proposed next diagnostic, an in-RAM firmware patch applied by the startup
script like the existing trace hooks:

1. Change the misaligned `sw $k1, 0x8a($k0)` at `0x8b15bc70` to an aligned
   free slot (`0x94`). This ends the recursion, so the firmware parks in its
   own dump loop instead of overwriting DRAM, and Linux survives.
2. Point the register save area at its uncached alias (`lui a1, 0xabaa` at
   `0x8b15bbd8`). The faulting EPC, Cause and BadVAddr then land in DRAM,
   readable from Linux at `0x4ba99dc8`.

The patch is implemented as a bench tool, `tools/mips/fatal-dump-patch.py`.
It writes the two words through `/dev/mem` into the no-map firmware
reservation after boot, after checking six guard words and the original
instructions, and it reads them back. `--restore` reverts the patch, and a
reboot reloads the pristine firmware. `--read` decodes the save area: GPRs,
Status, Cause exception code, EPC and BadVAddr. Both patched sites are
reachable only from the fatal handlers, so no stale instruction-cache copy
can exist. Host tests pass; on the board, the live firmware matches the
guards and the originals. The patch has not yet been applied in a trial.

## Root cause found — U-Boot comm-trace trampolines use `$k0`/`$k1`

With the fatal-dump patch applied (boot `4f3feb55`), the first firmware fault
was preserved: **EPC `0x8b1004c8`**. That address is not stock firmware code.
It is a comm-trace trampoline that our U-Boot (`h713_mips.c`,
`h713_mips_comm_trace_patches[]`) installs at `0x8b1004c0` for marker
`0xa002` ("release semaphore acquired"):

```
lui  $k0, 0xad98          # trace page (uncached)
ori  $k1, $zero, 0xa002
sw   $k1, 0($k0)          # <- EPC
j    <original>
```

`$k0`/`$k1` belong to exception handlers. The firmware's interrupt exit loads
them with the saved Status and EPC immediately before `eret` (`0x8b101c2c`,
`0x8b101c30`). An interrupt landing between the `lui`/`ori` and the `sw`
therefore turns the store into a write to a Status-valued address. The fault
enters the fatal dump, the dump recurses, and the runaway stack overwrites
DRAM. IRQ-mode reception makes MIPS interrupts denser, so it hits this
two-instruction window far more often. Polling has the same race, just rarer.
(The captured Cause, TLBL with BadVAddr `0xc`, comes from a later nested
fault; EPC is not updated under EXL.)

Several CALL/RETURN marker trampolines (`a0xx`, `b0xx`, `a105`, `d002`) share
this pattern. Newer hooks in the same table already save `t8`/`t9` on the
stack. The fix is to give the task-context markers that treatment, or to drop
them. This is a U-Boot proper change, and production startup gates read the
trace page.

Even with the recursion fixed, the parked dump handler re-faulted while
printing and corrupted Linux memory 10 s later
(`8ad3e7a48b1fcc84`). The board then reset, and its warm launch stopped at
U-Boot.
After the power-cycle the board runs normal 0202 polling (boot `129444a2`); a read-only fsck is clean.

### U-Boot fix prepared — `patches/u-boot/0006`

`0006-h713-comm-trace-markers-avoid-k0-k1.patch` rewrites the 155 comm-trace
cave words that used k0/k1 to use t8/t9 (52 `lui`, 51 `ori`, 52 stores). It
narrows trace relocation to t8, with counts unchanged at 61/80, and makes the
apply loop refuse any cave word naming k0/k1. A liveness checker proves t8/t9
are dead at all 61 hook sites in the pinned firmware, and it does flag live
registers when asked to watch them. A table diff test confirms only the
register fields changed. The full DDR3 U-Boot build passes, and the image
contains the new marker words and none of the old `0xa002` encoding. Only the
comm-trace table is used by the production launch. **Not installed yet**: it
needs the U-Boot proper install procedure, then an IRQ-mode qualification
run.
U-Boot 0006 install prepared: `local/recovery/2026-11-15-uboot-0006/RUNBOOK.md` (reproducible baseline matches the board's proper byte for byte; candidate differs only in the U-Boot image; board preview PASS).

**Installed 2026-11-15.** The 0006 proper (`24d25285…`) and the 0006-aware
`read-comm-trace.py` (`0f8194cf…`, guarded by `tools/hdmi/install-comm-trace-reader.py`)
are on the DDR3 bench. A cold boot takes the normal startup path with all HDMI services
and the health acknowledgement succeeding. The first warm boot exposed the
reader's old adapter-return pin (prepare failed); after fixing it, the board took the
designed GP6 fallback once, as intended. IRQ-mode qualification is next.

### IRQ qualification on U-Boot 0006 — PASS (one run)

On the production stack with only `rx_irq=1` (root read-only, fatal-dump safety
patch armed): 3 + 600 serial + 4×150 concurrent + 8×600 serial = **6003 calls, all
completed**. There were 12006 RX messages by IRQ and none by polling, with no TX desync. No firmware
fault was recorded, and there were no kernel faults or corruption signatures; the read-only fsck is clean. The
previous setup faulted within 74–2037 calls. This is one warm-boot run: repeat it after
a cold boot before deciding whether IRQ reception becomes the default.

**Cold-boot repeat — PASS.** It produced the same results after an operator cold cycle (boot
`475220c5`): 6003 calls completed, 12006 RX by IRQ, none by polling, no fault or
corruption. IRQ reception on U-Boot 0006 is qualified on warm and cold boot. It
remains opt-in (`rx_irq=1`); changing the default is a separate decision.

### 0205 installed — IRQ reception by default (2026-11-15)

FIT `ed111cb3…`, module `137d93c4…`, installed with the guarded kernel-FIT
installer. On a warm boot the normal startup completes, all HDMI services and
the health acknowledgement succeed, and CPU_COMM registers IRQ-only by default
with the pre-0006 guard silent.

A short stress run on the plain default stalled after 238 calls (CALL_ACK
timeout, sends quarantined until reboot). The firmware log was at level 5 with
its 2 MiB buffer exactly full, which triggers the synchronous UART flush
described above. That limit affects polling equally. After `elog -l 2` the same
run passes (3 + 600 + 4×150, 2406 IRQ RX, no desync). **Open:** set the firmware
log filter at startup so heavy CPU_COMM traffic cannot hit the flush.

### Firmware log filter set at startup (2026-11-15)

`h713-mips-elog-level.service` runs `mips-shell.py --elog-level 2` once after
`h713-hdmi-prepare`/`h713-hdmi-capture`. The action pins the firmware `elog` handler,
requires an idle shell ring and the exact 21-byte reply, and reads back the
filter byte at `0x4b48bdb0`. It is part of the release overlay and installed on
the board with `tools/hdmi/install-elog-level.py` (shell `5d0dd84e…` → `d7e505bb…`,
manifest `5652cf77…` → `06674f3a…`).

Warm boot `06fc390d`: the unit started 16 ms after prepare exited and logged
`before 5 → level 2, verified` within 1.9 s. The system is `running` with all HDMI
services and the health ack active. On the plain default configuration (IRQ, no
manual step), 3 + 600 serial + 4×150 concurrent + 1200 serial = 2403 calls all
returned rc 0, with 4806 RX by IRQ and 0 by polling, `tx_desynced=N`, and no
CPU_COMM warnings. The previous run stalled at call 238. **Closed.**
