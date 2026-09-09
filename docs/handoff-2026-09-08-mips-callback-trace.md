# Handoff to Claude: MIPS callback trace, 2026-09-08

## Start here

We continued from `handoff-2026-09-06-composition-block.md`, testing whether
bounded ring progress and SetSource would make firmware service a corrected
frame. Neither experiment established that. We then instrumented the exact MIPS
firmware through a temporary U-Boot diagnostic patch table.

**Latest finding:** the detector callback and CheckSignal ran during bring-up,
but their counters were frozen throughout the Linux experiment. SetSource
still reached its RPC adapter and HAL with argument 1. Find where callback
progress stops before trying another composition-register workaround.

**Recovery is complete:** original second-stage bootloader restored and verified
byte for byte; installed SPL never changed. Normal Linux 6.18.38 and SSH work.
MIPS reset register `0x0306101c` reads zero (parked), as expected at default boot.
The diagnostic hooks are not active now. MIPS/DECD do not start in the required
test configuration by default; this is intentional, not a failed cold boot.
No final screen improvement was established. User previously reported blank screen.

## What we did

1. **Bounded ring writes, September 6.** Brought MIPS up explicitly, booted the
   test kernel, submitted using corrected `decd-client.coord1080` with budget 1,
   then allowed four additional writes (counter 1 to 5). Board survived, but
   composition was already at the correct values and did not change. AFBD still
   had 1920-wide/0x780-stride and IOVA-under-bypass problems. This did not reproduce
   the original 852x480 composition mismatch or prove frame service.
2. **SetSource, September 8.** Fresh bring-up, one frozen ring write, `dtv get_fb`,
   then `THal_Vp_SetSource_1_000(1)`. RPC returned successfully (~75 ms, nret=0),
   but composition/AFBD and sampled detector state did not change.
3. **Static dispatch investigation.** Located the registered callback thunk,
   CheckSignal, message manager, and SetSource adapter/HAL. Corrected two earlier
   assumptions: `dtv get_fb` parses into a caller-owned buffer, and ARM reads of
   cached MIPS globals cannot establish whether firmware changed them.
4. **Trace preparation and failed volatile installation.** Generated eight
   register-preserving hooks, checked in 32 paired Unicorn cases. Writing the
   resident U-Boot table faulted on a read-only mapping. A cache-disable/copy
   helper also faulted before copying; board auto-recovered both times. Do not
   retry `tools/mips/event8-table-copy.S`; it is marked FAILED / DO NOT RUN.
5. **Authorized temporary second-stage flash.** Backed up installed SPL and
   second stage to board and host; verified second stage matches the reference
   image. Changed only its diagnostic patch table, flashed/read back, ran
   `h713_disp mips-comm-trace 0x34`, and reached application readiness. Booted
   the test kernel and ran the bounded frame/SetSource experiment.
6. **Restored and verified original bootloader**, then booted normal Linux and
   verified SSH and parked MIPS. Exact recovery copies and logs are retained.

## Latest measurements and limits

| Sample | event8-filtered dispatch | callback | CheckSignal entry / return | last result | RPC / HAL |
|---|---:|---:|---:|---:|---:|
| U-Boot after readiness | 0 | 997 | 997 / 997 | 0 | 0 / 0 |
| First Linux sample | 0 | 3928 | 3928 / 3928 | 0 | 0 / 0 |
| Linux idle +2 s | 0 | 3928 | 3928 / 3928 | 0 | 0 / 0 |
| One corrected frame | 0 | 3928 | 3928 / 3928 | 0 | 0 / 0 |
| SetSource(1), immediate and +2 s | 0 | 3928 | 3928 / 3928 | 0 | 1 / 1 |

HAL captured source=1. RPC took 75,537 microseconds. Ring stayed at 1/1.
Composition and AFBD snapshots before/after RPC match exactly.

Do not overstate this:

