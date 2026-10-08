# Stock processing-graph comparison, 2026-10-08

Result: transport activity, but no tone-correlated PCM. The Android evidence/handoff was
committed first as b27e345, as requested by the user. The user then confirmed
physical cold boot at U-Boot. Guarded first MIPS launch and source3 transition
passed. Preserved FIT embedded DT size8319 verified; copied RAM DT IRQ order
corrected to SPI115/SPI113 and used to boot the preserved6.18.38 kernel.

The new `stock_graph` parameter applies only13 fixed DSP logical words derived
from Sound_Path_Init plus route8f, with explicit HDMI input unmute. Every word
is saved before any write; unknown bits preserved; each write read back;
explicit0 restores in reverse order. Requires both patch versions1 and stock
cross-processor lock. Mutually exclusive with direct capture_route and the
DTV-channel alternate. Any partial failure latches failed and requires cold
boot. This is a graph comparison trial, not complete Android initialization.

Fixed masks match capture-graph-selected-words.json; input unmute uses8017 bit0
as in the existing direct probe. Compiled against exact running kernel,
SHA256768fa533db541c6fa40a8b697c4a7c3151957b1b965be9d070c152f690786a31.

See cold-start.log, commdev.log, source3.log, ram-dt.log and linux-boot.log for
startup. Both host tone playback and30s signal helper returned0. The private DMA buffer
was overwritten entirely with zeros in all four tone snapshots. Bridge IRQ
samples3029,3587,4124,4684 advanced; AudIf IRQ/status remained0. Stock-graph
settings therefore permit bridge transport activity in this setup, unlike the
previous directbd trial. They do not establish that HDMI samples reached the
DSP processing graph. See dma-analysis.json, dma-tone-{1..4}.bin,
snapshot-{1..4}.log, trial-result.json and signal-evidence/.

Receiver video cache showed state5/1280x720, N6144/CTS74250. During-tone cache
reads were added this time; cached rate/APLL history stayed0. These reads are
outside MIPS cache coherence; zero history does not prove missing PLL setup.
No undocumented MMIO or PLL writes were performed.

All13 DSP words restored in reverse order with verified readback:
dsp-graph-restored.log. Bridge/SPDI1/AudioTop/TVFE trial state restored and
modules unloaded; MIPS help win still responds (cleanup.log). Only base
receiver-power/EDID holds remain. The fixed volatile DSP patch remains and
requires another physical cold boot before a new DSP trial. Installed FIT,
bootloader and persistent environment unchanged.

Next: compare omitted stock initialization/effect/gain controls feeding8400
through8f01/8d01 and processing outputs9009/900a, plus obtain positive receiver
audio readiness evidence safely. Do not repeat directbd or claim capture
success from DMA/interrupts. Each later experiment must name its fixed decoded
settings, preserve unknown bits, save/readback/restore and require actual tones.
