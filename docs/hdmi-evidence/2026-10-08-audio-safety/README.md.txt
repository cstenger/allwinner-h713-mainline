# Audio safety preflight, 2026-10-08

This run implemented the safety prerequisites from the reviewed capture plan.
No bootloader, installed kernel, DSP patch, selector or codec setting was changed
by these preflight checks. The inherited diagnostic MIPS firmware remains live.

## Real stock DSP lock

Stock `snd_alsa_trid.ko` REG_Init maps physical 0x05001530, size 8.
WaitDSPFree waits for the peer word to differ from 0x55, publishes ARM claim
0x55 at +4, and rechecks the peer. ReleaseDSP writes ARM word 0xaa.
The old 0x02031078/0x02032078 accesses were codec/daudio registers, not locks.
The old probe was unloaded without executing any further commands through it.

The display-owned TVCAP/TVFE domains were active and the display bus clock was
held, as recorded in preflight-system.log. This corroborates the stock mapping
and existing live audio port; domain names alone would not establish safe MMIO.
The read helper allows only the two lock words and the two CCU clock words.
Before the first claim both lock words read zero. CPU and UMAC clock words both
read 0x80000002, matching stock. This does not measure their clock frequencies.

The corrected DSP probe was loaded with explicit readiness gates. Bounded
version reads on device 0 and device 1 both returned 1. After commands the peer
read zero and ARM word 0xaa. MIPS remained responsive. See
stock-lock-read-test.log. This validates these commands under the observed boot
state; it does not establish the cause of previous DSP timeouts.

The shared lock header has an offline fake-MMIO test exercising actual C code:
contention before/after publishing the claim, bounded timeouts, stale ARM claim,
failed claim/release readback, and 1,000 claim/release cycles. It never writes the
peer word. See lock-test.log.

## Interrupt and event-register corrections

Patch 0024 now lists stock bridge SPI 115 first and AudIf SPI 113 second.
The installed kernel/DT still has the old ordering: no bridge module was loaded.
The managed bridge probe refuses unknown/reversed DT IRQ ordering before taking
clocks or mapping registers/IRQs. Its teardown no longer writes a saved value
back to AudIf's W1C event register 0x06146008.

Both speaker and DSP probes use the shared real lock. Diagnostic ARM clients
must remain exclusive; unload one before loading another. A DSP timeout ends
command traffic and requires a cold restart. Codec restore can still run, but
DSP restore must not be claimed successful after a timeout.

## Offline speaker initialization recovered

`tools/stock/decode-speaker-init.py` links the captured libmspsound,
libmsp_util and libmspdriver in separate Unicorn contexts with mirrored data
and distinct code/stack banks. The exact stock preset passes BP_AUD_Init;
Sound_Path_Init and Sound_Path_Connect(0x89) both return zero and reach the
return trampoline. Hardware DSP reads/writes, AudioTop register operations and
time functions are stubs. Firmware version checks receive simulated version 1.
No output from this harness establishes actual hardware readiness.

The init enables I2SOUT1 module 0x9a00: device 0, DSP word 0x001e mask 0x8000,
value 0xffff. It then applies stock config 0x3000a440: word 0x001e mask 0x7fff,
value 0x2440; word 0x001f mask 0xf93f, value 0x3000. Together these give word
0x001e = 0xa440 while preserving unrelated bits of 0x001f. I2SIN1 module
0x9600 receives config 0x01800000: word 0x0012 mask 0x23ff, value 0x0180,
in addition to its existing enable bit 0x8000. These format writes and output
enable were absent from the previous split trial.

The codec stock put clears its clock-output bits 17/18, making it a slave.
The recovered DSP config is the stock counterpart, but individual MSP clock
bit meanings have not been established. Do not report BCLK/LRCK as measured.

For this preset, path connect itself emits only the six existing selector
writes (0077=1617, 0118=7c7d, 0020=2e2f). It also constructs module groups in
ARM software; it does not add interface-enable, volume or prescale writes.
Those come from initialization or separate HAL calls. The full reachable graph
has additional fixed modules (8b00/8b01 etc.) beyond the plan's short list.
The decoder records the complete initialization rather than claiming the
limited speaker trial reproduces every stock gain/effect setting.

The revised split trial adds just these recovered interface settings, saving
and restoring their original words. It remains a diagnostic experiment.
RXCNT/FSTA/ISTA are observations, not an independently calibrated clock probe;
zero counts alone cannot prove absent clocks, and growth with silence does not
prove absent HDMI input. The runner refuses an existing evidence directory and
attempts every cleanup even if one fails. A DSP failure stops further DSP
commands; skipped DSP restoration is explicitly logged as needing a cold boot.