- First Linux sample was **after replacing DECD and loading CPU_COMM**. We have
  not localized the stall to Linux itself, a specific driver, or even bootm.
- Nonzero callback counts prove earlier execution, not continuing Linux polling.
- Last CheckSignal result zero does not mean all historical returns were zero.
- Event8-filtered dispatch count zero conflicts with the assumed callback route.
  Another route or incomplete instrumentation coverage remains possible. It does
  not establish that the event producer is dead.
- Successful RPC shows the entire MIPS core is not stopped.
- No IRQ/timer/vsync identity for event8 has been established.

## Next steps for Claude

1. Inspect the generator and firmware call paths. Explain the zero event8 count
   despite callback progress. Extend the callback hook to capture original `$ra`
   and message ID (verify ABI/readable pointer first), and count all DoMessage
   entries as well as event8. Preserve displaced instructions and all registers;
   extend the emulator checks. Keep uncached KSEG1 counters and bounded sampling.
2. Establish whether callbacks keep advancing **while remaining in U-Boot**:
   sample twice a few seconds apart, then again after a longer bounded interval.
   This separates a time-dependent firmware stall from a Linux-triggered one.
3. If U-Boot progress persists, sample at Linux milestones **before automatic
   DECD probe**, after probe, after module replacement, and after CPU_COMM load.
   The existing test kernel auto-loads DECD, so sampling only after SSH comes up
   repeats our blind spot. Inspect how it is loaded and arrange an early sample
   or a boot that defers that load; do not assume the AFBD blacklist disables DECD.
4. Once the first failing boundary is known, compare the clocks, interrupts,
   resets and shared state affected there. Keep frame submission out of that
   first localization run; then add one budgeted frame once baseline is understood.
5. Return to the composition/AFBD mismatch only after proving frame-service
   progress. Avoid inferring service from ring-write count or debug parsing alone.

## Reproduction and access

Workspace: `/home/chris/Projects/h713`. Board: `root@192.168.4.1`.
Use `ssh -F /dev/null` / `scp -F /dev/null` (host SSH config has an ownership
error otherwise). Serial is `/dev/ttyUSB0`, 115200; `/dev/ttyACM0` is monitor
controls, not the board console. Network/serial commands required sandbox
escalation in Codex. No need to change board startup defaults.

From normal Linux, the established controlled bring-up is:

```sh
python3 tools/serial/reboot-to-uboot.py /dev/ttyUSB0 18
# At the U-Boot prompt, ordinary uninstrumented bring-up:
python3 tools/serial/console.py --port /dev/ttyUSB0 --wait 2 'h713_disp init 0x34'
# For a newly deployed trace table, use mips-comm-trace instead of init.
python3 tools/serial/boot_kernel.py --load /root/fits/h713-kernel-decd-iommu-0076v3.fit --extra initcall_blacklist=h713_afbd_platform_driver_init --secs 25
```

Run only one MIPS initialization per boot; do not re-release a quiesced core
with direct MMIO. Start a fresh boot for another run. Inspect readiness output
before booting Linux. Warm reboot from default Linux worked in these tests.

The Linux test setup used:

```sh
rmmod sunxi_decd
insmod /root/sunxi-decd-budget.ko ring_writes_max=1
insmod /root/hy310-cpu-comm-next.ko
sh /root/event8-experiment.sh
```

The last script is retained on board and in the evidence directory below.
It samples idle, submits `/root/decd-test-frame.nv12` using
`/root/decd-client.coord1080`, invokes `dtv get_fb`, calls
`/root/cpu-comm-probe THal_Vp_SetSource_1_000 1`, and samples again. It asserts
initial ring count zero and freezes at one. **It assumes hooks are installed;
normal boot has none.** Do not use it unchanged for early-boot localization.

## Firmware and trace anchors

Exact raw image: `local/mips-display/board-b-mips/display.bin`, base `0x8b100000`.
SHA-256: `4380f1b3ed7b62aa50582e7cb16a87bdface1b4300578fe3631a416354da30ce`.
Use `tools/mips/disasm.py`; confusing the base with 0x8b101000 previously produced
wrong function interpretations.

