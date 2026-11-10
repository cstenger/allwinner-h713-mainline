# Event-8 instrumentation: deployment history

The initial volatile attempts below failed. The subsequent user-authorized
temporary flash succeeded; see [hardware results](event8-trace-result-2026-09-08.md).
The original second stage was restored and verified after that experiment.

## Prepared and checked

`tools/mips/event8-trace.py` produces a 391-entry replacement for the existing
U-Boot `h713_disp mips-comm-trace` patch table. It validates the exact firmware
SHA-256, checks pristine cave bytes, preserves displaced instructions, and
tests all eight trampolines in 32 paired Unicorn emulator cases (every GPR,
counter selection, and captured return/input value). This does not emulate
hardware caches, scheduling, interrupt reentrancy, or the complete firmware.

Hooks count event-8 DoMessage entries, the detector's secondary-base callback,
CheckSignal entry and all three returns, SetSource adapter entry, and SetSource
HAL entry. Counts/last values occupy 0x4e340080..0x4e34009c, written through
MIPS KSEG1 0xae340000. The existing readiness setup clears this shared page.
Counters wrap at 32 bits and are non-atomic; intended use is bounded sampling
of deltas, not resetting them while live.

The resident original table at 0x7ffa4880 matched all 6256 bytes of the saved
image table. CRC32: original 5420aff3; replacement c9fa63aa. U-Boot relocation
base was 0x7ff13000; table offset within U-Boot is 0x91880.

## Two failed volatile installation attempts

1. `cp.b` into the resident table faulted on its read-only MMU mapping
   (ESR 0x9600004f, FAR 0x7ffa4880). Automatic reset recovered default Linux.
2. This U-Boot has no `dcache` command. A 112-byte standalone helper was built
   to call the existing dcache_disable/enable routines around the copy. Those
   routines matched the saved image (combined CRC32 1625241d). Helper copy and
   register preservation passed an ARM64 emulator check with cache calls stubbed.
   Hardware faulted within the cache-control call before the copy loop
   (ESR 0x8a000000, PC/LR 1), then reset. Its exact underlying cause is unresolved.
   `tools/mips/event8-table-copy.S` is retained and marked DO NOT RUN.

No MIPS hook was installed. No eMMC bootloader or FAT firmware was changed.
The board recovered to default Linux, core parked, SSH working.

## Concrete alternative requiring a persistent bootloader change

Prepared `build/out/u-boot-sunxi-with-spl-event8-trace.bin` by replacing only
the matched patch-table bytes in the known frame-trace image. Size remains
948841 bytes; SPL and all bytes outside the table remain identical. The
embedded FIT U-Boot node is uncompressed and has no hash/signature child.
This candidate has not been flashed or hardware-validated.

Original SHA-256:
`6f7c32c06d6702206ab8ab52195bfb5cdd1d11820047512fdb52c1af2ebe3929`

The candidate changes the diagnostic mips-comm-trace table, not default init.
Before deployment, back up and verify the currently installed bootloader,
then follow the repository's established flash/readback procedure. This
deployment differs from the RAM-only approach attempted here.

After deployment: start `h713_disp mips-comm-trace 0x34`, verify readiness and
baseline witnesses, boot the test kernel, load budgeted DECD, stage one frame,
and compare trace deltas over a bounded interval. Keep the ring frozen for the
SetSource comparison. Restore the prior bootloader after collecting evidence.

Generated table, hook words, original table, and layout are in
[event8-instrumented-2026-09-08](event8-instrumented-2026-09-08/).
