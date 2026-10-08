# Bounded DSP1 logical read diagnostic

Not a production driver. Never autoload. Build against the exact running
kernel; it does not acquire audio clocks itself.

Before loading, verify the guarded cold U-Boot source-3 transition, live MIPS,
TVFE/TVCAP holds, four receiver clocks, the stock-order TVFE hold, and the audio
probe with `init_audio_top=1 stock_audio_ihb=1`. No ALSA stream or Linux driver
may own the handshake windows at 02031078/02032078. The current kernel's codec
owns only 02030000–0203032b and its playback stream was closed during validation.
These prerequisites are explicit caller acknowledgements, not checks enforced
by this module. Unload this module before removing either power/clock hold.

Load with `armed=1 live_source3=1 audio_ready=1`. Initial load only reads command
status and both ownership words. It never downloads firmware, changes a DSP
selector, or enables DMA/interrupts. Do not set `dsp_word` during module load.

A sysfs write to `dsp_word` accepts only 0x77, 0x130 or 0xfff7. It claims the
stock user-owner word with 0x55, verifies that kernel ownership is not 0x55,
waits at most 10 ms for command-not-busy, writes the logical read request,
requires completion to clear within 1 ms and rise within 10 ms, reads the
response, then restores the original ownership word. Idle user values are
restricted to 0, 0xaa and the measured Linux cold value 0x50.

Completion stays asserted after a response read. Requiring an observed clear
protects against stale completion but can reject an operation that completes
before the first sample. Such a timeout is inconclusive, not proof of DSP
failure. The first selector trial observed a clear/set transition for 0x77,
returning zero; the next request at 0x130 did not observe clear and stopped.

Any timeout blocks subsequent commands for the lifetime of the loaded module.
**Physically power-cycle after timeout before any new DSP trial.** Unloading
and reloading resets this software latch; it does not recover the hardware.
See ../../docs/hdmi-evidence/2026-10-07-dsp-cold/README.md for measured results.

## Revised completion and fixed stock initialization

The current reader samples immediately after the request with IRQs disabled
for at most 100 us, then performs the longer completion wait with IRQs enabled.
It supports DSP0 logical80ff and DSP1 logical80ff (encoded0x180ff). All four
readiness/selector reads passed on the next cold boot. DSP1 uses command+18,
status busy bit7/completion bit8; DSP0 uses+10,bits4/5, from the vendor functions.

`tools/hdmi/build-dsp-probe.py` optionally compiles a fixed stock patch build
in a separate directory. It accepts only the recovered 2896-byte patch with
SHA2568e31db199e0078d142f622436ff0b7249b333dbb6df8ec3fbabc0d8fea6ea0c5,
generating724 exact big-endian pairs. The ordinary module build has no patch
or capture-route parameter. No proprietary patch table is added to this source.

`stock_patch=1` is a one-shot sysfs operation, never an insmod argument.
It requires both version words to be zero, claims ownership, verifies stock
masked control writes at00ee/8034/8017, then writes the stock prefix and724
pairs with1ms pacing and bounded busy waits. It verifies both stock version
words afterward. On hardware both changed0->1. Partial failure requires a
physical cold boot; unloading this module cannot undo the volatile DSP patch.

`capture_route=1` in the optional build requires versions1/1. It saves and
verifies word0130=1617 for preset routebd, clears HDMI mute bit0 at8017,
and enables I2SIN1 via word0012 bit15 (vendor EnableInterface). Explicit
`capture_route=0` restores and verifies all three originals. This is a route
experiment, not a complete Android graph or proven capture path. Two bounded
stereo trials, with and without the separate interface enable, left the full
64-KiB SPDI1/Audio Bridge capture buffer unchanged and both IRQ counts zero.
See the dsp-readiness evidence for provenance, hashes and exact final state.