- THidTVPro singleton pointer: ARM `0x4b27266c`; observed MIPS object `0x8b83084c`.
- Callback secondary object: self+0xbc, vptr `0x8b1f8c28`; slot+c thunk
  `0x8b147678` jumps to `0x8b147390`, subtracting 0xbc from a0 in delay slot.
- CheckSignal: `0x8b147dd0`; return sites `0x8b147ee4`, `0x8b147f34`, `0x8b147fbc`.
- GetFrameInfo: `0x8b147834`, copies 144 bytes to a1. Debug command uses stack;
  CheckSignal uses detector+b0 and latches +140.
- Message manager DoMessage: `0x8b156bf8`; callback virtual call `0x8b156d28`.
  Enable registers event8 via `0x8b146e34`; manager details are in dispatch report.
- SetSource adapter `0x8b10a218`; HAL `0x8b14b448`; nret=0 is expected.
- Trace words ARM `0x4e340080..9c`: event8, callback, CheckSignal entry, return
  count, last result, RPC count, HAL count, last source. Written through MIPS
  KSEG1 `0xae340000`. Non-atomic 32-bit counters; do not clear while live.
- Generator: `tools/mips/event8-trace.py OUTPUT_DIR` (needs capstone/unicorn in
  the workflows; emulator checks do not model hardware cache or scheduling).

## Flash layout and recovery artifacts

Follow `tools/boot-switch.sh` / `docs/flash.md` for layout. Installed second stage
is at LBA 4828160 (`0x49ac00`) on `/dev/mmcblk0`; SPL at LBA16, 64 sectors.
Only 1790 second-stage sectors were temporarily changed, preserving tail bytes.
**Installed SPL differs from the reference combined image; never replace it
merely to deploy this table.** Vendor boot chain and environment were untouched.

Evidence directory: `docs/reference/event8-instrumented-2026-09-08/`.
Recovery copies are also `/root/event8-original-{spl,proper}.bin` on board.

- Original padded proper SHA-256:
  `b65bd629c43fc48034a7e32e686bbc735b2e7067f56cd6b77da6eddf75fde208`
- Original installed SPL SHA-256:
  `cb9da87448a57aa1cafbc7ebf66200b5183304cef1eafe23d0818b99696a49ec`
- Temporary padded proper SHA-256:
  `4e11fb9d748a0711a88b16bb848b4705424f7113ffa2756c8a5b8bf1e66aa0a6`
- Combined diagnostic image: `build/out/u-boot-sunxi-with-spl-event8-trace.bin`,
  948841 bytes; only table at combined offset 0x999b4 (6256 bytes) differs from
  `u-boot-sunxi-with-spl-frame-trace.bin`. Do not flash its SPL.

The current trace replaces the old diagnostic table entirely. U-Boot still
prints the old “CPU_COMM RETURN progress trace installed” message; use the
actual generated table/counters to interpret results. Original table is retained.

## Evidence map

- [Latest measured result](reference/event8-trace-result-2026-09-08.md)
- [Raw latest experiment, backups, hooks and recovery logs](reference/event8-instrumented-2026-09-08/)
- [Static dispatch analysis](reference/dispatch-trace-2026-09-08.md)
- [Earlier SetSource experiment](reference/setsource-result-2026-09-08.md)
- [Bounded ring experiment](reference/composition-budget-result-2026-09-06.md)
- [Failed volatile deployment history](reference/event8-instrumentation-status-2026-09-08.md)
- [Original composition handoff](handoff-2026-09-06-composition-block.md)

Several reports/scripts are untracked and older reports have corrections; no
commit was made. Preserve these working-tree artifacts when switching agents.
Treat earlier causal claims in the September 6 handoff as hypotheses to reconcile
with these later measurements, not as confirmed explanations of every run.
