# HDMI PCM rates: all three advertised input rates passed

The user physically cold-cycled the board and stopped it at U-Boot. The
unmodified successful graph-chain module binaries then prepared the complete
capture path without a DSP timeout. The bounded sweep passed all four trials:

| Trial | Actual host HDMI rate | Inferred DMA rate | Lowest expected-tone energy fraction | Level ratio L / R vs first control |
| --- | ---: | ---: | ---: | --- |
| Initial control | 48,000 Hz | 48,000 Hz | 0.9582 | 1.00000 / 1.00000 |
| 32 kHz input | 32,000 Hz | 48,000 Hz | 0.9724 | 1.00000 / 1.00103 |
| 44.1 kHz input | 44,100 Hz | 48,000 Hz | 0.9913 | 0.99983 / 1.00018 |
| Final control | 48,000 Hz | 48,000 Hz | 0.9574 | 0.99983 / 1.00001 |

Each trial has three64KiB private coherent DMA snapshots of L1kHz/R2kHz,
stereoS16_LE. Every snapshot passed the capture-rate, tone, channel separation,
DC and amplitude checks. Maximum opposite-channel tone energy fraction across
the whole sweep was6.03e-5. All four active-stream silence tails were entirely
zero. Bridge IRQs advanced during tone and silence, at approximately184-185Hz.
All playback and signal-helper return codes were0, and each helper's temporary
SCP/DDC modules were confirmed removed.

## Evidence and interpretation

[`sweep/summary.json`](sweep/summary.json) records the full result. Each trial
directory includes ELD, host hardware parameters, verbose `aplay` configuration,
raw DMA rings, detailed spectral analysis, board uptime/IRQ counters, signal
logs and copied signal-helper evidence. The ELD advertises stereo16-bit LPCM
at32/44.1/48kHz. `hw-params.txt` positively verifies each requested source rate;
playback used a direct `hw:` device with host resampling disabled.

The DMA rate is inferred from known tone cycles per sample, with both channels
agreeing on48kHz, rather than assumed from the source's WAV header. This
establishes rate conversion somewhere in the receiver/DSP path for32 and
44.1kHz input. It does not identify which block resamples, measure continuous
frame timing or drift, prove uninterrupted format switching in a single live
capture session, or extend support to24-bit/multichannel/compressed formats.
Live-ring read seams account for some spectral leakage; the raw rings remain
available for independent inspection.

**Driver implication:** start with a fixed48kHz stereoS16_LE ALSA capture
interface. The tested HDMI inputs at32/44.1/48kHz all feed that interface. Do
not advertise native32/44.1kHz capture based on these input capabilities.

## Setup and cleanup

`mips-start.log` records the first guarded trace launch at the user-stopped
cold-boot U-Boot prompt; `source3-fit.log` verifies current PID/source3 worker
completion and preserved FIT/DT size. `ram-dt-boot.log` applies only the known
IRQ115/113 correction in RAM. `linux-preparation.log` verifies source3/canaries
and holds. `audio-setup.log` records exact module hashes, private DMA,
CONFIG2207 and cold DSP versions0/0. `dsp-patch.log` confirms the fixed724-pair
patch and versions1/1. `dsp-graph.log` verifies all22 graph settings.

`dsp-graph-restored.log`: all22 original words reverse-restored, every readback
equal to the saved value. `cleanup.log`: DSP, bridge and TVFE diagnostics
unloaded, SPDI1/ostream0/AudioTop/IHB/TVFE state restored, MIPS `help win`
responds. Only base receiver-power/EDID holds remain. The volatile stock DSP
patch remains until a physical cold boot. No persistent boot artifacts changed
and no serial listener or playback process remains.
