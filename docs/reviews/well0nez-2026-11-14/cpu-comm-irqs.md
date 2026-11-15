# CPU_COMM IRQ trials — November 14, 2026

**Historical IRQ trials; IRQ-driven operation is not qualified for production.**
Follow-up [shared-memory handoff investigation](cpu-comm-handoff.md) fixes
independent corruption paths and reproduces the approximately 240-call
stall in a matched-length polling test. The original short polling
comparison below cannot isolate IRQ timing. Restoration statements here
describe the end of this initial trial, not the later candidate state.

**Initial result.** The corrected
mapping delivered full round trips with no polling, but concurrent calls
subsequently timed out, and a repeat IRQ boot suffered kernel memory
corruption. The DDR3 bench was rolled back to its previously qualified
FIT/startup-script/CPU_COMM-module pair and verified healthy. The review
patch keeps polling as the default; no trial candidate remains installed.

## Changes prepared

- **0198**, attributed to well0nez's pinned 0024d: CPU_COMM lists stock
  SPI **46/109/108**, in ARM/ARISC/MIPS bank order. Watchdog changes from
  the conflicting SPI 46 to stock SPI **53**. The 0x1000 register mapping
  remains unchanged. Both compiled board DTBs were checked for exactly
  these two property changes.
- **0199**, our adaptation of well0nez's 0014b/0014c ownership analysis:
  preserve the existing bank-0-only request, retaining a sleepable ONESHOT
  threaded handler. Mask only MIPS-to-ARM RX BIT(2), drain in the thread,
  acknowledge that endpoint, then re-enable it. Do not request remote
  inbox IRQs or clear unrelated RX/TX status.
- Successful opt-in IRQ registration starts **no polling timer**. Explicit
  `rx_irq=false`, absent IRQ, or registration failure selects polling.
  Read-only `rx_irq_active`, `rx_poll_active`, `rx_messages_irq` and
  `rx_messages_poll` expose actual operation. The old exploratory
  `rx_irq_en` override is removed; the known endpoint bit is used.
- Teardown masks RX both before and after `free_irq()`: a running thread
  can re-enable it while `free_irq()` waits. A source-extraction regression
  simulates that race.
- Guarded bundle/install tooling supports only the exact msgbox/watchdog
  DT change and a baseline-reproduced `hy310-cpu-comm.ko`, with the module
  in the same backup/readback/rollback scope as the FIT and script.

Pinned source attribution is retained in both patch headers. No import of
well0nez's direct hard-IRQ callback is made: our callback takes semaphores.
The old storm on GIC hwirq 53 used **SPI 21**, not the correct **SPI 46**.
Linux IRQ numbers below are dynamically allocated and are not SPI numbers.

## Host verification

The final review source retains IRQ **opt-in**, unlike the temporary test
builds that enabled it by default for qualification.

- Full production kernel/module build: pass, LLVM 23.1.4, release identity
  and epoch matching the installed baseline.
- Baseline FIT and CPU_COMM module reproduced byte for byte. Configuration,
  kernel release, and Module.symvers match the candidate.
- Seven bundle-builder tests and fifteen installer tests pass, including
  CPU_COMM rollback, injected activation failure restoration, baseline
  drift refusal, and refusal of unrelated or misordered DT changes.
- Extracted real handler/registration/teardown helpers pass ASan/UBSan
  checks for endpoint ownership, mask/drain/ack/unmask order, IRQ-only mode,
  explicit/missing/failed-IRQ polling fallback and teardown races.
- Both DDR3 and LPDDR3 DTBs pass the narrow canonical DT comparison.
  This is not LPDDR3 hardware qualification.

The final source-only review bundle metadata is in
[cpu-comm-irq-validation.json](cpu-comm-irq-validation.json). Its CPU_COMM
module was built but **not installed** following the failed trials.

## Bench results

Board: HY200 QZ713DF_A1, DDR3, kernel 6.18.38. Calls used the existing
`/dev/cpu_comm` CALL ioctl and firmware's `THal_Vp_GetSignalInfo_1_000`
control routine (`0x24b17fb7`), zero parameters. This is a transport/control
stub test, not qualification of a real signal-information implementation.
Each completed call returned zero; kernel logs show CALL, CALL_ACK, RETURN
and RETURN_ACK. No firmware was replaced for these tests.

