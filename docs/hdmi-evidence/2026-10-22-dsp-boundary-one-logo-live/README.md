# DSP boundary one-logo run — October 22, 2026

**Terminal result: inconclusive. The first pre-AudioTop device-0 version
attempt timed out with DSP status `00000010`; no completed version was read.
Board ended in orderly poweroff.** The planned AudioTop writes and later
version pairs were not executed. The no-logo arm was not run because its
prerequisite—qualifying pre-AudioTop responses in the one-logo arm—failed.
[Design and stop rules](../../hdmi-dsp-boundary-design-2026-10-22.md).

## Captured path

| Point | Observation / evidence |
| --- | --- |
| Fresh cold production | Boot `013a628c-db47-4614-b89e-d663d4f9b2b2`; one cold SPL/GP6 zero, original bootcmd; active capture/signal/speaker, both TV domains ON; DSP `0000/0000` → pinned 724-pair patch verified `1/1` ([baseline](cold-census.json), [UART](cold-production-uart.log)) |
| Bundle staging | Boundary FIT and all bundle hashes verified; existing bench guard and exact original backup/mode verified; guard unchanged ([record](stage-verification.json)) |
| Orderly warm reset | Boot-ID/owner-checked reset, one warm SPL, GP6 magic retained, MIPS parked ([request](orderly-reboot-request.txt), [catch](warm-catch/serial.log)) |
| Pre-logo | Bus-only opening, both domains `00010000`; no domain power command ([census](warm-prelogo/census.json)) |
| One warm logo | Exact success marker and parked MIPS captured; lamp left off ([UART](warm-logo.log)) |
| RAM diagnostic | Exact candidate FIT, hook/image transfer checks and embedded DT; warm boot `5b3937e4-fc0a-47c9-8fe0-cd701e4eafd6`, `6.18.38 #4`; hold eligible/applied, no TVFE power command, disabled display/CPU_COMM, inactive HDMI services ([loader](ram-boot/preboot.json), [health](warm-health.txt), [bound arm](arm-proof.json)) |
| Clock/reset setup | All receiver/audio/display clock steps/readbacks passed. Demod bus reset initially asserted and released; display/TVCAP resets already released (both initial status 0). All seven routing words inherited exactly; write mask 0 ([snapshot 47](board-export/snapshot-47.json)) |
| AudioTop census | Control/config `0/0`; no AudioTop writes by the warm observer ([snapshot 47](board-export/snapshot-47.json)) |
| Locks | Peer/own sampled `0/0`; stock ARM `0x55` claim passed readback and peer checks ([snapshot 50](board-export/snapshot-50.json)) |
| Before request | Step 51 DSP status read completed with `00000000` ([snapshot 51](board-export/snapshot-51.json)) |
| Device 0 attempt | Step 52, 342.724–342.780 s: timeout latched, outcome 2, last status `00000010` (busy bit 4 set, done bit 5 clear), raw response remains unknown sentinel `ffffffff` ([snapshot 52](board-export/snapshot-52.json), [exact-boot journal](warm-kernel-journal.txt)) |
| Required terminal sequence | Step 53 marked device 1 skipped, outcome 3; no device-1 command. Step 54 ARM lock release/readback passed; step 55 final health/released-lock check passed. Hold 1; violated/failed/claimed 0; timeout 1; ledger certain ([snapshot 55](board-export/snapshot-55.json), [ledger](board-export/ledger.json)) |
| Shutdown | Fresh-ID/state/owner-checked orderly poweroff. Guard retained-hold notice and `reboot: Power down` at 436.198947 s; passive recorder closed ([request](end-poweroff-request.txt), [continuous UART](steps-uart.log)) |

Steps 1–55 each have one ordered UART BEGIN/DONE. Step 52's DONE means the
bounded observer operation recorded a timeout, **not protocol completion**.
There is no step 56 or later, no setup-as-recovery, no retry, and no second
warm reset. Step calls within a stage were separate helper invocations,
chained to stop on nonzero exit; stage snapshots were reviewed before each
required acknowledgment. A host deadline also prevented waiting indefinitely
on a stalled helper; it did not fire. No generic warm devmem census ran.
[Verification](verification.json) checks the terminal state and raw sequence.

The observer records the final timeout status but does not distinguish its
initial busy wait from its post-command done wait. Therefore this evidence
bounds device 0 to **at most one command write**; it does not prove whether
the command was published before the timeout. The prior idle sample was at
328.466 s, not an atomic trace of the subsequent request. No version should
be inferred from either the status word or unknown raw response.

## Meaning and next diagnostic requirement

[Analysis](analysis.json) correctly reports `inconclusive`, all four pairs
null and no first observed version change. With the verified held-domain,
clock, routing and lock conditions, the pre-AudioTop path failed to produce
a completed response. Keeping TVFE ON and proving writable lock backing
are insufficient to qualify that observation path.

This does **not** locate patch loss in reset, warm logo or AudioTop setup,
and does not supersede the previous completed post-setup `0/0` result. It
neither proves that AudioTop setup erases the patch nor that reset did so.
The new DT also disables display/CPU_COMM, so this run is not an isolated
AudioTop comparison against the previous live run.

Next work needs a separately prepared interface-qualification/control
experiment: record busy-wait versus command-sent/done-wait phases, then find
the minimum known AudioTop setup needed for a first completed request in a
**new cold cycle**, without retrying a failed request or adding setup after
timeout. A no-reset patched positive control would be needed to attribute
loss to setup rather than merely make an unreadable interface usable. Do
not simply repeat this pre-setup request in a no-logo boot. No such next
candidate or additional hardware trial was performed here.

## Final board and host state

Board is orderly powered off; lamp was kept off. The diagnostic DT disabled
the display driver, so its usual panel-shutdown callback did not execute.
**Physically disconnect board power and leave it off before another trial.**
No UART reader/catcher remains armed.

The boundary bundle remains staged separately at
`/root/hdmi-dsp-boundary-2026-10-22/`, including the boot-bound arm proof.
Normal FAT FIT/startup script/environment/bootloader were unchanged. The
bench shutdown guard remains installed, SHA-256
`5ad26677ac791d2be659db88165d689d997705f45ee4d516015e786342ad764d`.
Its original mode-0755 backup remains at
`/root/hdmi-dsp-retention-2026-10-21/previous-hold-guard`, SHA-256
`96f37655b33bf78d95b33fa4f431721be5a7506c73c12dcd4df58032cad27113`.
Restore only after a fully disconnected cold normal boot, retain flag absent,
and both hashes verified. The warm observer issued no source3 relaunch, DSP patch/graph operation,
reset assertion or GP6/GP7 write. Production warm-recovery policy
remains unchanged. Board wallclock reset to April; boot IDs and monotonic
UART/journal times identify this October 22 host-captured experiment.
