# CPU_COMM doorbell pulse — November 16, 2026

**Result: the display MIPS wakes on the FIFO write alone.** The TX_IRQ_EN
pulse our driver sends after every doorbell word is not needed while the
firmware is running. It enables an interrupt that the firmware never handles.
Kernel **0209** removes the pulse and narrows the 0014e whitelist; see
[0209](#0209) below.

This closes the question left open in the [review index](README.md): our
original edge-trigger claim was never established, and well0nez's 0014f
later retracted the same claim.

## Firmware evidence

From the production `display.bin`, disassembled with base `0x8b100000`
(self-test passed):

- **The firmware's own send** (`0x8b12199c`) computes the block's `+0x60`
  count and `+0x70` data registers, waits while the count is 8, then writes
  the data word. It never writes a TX-IRQ enable. Our ARM side receives
  every such message by IRQ (12006 per 6003-call run). A data write alone
  therefore wakes the receiver.
- **The firmware's msgbox initialization** (around `0x8b1217b0`–`0x8b1218e8`)
  works on the block we transmit into (`0x03003800`):
  - it clears its RX-IRQ enable bit 2 at `0x3820`;
  - it drains stale words via `0x3864`/`0x3874`;
  - it clears RX status bit 2 at `0x3824`;
  - it registers the LISR at `0x8b121698`.
- **Channel registration** (`0x8b121950`) then sets
  `0x3820 |= 1 << (2 * port)`, which is bit 2 for port 1, our FIFO.
- **The LISR** drains `+0x60`/`+0x70` and writes back RX status only.
- **The callback** (`0x8b122678`) dispatches the raw word as 0–3 and sends
  anything else to a log line and return.
- **No `+0x30`/`+0x34` use.** A scan of every `0x0300 3xxx` reference in
  the image finds only `+0x10`, `+0x24`, `+0x60`, `+0x70`, `0x3820` and
  `0x3864`.

## Live registers

On boot `41b98df8-d8eb-491f-aedf-3796ec5783d1`, the 0208 cold-qualified
image, read-only:

| Block | RX enable `+0x20` | RX status `+0x24` | TX enable `+0x30` | TX status `+0x34` | Port-1 count |
| --- | --- | --- | --- | --- | --- |
| `0x100` (ARM inbox) | `0x4` | `0` | `0` | `0xaa` | `0` |
| `0x800` (MIPS inbox, our TX) | `0x4` | `0` | `0` | `0xaa` | `0` |

The MIPS has port 1's RX interrupt armed. TX status is a latched "FIFO has
room" flag for every port. Our pulse sets `0x830` bit 3 for 10 µs, so it
briefly asserts that level interrupt on the MIPS, which the firmware never
acknowledges. It is a spurious extra wake-up, not the doorbell.

The earlier observation behind the original comment ("count went 0 → 1 and
the MIPS never drained it") fits a MIPS that was parked or had not yet
registered its channel: before registration its RX enable is clear.

## Board probe

`local/recovery/2026-11-16-cpu-comm-tx/qual/doorbell-probe.py` writes the
word `0x4` to `0x03003874` **without** a pulse and times the port-1 count's
return to zero. The firmware callback discards words of 4 or more, so no
CPU_COMM protocol state changes.

Before running, the probe requires:

- IRQ-only RX, no desync and no TX refusals;
- MIPS RX enable armed and TX enable clear;
- an empty FIFO.

A trial counts as clean only if the kernel's IRQ RX and refusal counters
did not move. The driver sends its pulsed words only in reply to RX, so an
unmoved counter means no pulsed send could have drained the probe word.

| Run | Trials | Clean | Drained | Latency (µs) |
| --- | ---: | ---: | ---: | --- |
| Slice writes | 20 | 20 | 20 | 35.4 / 51.7 / 149.1 (min / median / max) |
| Typed 32-bit writes | 20 | 20 | 20 | 19.4 / 36.0 / 1789.9 |

The first run's count sometimes read 2 straight after one write. Python's
`mmap` slice assignment goes through `memcpy`, which can store the 4 bytes
as two overlapping 32-bit stores. That pushed two ignored words. The rerun
uses single typed stores; the count then reads only 0 or 1. Either way every
word drained with no pulse. Nineteen of the typed trials drained within
96 µs. One took 1.79 ms, consistent with the MIPS being busy, since that
trial's counters stayed still.

After the probes the IRQ RX counter was still 12006, with `tx_desynced=N`
and `tx_fifo_full=0`, and TX enable read back 0. Three ordinary calls then
passed (RX 12006 → 12012 by IRQ, none by polling). The startup checker
passed, the system was `running`, the firmware fault magic was zero, the
log filter was 2, and the kernel log had no CPU_COMM errors.

The firmware ELOG write pointer moved from `0x5f284` to `0x5f5ba` (about
14 bytes per discarded probe word), so the firmware records something for
an unknown word even at filter level 2. That is far below the 2 MiB flush
boundary, but repeated probing is not free.

## Recommendation

Remove the pulse in the next CPU_COMM module patch, with the whitelist
narrowing:

- Delete the TX_IRQ_EN write/`udelay(10)`/clear. This also takes a 10 µs
  busy-wait out of `msgbox_tx_lock` and one spurious MIPS interrupt out of
  every message.
- Correct the `cpu_comm_hw.c` comments that still describe the block as
  edge-triggered.
- Requalify with the warm and operator-cold 6003-call runs.

No runtime parameter is needed: the firmware evidence and this probe
already discriminate.

The pulse may still matter only before the firmware has registered its
channel. The driver must not send then anyway: `isCPUAppReady()` gates
sends.

Evidence digests (SHA-256):

| File | Digest |
| --- | --- |
| `doorbell-probe.py` | `1c2db398…` |
| `doorbell-probe.txt` | `9b782571…` |
| `doorbell-probe-typed.txt` | `539388a1…` |
| `doorbell-postcheck.txt` | `4fe92df4…` |

## 0209

`0209-soc-sunxi-cpu-comm-ring-the-doorbell-with-the-fifo-write.patch`
changes only `cpu_comm_hw.c`:

- `cpu_comm_msgbox_send()` writes the data word under `msgbox_tx_lock` and
  nothing else. The TX_IRQ_EN defines are gone, and the register comments
  now describe the RX-enable mechanism.
- `known_regs[]` holds exactly `0x03061024` and `0x03061028`. The comment
  records the stock module's four words and why the hwspinlock pair is not
  carried.

`test-cpu-comm-tx.py` changes:

- **Doorbell model.** It now counts TX_IRQ_EN writes as a failure and
  checks that each data word follows its own thread's publication under the
  lock.
- **New whitelist case.** It accepts only the two share registers and
  refuses the old msgbox and hwspinlock words, the MIPS status register and
  transport registers. It also scans every `comm_Read/WriteRegWord` literal
  and `getShareRegbyID` return in the driver, requiring that set to equal
  the whitelist.
- **Results.** All 6 cases pass. 14 mutants are rejected, including a
  restored pulse and re-added msgbox/hwspinlock entries. The three 0207
  baseline defects are still reproduced. The 0208 tree itself now fails the
  doorbell case on its pulse writes.

The handoff, IRQ, spinlock and witness suites still pass. The module builds
with `W=1` and no new warnings. Checkpatch is clean, and the patch applies
with zero fuzz to byte-identical source.

### Release build and bundle

The pinned release build (clang/LLD 23.1.4, production config, fixed epoch)
applies 171 patches. Compared with 0208:

- `.config`, `Module.symvers`, the kernel release and every DTB are
  identical, and the FIT is still `845494c3…`.
- Only `hy310-cpu-comm.ko` changes: `9864701f…` → `828dbb724297bbae273ed358a9de14b6c0ad3e3625aa3d1e0e437b12bbbd2156`.
- The release-built `cpu_comm_hw.c` matches the tested source byte for byte.
- The 0208 baseline rebuild reproduces the installed module.

All 23 TX checks and the other CPU_COMM suites pass again on the release
tree.

The module-only bundle (`local/recovery/2026-11-16-cpu-comm-0209/bundle/`,
manifest `163fe82a…`) pins FIT `845494c3…`, cmd `41faabdc…`, scr
`c565a05a…` and installed module `9864701f…`. On a fake root built from the
real installed bytes:

- preview writes nothing;
- apply changes only the module;
- rollback restores the tree exactly.

### Installation and qualification

**Installed** on boot `41b98df8` with the guarded installer: preview
`baseline`, then apply. The boot FAT was mounted read-only. Afterwards the
module is `828dbb72…`, the FAT FIT/scr are unchanged and both manifests
verify. The backup is
`/var/lib/h713-hdmi-startup/kernel-fit-ec4c3ad882a543c785efafab14f29d04`,
holding 0208 `9864701f…`.

**The warm reboots after the stress runs powered off. They did not hang, and
0209 is not the cause.** A UART capture of the retry from boot `a0f8f6a9`
ends with:

> `h713-hdmi-hold-guard: reboot refused, HDMI holds retained ( h713_hdmi_receiver ); powering off, cold cycle required`

The H2 hold guard (a `systemd-shutdown` hook that runs after journald stops)
did exactly what it was designed to do. The receiver was still held because
`h713-hdmi-capture`'s stop exited 1 with
`kernel log changed during restore; verification unavailable`.

`tools/hdmi/h713-hdmi-session.py` `stop()` snapshots `dmesg`, runs `rmmod`,
and requires the new log to start with the snapshot. Once the kernel ring is
full, every new line evicts the oldest, so the check fails even though the
journal shows all 22 DSP words and 15 TVFE clock words restored and
verified. The 6003-call run fills the ring with per-call CPU_COMM lines.
`41b98df8` hit the same failure under 0208, so this is a pre-existing
teardown bug.

**Power-cycle boot `a0f8f6a9` — PASS.**

- The loaded module's GNU build ID is `57b58b47…`, the 0209 release module
  (0208's is `3587b024…`).
- Startup check PASS, acknowledgement dry-run clean, manifests verified, no
  failed units, ext4 errors zero, eMMC HS400 at 200 MHz.
- Live registers: MIPS RX enable `0x3820=0x4`, TX enable `0x3830=0`.
- All **6003 calls** completed: 12006 IRQ RX, zero polling RX,
  `tx_desynced=N`, `tx_fifo_full=0`, and `TX_IRQ_EN` read 0 after every
  phase. The fault magic was zero and the ELOG pointer stayed at `0x5f2cc`.
- Serial-call latency is unchanged: median 0.61 ms and p99 3.2 ms, against
  0.62 ms and 2.9 ms for 0208 cold.
- The CPU_COMM error scan is clean after traffic.

**Warm boot `0459e48c` — PASS.** It was rebooted from `8142459f` before any
stress, with the ring not yet wrapped. The UART shows `reboot: Restarting
system`, then U-Boot, then the kernel, with no guard refusal.

- The loaded build ID is the 0209 module's. Startup check PASS, manifests
  verify, no failed units, ext4 errors zero.
- The previous boot's capture stop succeeded.
- 3 control calls, then all **6003 calls**: 12012 IRQ RX, zero polling,
  `tx_desynced=N`, `tx_fifo_full=0` and `TX_IRQ_EN` 0 after every phase.
  Fault magic zero, ELOG pointer `0x5f284`, no CPU_COMM errors.

**0209 is qualified warm and from power-on.**

### Teardown fix: `/dev/kmsg` cursor (installed, verified)

`h713-hdmi-session.py` `stop()` now takes a `/dev/kmsg` cursor before
`rmmod`: non-blocking, seeked to the end. It reads only the records logged
after it. The verification is unchanged: 22 `DSP restore … verified`
lines, `managed DSP graph restored 22 words` and
`15 clock words and bus verified`. Older records rolling off the ring no
longer matter. Only an overrun past the cursor itself (`EPIPE`) refuses, and
it says so. If `rmmod` fails, the cursor is discarded without masking that
error.

Host tests:

- `test-hdmi-session.py` passes 35 tests. New ones cover:
  - a stop after a 2000-line flood has wrapped a bounded ring;
  - an overrun refusal;
  - restore lines logged before the cursor not counting;
  - no leaked cursor on a failed `rmmod`.
- The old script fails the wrapped-ring test with the board's exact error.
- `install-session-kmsg.py`, modelled on the in-process IPC installer, pins
  the installed session `06ab1e7a…`, the live capture unit `35883a89…`,
  the parallel prepare unit and the manifest `999ebe1e…`. It replaces the
  script and its manifest entry only. Its 5 tests cover preview, install,
  exact rollback, foreign-state refusal, partial-write latch and recovery,
  and payload identity.

On the board:

- The real cursor read exactly the three marker records written after it
  on the already-wrapped ring, read empty when nothing was logged, and
  discarded cleanly.
- **Install.** On boot `0459e48c`: preview, then apply. Session
  `69c67f72…`, manifest `7e4aa73b…`, backup
  `/var/lib/h713-hdmi-startup/session-kmsg-278c42ebbd9f4707bf5107b0582c4285`,
  no services changed.
- **Reboot.** The same boot, with its ring wrapped by the 6003-call run, was
  then rebooted. The UART shows `reboot: Restarting system`, U-Boot and the
  kernel, with no guard refusal. The capture stop returned
  `dsp_restored_words: 22, tvfe_restored_words: 15`. The receiver parked,
  released its holds and was removed.
- **New boot.** `2cfc0d6c` passes startup health and the acknowledgement
  dry-run. Manifests verify, no units failed, ext4 errors are zero, and
  CPU_COMM 0209 is IRQ-only with no desync.

Still open, lower priority:

- `tools/hdmi/bench-receiver-only.py`, a bench tool not used in production,
  keeps the same prefix check.
- The per-call `cpu_comm: addressing channel …` info line is what fills
  the ring during stress; rate-limiting it is a separate kernel change. See the
[validation summary](cpu-comm-doorbell-validation.json).
