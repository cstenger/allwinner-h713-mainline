# Linux direct-route capture trial, 2026-10-08

Result: no PCM DMA writes. All four 65,536-byte tone snapshots remain entirely
0xa5, identical to the pre-tone buffer; bridge IRQ count stays zero. Host ALSA
playback of 10 seconds of stereo S16_LE 48-kHz tones (L 1 kHz, R 2 kHz) to
hw:0,8 completed with return code 0. The canonical HDMI ELD was valid and
receiver port-cache samples show state 5, 1280x720, pixel repeat 0. This is a
failed direct-route diagnostic, not a reproduction of Android's complete graph.

## Setup and evidence

The preserved Linux 6.18.38 kernel was booted with only the loaded RAM DT IRQ
order corrected to bridge SPI115, AudIf SPI113. Installed FIT, SPL, U-Boot and
IR/suspend changes were preserved; exact restoration evidence is in
[the Android capture directory](../2026-10-08-android-capture/README.md).
The IRQ correction must be reapplied on another boot.

The TVFE hold and bridge/DSP probes were built against the exact running kernel.
`builds.json` records module SHA256 values. `tvfe-preflight.log` and
`audio-setup.log` record clock checks and guarded source-3/audio setup.
Private coherent DMA was allocated at 76c60000; the stock literal address was
not used. CONFIG=2207, block=40, start=006c6000, end=006c6fff, address-high=70.
Linux IRQ336 maps bridge SPI115; IRQ335 maps AudIf SPI113.
SPDI1 controls were 90000000/3000, AudioTop 700/011a5e00, IHB81000002.

`dsp-patch.log` verifies the existing fixed 724-pair volatile stock patch:
cold versions 0/0 became 1/1, with the stock ownership lock and bounded waits.
No patch timeout occurred. This patch has no verified inverse; a physical cold
boot is required to clear it even after the diagnostics are unloaded.

`dsp-route.log` verifies all five saved/readback settings for direct route bd:

| DSP word | Saved | Trial | Meaning from stock code |
| --- | --- | --- | --- |
| 0130 | 0000 | 1617 | I2SIN1 to DTVOUT1 |
| 0012 | 0000 | 8180 | Input interface enabled, stock I2S format |
| 0017 | 2000 | 2000 | Input prescale 32 was already present |
| 801a | 0000 | 0000 | DTV output channel 0 |
| 8017 | 0001 | 0000 | HDMI input unmuted |

The earlier concern that input prescale was missing was not borne out here:
its cold post-patch value was already 2000. Format and route did change.

`run-trial.py` is the executed host orchestration snapshot. The existing
bounded signal helper ran with --seconds 30 --stock-io --probe-port-cache;
`signal-window.log` and `signal-evidence/` preserve its logs and restoration.
`trial-result.json` records both playback and signal-helper return codes 0.
`dma-before.bin`, `dma-tone-{1..4}.bin`, `dma-analysis.json`, and
`snapshot-{1..4}.log` establish unchanged private DMA and zero bridge IRQs.
Snapshots are live ring reads, not atomic completed-period captures. Because
every byte remained the sentinel, no PCM FFT is meaningful in this run.

`receiver-after-tone.json` contains cached N6144/CTS74250 but cached sample
rate and PLL history remain zero. ARM reads MIPS DRAM outside MIPS cache
coherency; these zeros do not prove missing audio packets or clocks. The
before-tone audio-cache sample was taken during receiver acquisition and does
not establish tone-time readiness. This run did not obtain positive receiver
sample-rate/APLL completion evidence. Do not attribute the failure exclusively
to the route, SPDI status, DSP initialization, or PLL from this experiment.

## Restoration

Signal helper reports SRAM/peripheral restoration true, EDID mismatch zero,
and DDC pins returned to inputs. Five DSP route words were restored in reverse
order with readback (`dsp-route-restored.log`). The DSP, bridge and TVFE trial
modules were unloaded. `cleanup.log` confirms restored SPDI controls,
output stream 0, AudioTop and TVFE state; MIPS `help win` still responds.
Only the preexisting receiver power and EDID holds remain loaded.

The volatile DSP patch and its initialization words remain until physical
cold boot. No eMMC write, boot environment save, U-Boot reflash, undocumented
receiver-window read, PLL register write, DAC amplifier action or Speaker
Switch0 action was part of this Linux trial.

## Next work

Offline HAL/preset decoding now establishes that the successful Android setup
selects route 8f, not bd. See `hal-route-selection.json`, `routes-8f-bd.json`,
and `capture-init-code.json` in the Android capture directory. Route 8f uses
processing outputs 9009/900a; stock initialization connects those to DTVOUT1
(0130=696a), while direct bd connects 9600 directly (0130=1617).

Compare the processing graph and its prerequisites offline before the next
bounded experiment. The emulated initialization includes hardware/timing stubs
and must not be replayed wholesale. Separately require positive receiver audio
readiness evidence, without reviving disproven zero-status clock gates.

`capture-graph-selected-words.json` in the Android evidence directory folds
the emitted initialization/route writes while retaining unknown-bit masks.
Besides DTVOUT1 0130=696a, the processing graph needs 0077=1617, 004d=696a,
8059 low byte 7c, 805a low byte 7d, 0003 bits 0f00=0300, 800c masked bits
00f8=0080, 800d low byte 0, and 00ac=0. These are comparison targets;
unmodeled hardware/timing prerequisites and actual cold DSP values still need
checking. The direct route trial configured none of this processing graph.
