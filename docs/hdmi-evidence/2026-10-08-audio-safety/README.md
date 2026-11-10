# Audio safety preflight observations — October 8, 2026

Historical records, curated October 19. This preflight ran with inherited
live diagnostic MIPS state. Its successful reads do not establish readiness
under other boots or explain earlier DSP timeouts. No new hardware checks
were performed during curation.

The corrected stock shared DSP lock is at physical 0x05001530 (two words),
not the earlier misidentified codec/DAUDIO registers. The
[initial read](stock-lock-and-clocks.json) records both lock words zero and
two CCU clock words 80000002. After bounded device-0/device-1 version reads
returned 1, [stock-lock-read-test.log.txt](stock-lock-read-test.log.txt) records
peer=0 and ARM=aa, plus responsive MIPS. These word readings do not measure
clock frequency. The [lock test](lock-test.log.txt) is a historical offline
fake-MMIO pass for contention, timeouts, readback failures and 1000 cycles;
it was not rerun here.

The original notes also record the bridge IRQ-order and W1C corrections. The
installed DT still had the old ordering at preflight, so no bridge module was
loaded then. Source assertions and boot observations must not be confused with
a successful bridge-capture trial. The later rate sessions have their own
RAM-DT/setup records.

[speaker-init-code.json](speaker-init-code.json) retains the complete offline
speaker-init trace and library/preset hashes. Init/connect returned 0/0 in a
model with stubbed hardware, time and version replies. The trace records
I2SOUT1/I2SIN1 format/enable writes and six connect selector writes; it does
not prove physical clocks, hardware readiness or speaker output. It is not a
live initialization recipe. [dsp-build.json](dsp-build.json),
[module-sha256.txt](module-sha256.txt) and [tinyalsa-build.json](tinyalsa-build.json)
retain historical build identities, not freshly rebuilt artifacts.

[README.md.txt](README.md.txt) preserves the original detailed notes, including
then-current source changes and instructions. See the
[October 8 history](../../audio-oct8-history/README.md) and its
[manifest](../../audio-oct8-history/manifest.json) for source/export hashes,
normalization and limits. The [rate evidence](../2026-10-08-audio-rate-test/README.md)
separates the later aborted setup from the successful cold-start retry.
