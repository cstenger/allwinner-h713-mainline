# HDMI-in audio captured on Linux: 22-word graph chain, 2026-10-08

**Result: tone-correlated stereo HDMI PCM reached Linux memory.** The host
played L 1 kHz / R 2 kHz, 48 kHz S16_LE into HDMI1. The private bridge DMA
buffer held that signal with the channels separated (`dma-analysis.json`):

| Snapshot | L peak | L energy in 1 kHz +-30 Hz | R peak | R energy in 2 kHz +-30 Hz | Opposite tone |
| --- | --- | --- | --- | --- | --- |
| dma-tone-1 | 999 Hz | 0.974 | 2001 Hz | 0.972 | <= 4e-5 |
| dma-tone-2 | 999 Hz | 0.988 | 2001 Hz | 0.987 | <= 5e-6 |
| dma-tone-3 | 999 Hz | 0.993 | 2001 Hz | 0.993 | <= 8e-6 |
| dma-tone-4 | all zero (taken at 562.9 s, after the 10 s tone ended ~561.5 s) | | | | |

The missing energy (< 3 %) is window leakage plus the discontinuities you get
from a live ring read that crosses the write pointer. Peak level is +-6324,
RMS 4472 (= 6324/sqrt 2, a pure sine). Stock Android's capture peaked near
2100 after its HAL software prescale of 0.334966, which is about 6270 raw. The
level matches. The post-tone snapshot is pure zeros, a built-in silence
control. Bridge IRQ (SPI 115, Linux 336) kept advancing (85948 -> 87748
during the window). AudIf/SPDI status stayed zero, as on stock.

## What made the difference

This is the 13-word stock-graph trial plus nine words recovered offline
(`../README.md`, `../../2026-10-08-graph-chain-offline/README.md`). The saved
cold values in `dsp-graph.log` show which of the nine mattered:

| Word | Cold (after stock patch) | Applied | Meaning |
| --- | --- | --- | --- |
| 007c/007d/007e | 8081/8283/8485 | same | 8400 -> 8500 is already wired after the patch |
| 8102/8103 | 0000 | 0086/0087 | **8500 -> mixer 8f01 inputs 2/3 were unconnected** |
| 0102/0103 | 0000 | 2000/0020 | **mixer 8f01 input 2/3 gains were 0** |
| 0059/005a | **8000** | 0000 | **9009/900a (feeding DTVOUT1) were user-muted** |

Both breaks would each give exactly the zero-PCM-with-IRQs result of the
13-word trial.

## Run record

The board was cold booted by the operator; `cold-start.log`, `source3.log`,
`fit-check.log` (DT size 8319), `ram-dt.log` (IRQ 115/113 in the RAM copy
only), `linux-boot.log` (same 6.18.38 #1). `staged.log` lists the module
hashes: TVFE 8f32cf93..., bridge 1e137200... (both bit-identical to the
recorded builds) and DSP probe 8b5c8e64... (graph_chain plus stock 50 ms
waits). `linux-preparation.log`, `audio-setup.log` (cold versions 0/0,
graph_chain=Y), `dsp-patch.log` (724 pairs, versions 1/1), `dsp-graph.log`
(22 words saved/written/verified, no slow completion-clear needed).

The first signal window (`no-link-window/`) got no host ELD: the host
connector card1-HDMI-A-1 never went connected although the board asserted HPD
and served EDID with 0 mismatches. The operator reseated the PC -> HDMI1 cable.
The rerun (`signal-window.log`, `trial-result.json`) found ELD "H713 HDMI IN"
on hw:0,8. Playback and the 30 s signal helper both returned 0. `run-trial.py`
is the executed orchestration (the stock-graph script with only the output
path changed). Receiver cache during the tone: state 5, 1280x720, N 6144 /
CTS 74250.

## Restoration

`dsp-graph-restored.log`: all 22 words restored in reverse order, every
readback equal to its saved value. `cleanup.log`: SPDI1, output stream 0,
AudioTop, IHB clock and TVFE restored; DSP, bridge and TVFE modules unloaded;
MIPS `help win` responds. The remaining loaded modules are h713_edid_clock
and h713_hdmi_power. The volatile DSP patch stays until the next physical cold
boot. Installed FIT, bootloader and environment are unchanged.

## What this establishes and what it does not

Established: HDMI RX -> I2SIN1 (9600) -> 8400 -> 8500 -> 8f01 -> 9009/900a ->
DTVOUT1 -> SPDI1/bridge ostream0 -> private DMA works on Linux with the stock
patch and 22 decoded words. Receiver audio readiness is therefore not a
blocker, and no PLL writes were needed.

Not yet: a real ALSA capture driver (this is a diagnostic ring read), the
long-term stability, other sample rates, compressed formats, and teardown
without a cold boot (the patch has no inverse).
