# CPU_COMM TX reservation and send errors — November 16, 2026

Kernel **0208** adapts the TX FIFO depth check from well0nez's pinned
[0014f](https://github.com/well0nez/allwinner-h713-linux/blob/149f51d0df24c45b12674c81aab128b1fc8f5d4b/mainline/patches/kernel/0014f-soc-sunxi-cpu-comm-never-write-into-a-full-tx-fifo.patch).
It is **installed** (module only) and **passes the warm-boot 6003-call
qualification**. The operator cold-boot repeat is pending.

## What was wrong

0014f reads the TX FIFO count without a lock and returns `-EBUSY` after the
caller has already set the message's SENT flag in shared memory. A refusal at
that point leaves a publication the peer may still act on. Our tree had the
same ordering with no check at all, and four further defects around it:

1. `SendComm2CPUEx` ignored `SendCommLow`'s return. Any refusal became a
   500-jiffy CALL_ACK timeout followed by the permanent `tx_desynced`
   quarantine.
2. `SendAckLow` set the ACK SENT flag before ringing the doorbell. If that
   word were ever lost, the next ACK on the sequence would find the flag
   still set and call `BUG()` in the receive thread.
3. Doorbells were not serialized. A CALL on one CPU and an ACK from the
   receive thread could interleave their data writes and TX_IRQ_EN pulses.
   If the receiver needs the edge, which is unsettled, one wake-up could be
   swallowed and a word left stranded.
4. A failed `copy_to_user` left its wait object on the active list. A caller
   passing a read-only buffer could exhaust the wait pool, after which
   `GetFreeWaitComm`'s `schedule()` loop never returns. Its call slot was
   also dropped from the cache and leaked.

### How reachable a full FIFO is

The ARM sends four kinds of doorbell word: CALL and RETURN (SENT at header
byte 8 of the dir-0/dir-1 write sequences) and CALL_ACK and RETURN_ACK (SENT
at byte 105). Each is held off by its own flag until the MIPS consumes it,
and the MIPS pops the FIFO word before it clears the flag. At most four
words are therefore in flight against a depth of eight. A full FIFO needs
leftover words, for example from repeated module loads while the MIPS is
parked. The depth check is defence in depth; the error paths above are the
substantive fix.

## Implementation

`cpu_comm_msgbox_send(type, publish, ctx)` replaces the old doorbell
function, which had no other users and was not exported:

- Under `msgbox_tx_lock`, read the TX count. The driver is the only writer
  and the MIPS can only lower it, so a count below eight reserves the word.
- Run `publish` (the shared header and its SENT flag), then write the data
  word and pulse TX_IRQ_EN, all before unlocking. The pulse is unchanged.
- If the FIFO stays full for 100 ms (sleeping 50–100 µs between checks),
  return `-EBUSY` without running `publish`. An unmapped msgbox returns
  `-ENODEV` the same way. Read-only `tx_fifo_full` counts refusals.

`SendCommLow` and `SendAckLow` move their header writes into `publish`
callbacks, so a nonzero return means nothing new was written. Both callers
already run in sleepable context: `SendComm2CPUEx` holds sleeping counter
semaphores, and ACKs are sent from the threaded IRQ or polling work.

Error handling:

- **CALL/RETURN send refused** — clear the pending ACK, remove and release
  the wait object (direction 0), keep the unpublished slot cached for the
  next send, release the sequence semaphore and return the error. Nothing
  was published, so there is no quarantine.
- **`copy_to_user` failure** — same unwinding. A partial `copy_from_user`
  restores the cached slot's index so the next send cannot hit the slot
  address `BUG()`.
- **Published** — only now is the slot handed to the peer (cache cleared).
  The ACK-timeout path is unchanged apart from sharing the wait-release
  helper.
- **ACK refused or previous ACK still published** — return an error, log,
  and quarantine sends to that peer, as for a missing CALL_ACK. The receive
  thread survives. A matched RETURN still wakes its caller, because the
  completion claim makes it ARM-owned. A late RETURN is recycled only after
  its RETURN_ACK was published.

## Host verification

`tools/mips/test-cpu-comm-tx.py` extracts the actual prepared functions and
compiles them with ASan/UBSan (`-fno-sanitize-recover=all`) and
pthread/MMIO stubs:

- **Doorbell.** Accepted sends publish before the data word and leave the
  pulse low. A permanently full FIFO refuses after the bound with nothing
  published or written. An unmapped msgbox refuses the same way. Four
  senders of 300 words each, against a slow simulated drain from a full
  FIFO, deliver all 1208 words with no overflow, no interleaving and every
  publication inside the lock.
- **Publication.** Refused CALLs and ACKs leave the 512-byte header
  byte-identical. A still-published ACK quarantines instead of `BUG()`.
  Accepted messages carry SENT and the 64-bit handle.
- **Sender unwinding.** For success, a refused send, `copy_to_user` failure,
  partial `copy_from_user` and ACK timeout, the test checks the return code,
  semaphore balance, pending-ACK clearing, wait add/remove/release counts,
  slot caching and reuse without a second free-ring take, and quarantine.
- **Late RETURN.** Recycled only when its RETURN_ACK was accepted.

`--mutations` requires 11 broken variants to fail, each on its intended
assertion (stable over three runs). The variants are: publish before
reservation, no capacity check, unlocked doorbell, ignored send result,
`copy_to_user` wait leak, cache cleared on failure, pending ACK left set,
slot index not restored, unquarantined ACK refusal, stale ACK overwritten,
and recycle without ACK. `--baseline` runs the 0207 tree's functions against
the same model and reproduces the full-FIFO write, the stale-ACK `BUG()` and
the `copy_to_user` wait leak.

`test-cpu-comm-handoff.py` now stubs the new transport, and passes on both
the 0207 and 0208 trees. The IRQ, spinlock and witness tests pass unchanged
on 0208. The module builds with `W=1` using clang 23.1.4 with no new
warnings (the one warning is the existing unused `prev_idx` in
`cpu_comm_rpc.c`). Checkpatch reports zero errors and zero warnings with
`--no-signoff`; `--strict` reports only CamelCase on existing names. The
patch applies with zero fuzz and reproduces the tested sources byte for
byte.

## Release build

The pinned release build (`build-release-kernel.sh`, clang/LLD 23.1.4,
production config, fixed epoch) applies all 170 series patches. Its
CPU_COMM sources match the tested scratch sources byte for byte. The
host tests above pass again against this release tree (`linux-6.18.38-7181c5f7a932cb9d5f3c905ebd4e5679672b3a903d16ada6876620106b19d009`).

Compared with the installed 0207 build:

- `.config`, `Module.symvers`, the kernel release and every DTB are
  identical.
- `CONFIG_HY310_CPU_COMM=m`, so the FIT is unchanged: it is
  byte-identical to the installed `845494c3…`.
- The only module that differs is `hy310-cpu-comm.ko`, now `9864701f4d4d…`
  (full hash `9864701f4d4d3cca545b8c932716f8902321252fafc5af4e56f27d91207fe35a`).
- The same build reproduces the installed `137d93c4…` module before 0208.

Installing 0208 therefore replaces one module and nothing on the boot FAT.

## Install bundle

The bundle builder and guarded installer gained an explicit **module-only
scope** (`build-kernel-fit-bundle.py --module-only`). Before this, the
builder refused a candidate whose FIT equalled the baseline. The installer
also could not represent the case: with identical baseline and candidate
script hashes, its state check would read a baseline board as "candidate".

In module-only scope, the builder requires an unchanged FIT, startup script,
configuration and board DTB, plus at least one changed, baseline-reproduced
module. The installer then treats the FAT FIT and script, both bundle script
copies and their `SHA256SUMS` entries as read-only preconditions pinned to
the installed hashes. It stages, backs up and rolls back only the module
files. Installer tests (22) cover:

- preview;
- module-only writes and renames;
- exact rollback;
- refusal when the FIT, FAT script or a bundle script differs from its pin;
- foreign module drift;
- eight manifest-widening variants;
- restoration after an injected rename failure.

Three installer mutants (dropped pins, wrong targets, unchecked scope) each
fail them. Builder tests (9) cover the FIT equality rules.

The 0208 bundle (`local/recovery/2026-11-16-cpu-comm-tx/bundle/`, manifest
`375f34a8…`) carries only `hy310-cpu-comm.ko` `9864701f…`. It pins FIT
`845494c3…`, cmd `41faabdc…`, scr `c565a05a…` and installed module
`137d93c4…`.

- **Offline rehearsal.** On a fake root built from the real installed
  bytes, preview writes nothing and apply changes only the module. Rollback
  restores the tree exactly.
- **Board preview.** On boot `75218eb8-0937-4f0b-85ca-30f5a6c3ceb3`, with
  the FAT mounted read-only and unmounted afterwards, the preview reports
  state `baseline` and would write only the module. The procedure is in
  that directory's `RUNBOOK.md`.

**Installed November 16, 2026** on the same boot, uptime about 2290 s. The
installer ran a fresh preview (`baseline`) and then `--apply`, with the boot
FAT mounted **read-only** so the transaction could not write it; it was
unmounted afterwards. The result is `candidate`. Verified afterwards:

- The on-disk module is `9864701f…`, vermagic `6.18.38 SMP mod_unload aarch64`.
- The FAT FIT is still `845494c3…` and the scr still `c565a05a…`, with no
  staged files left.
- Both bundle manifests verify, and the system is `running`.
- The committed backup is
  `/var/lib/h713-hdmi-startup/kernel-fit-b4d327c9ed554935bfe797dc23e4c39d`.
  It holds only the 0207 module `137d93c4…`.

The running module remains 0207 until the next boot; no module was reloaded.

## Warm-boot qualification — PASS

After a warm reboot into boot `0259a3cf-0770-4253-87a1-e8bfac16244f`, the
running module is `9864701f…` and `tx_fifo_full` is present and zero. The
startup checker passes, the acknowledgement dry-run writes nothing, both
manifests verify, no units have failed and ext4's error counter is zero.
The automatic log filter reports level 2, verified.

The existing qualification script, extended to pin the module hash and
require `tx_fifo_full=0`, completed all **6003 calls** on the default
configuration. The phases were 3 controls, 600 serial, 4 × 150 concurrent
and 8 × 600 serial. After every phase:

- the boot ID was unchanged;
- IRQ reception was active and polling inactive;
- `tx_desynced=N` and `tx_fifo_full=0`;
- the filter read 2 and the firmware fault-save magic was zero.

Final counts are **12006 IRQ RX, zero polling RX**, and the ELOG pointer
stayed at `0x5f284`. The kernel log contains no send-refusal, quarantine,
timeout or late-RETURN messages. The startup checker still passes after the
traffic.

The [validation summary](cpu-comm-tx-validation.json) holds evidence
digests; raw logs are in `local/recovery/2026-11-16-cpu-comm-tx/qual/`.

## Hardware qualification still needed

Repeat
the CPU_COMM transport runs from the
[IRQ qualification](cpu-comm-handoff.md#irq-qualification-on-u-boot-0006--pass-one-run)
on an operator cold boot (warm passed above): 3 + 600 serial + 4×150 concurrent
+ 8×600 serial calls, with `rx_irq_active=Y`, `rx_poll_active=N`,
`tx_desynced=N` and `tx_fifo_full=0` after every phase, IRQ-only RX counts,
startup health and no CPU_COMM warnings. A full FIFO is not reproduced on
the board: forcing one would need a parked MIPS or injected words, and the
host tests cover that case instead.

Private working state (scratch tree, release build and logs) is under
`local/recovery/2026-11-16-cpu-comm-tx/`.
