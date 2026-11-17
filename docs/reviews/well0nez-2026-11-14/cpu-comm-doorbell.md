# CPU_COMM doorbell pulse — November 16, 2026

**Result: the display MIPS wakes on the FIFO write alone.** The TX_IRQ_EN
pulse our driver sends after every doorbell word is not needed while the
firmware is running. It enables an interrupt that the firmware never handles.
Nothing has been changed in the driver yet. Removing the pulse is planned as
part of the next CPU_COMM module patch, together with the
[0014e whitelist narrowing](../../handoff-2026-11-16-emmc-and-well0nez-for-claude.md).

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