| Trial | Boot | Result |
| --- | --- | --- |
| Original polling control | `2f81b106` | Three calls pass |
| Preliminary IRQ-only | `18960819` | Three initial calls plus 200 serial calls pass; 406 RX messages by IRQ, zero by polling |
| Four concurrent IRQ clients, 50 calls requested each | `18960819` | **Fail:** 37 calls complete, then all four clients report timeouts; 481 total IRQ RX messages, zero by polling |
| Polling-only comparison on final trial module | `caf1af7e` | Three control calls and all 200 concurrent calls pass; 406 RX messages by polling, zero by IRQ |
| Repeat final IRQ-only boot | `8a148120` | **Fail:** kernel paging faults and corruption during repeat-test attempt; no successful repeat qualification |
| Recovered original polling setup | `dbe874ad` | Three calls pass; startup check passes, running, no failed units |

On the successful preliminary IRQ run, `/proc/interrupts` names
`cpu_comm_msgbox` on Linux IRQ 333, **GIC hwirq 78 = SPI 46**. After the 200
serial calls it counted 398 interrupts; FIFO draining can consume multiple
words per interrupt. The spurious-IRQ record showed count 0/unhandled 0.
This establishes real IRQ delivery, not a polling backstop rescuing traffic.
It does not establish reliability under concurrent requests or repeat boots.

After concurrent failure, read-only MMIO inspection found RX enable 0x4,
RX pending 0 and RX FIFO count 0 at offsets 0x120/0x124/0x164. TX FIFO count
was also zero. A subsequent single call still timed out. No RX data FIFO
register was read by the diagnostic, so it consumed no messages. The polling comparison was shorter in total calls and could not isolate IRQ
timing. A later matched-length polling test also stalls; see the follow-up
report for the firmware UART logging backpressure evidence.

The repeat boot recorded kernel paging faults around uptime 35 seconds,
including `filp_close` and a V4L2 ioctl path, with mixed MIPS-looking pointer
words such as `8b15bd448baa0000` in kernel registers. SSH was unavailable and
serial SysRq sync/remount/reboot did not respond. The operator power-cycled
the board; UART then selected polling, followed by guarded rollback and a
clean baseline boot. The failed repeat-test file was not retained on disk;
the UART fault capture is the primary evidence for that attempt.

## Remaining investigation

well0nez's pinned **0014a**, around its `cpu_comm_sync_mips_cache()` addition,
describes a similar earlier MIPS-pointer/kernel-memory corruption while
processing messages too early, and its vendor reconstruction consumes the
publication flag before deferred dispatch. This is a lead, **not a proven
explanation** for our failures. Our existing callback already clears the
publication flag with a barrier, but dispatch is synchronous; copying the
other tree's flag loop alone would not prove coherency or lifetime safety.

Before another production IRQ proposal, investigate publication/snapshot
ordering, shared wait/return object lifetimes and deferred dispatch against
the actual firmware, then qualify repeated boots and concurrent calls.
A passing serialized run is insufficient. No speculative delay or automatic
poll rescue was added to conceal the observed failure.

## Restoration

Verified final boot: `dbe874ad-94f7-4472-8402-51b1235a18b4`.

| Restored file | SHA-256 |
| --- | --- |
| FIT | `22ee12d4bef763a6ee60e5c679e41262acfae19c2567b5c93abde3332e96cd83` |
| CPU_COMM module | `8244df26b0b3a8ea1c2f2234f8d7a761b60cf1e045b440d5e8f008e6808f4352` |
| Startup script | `79c039acb7e77087ec143f9f1214c877b5567a926f65c7a43a4b3a4ffc11badd` |
| Cedrus module, unchanged | `1c8c87bae78ad6fce0522faa89b37d02bda511af1535b669dcb655a85ce0d3f2` |

The temporary modprobe override was removed. Original saved environment hash
still equals `e6a56d4c6f2703c9360c29da4d1e1aec2d35bafd57bc6ca8232896e0296bc3ab`.
Startup's four IPC gates pass, health acknowledgement validates without a
write, and UART is released after capture. No SSD block device was present
at the final check after the operator power cycle; no CPU_COMM trial wrote
SSD data. This follow-up does not requalify USB enumeration.
The prior VP9/USB/PIO/HEVC candidate remains the installed baseline.

Raw UART, trial builds, per-client output, recovery commands and receipts
remain ignored under `local/recovery/2026-11-14-cpucomm-irqs/`. No firmware,
environment bytes, crash captures, commit, push or GitHub comment is included
in this follow-up. The local handoff points to the final recovery state.
