# HDMI PCM input-rate test

Prepared and hardware-verified 2026-10-08. All four trials passed; see
[the measured results](hdmi-evidence/2026-10-08-audio-rate-test/attempt2/README.md).
32, 44.1 and 48 kHz inputs all produced 48 kHz stereo S16_LE capture.

The sweep sends stereo S16_LE at **48,000 -> 32,000 -> 44,100 -> 48,000 Hz**.
The first and last trials are controls. Each trial opens the HDMI hardware PCM
for ten seconds of L 1 kHz / R 2 kHz tones (amplitude 6500), followed by four
seconds of digital silence while the same PCM remains open. Each gets its own
bounded, saved/restored 30-second HPD/EDID window through the existing
`run-detection-trial.py --stock-io` helper. Allow about three minutes overall.

## Prerequisites

Prepare the exact successful [graph-chain attempt 2](hdmi-evidence/2026-10-08-linux-graph-chain/attempt2/README.md)
path using the [handoff](handoff-2026-10-08-hdmi-audio-capture.md).
The diagnostic bridge must already be running at stage 4 with the private
64 KiB coherent DMA buffer, CONFIG 2207 and corrected bridge/AudIf IRQs
115/113. The DSP must have the stock volatile patch and the 22-word
`graph_chain=1`, `stock_graph=1` route active. TVFE and receiver-power/EDID
holds must remain active. No competing host HDMI playback or board audio client.
The host connector must initially be disconnected, as required by the helper.

The new runner checks the graph flags, bridge stage and DMA file. These checks
do **not** establish every hardware prerequisite; use the proven setup recipe.
The runner does not boot the board, load the DSP patch, apply the graph, load
bridge modules, or perform any new receiver/PLL MMIO access.

The previous run restored the graph and unloaded diagnostics. Re-establishing
the DSP experiment starts with a physical cold boot: unplug the serial adapter
and all USB from the board, remove power for at least one minute, then stop at
U-Boot and follow the handoff. Never warm-relaunch MIPS or clear a timeout latch
by reloading the DSP module.

## Run

From the main checkout, with host Python 3, NumPy, `aplay`, SSH and the existing
signal helper dependencies available:

```sh
python3 tools/hdmi/run-audio-rate-test.py /tmp/h713-audio-rate-trial
```

The evidence directory must not already exist. The sweep stops on the first
failure. There is no automatic hardware retry. Inspect `summary.json` and the
failed trial logs before changing hardware or repeating a test.

For an offline check without accessing board or host audio hardware:

```sh
python3 tools/hdmi/test-audio-rate-test.py
python3 tools/hdmi/run-audio-rate-test.py --generate-only /tmp/h713-rate-vectors
```

## Measurements and acceptance

- Uses `hw:C,D` and disables host resampling. Records the source ELD and actual
  `/proc/asound/.../hw_params`; rejects a negotiated rate other than the requested
  input rate, or a format other than stereo S16_LE. A WAV header alone is not proof.
- Saves three raw DMA rings during settled tone playback, at roughly 2, 4 and
  6 seconds. Rejects reads that extend outside the tone window or occur after
  playback/signal-helper exit. Keeps every ring for independent analysis.
- Infers the capture rate from each channel's known tone cycles per sample,
  comparing 32,000, 44,100 and 48,000 Hz. Requires both channels to agree within
  1%, at least 90% of spectral energy within +/-30 Hz of their own tone, less
  than 0.5% in the opposite tone, sensible amplitude and low DC. Hann windowing
  tolerates a discontinuity from reading a live ring across its write pointer.
- Accepts either the input rate or 48 kHz as the capture rate. Each 48 kHz
  control must therefore classify as 48 kHz. All three snapshots must agree.
- Records board uptime and bridge IRQ counters, requiring forward progress
  through tone and silence. Reports IRQ frequency as supporting timing evidence;
  interrupt coalescing prevents treating it as an exact sample counter.
- Reads silence about two seconds after the tone ends, with the host PCM still
  open. Requires both channel RMS levels at most 4 signed-16 units.
- Compares channel RMS against the first 48 kHz control, requiring less than
  15% change. Requires successful playback, signal-helper completion and removal
  of its temporary SCP/DDC modules.

`capture_rate_hz` is inferred from a known-frequency signal in DMA, **not** a
continuous frame-count or latency measurement. If all inputs classify at
48 kHz, that is evidence of conversion somewhere in the receiver/DSP path;
this test does not identify the converting block. If capture follows each
input, ALSA must handle rate-dependent timing. This diagnostic cannot establish
long-term drift, gap-free capture, precise latency, or rate switching while a
single capture application stays open.

## Restoration

On success or ordinary failure, the runner closes host playback and waits for
the bounded signal helper to restore its HPD/EDID state. The existing prepared
DSP/bridge/TVFE setup is left active for inspection. Restore the graph with
readback **before** unloading DSP, bridge and TVFE holds, following attempt 2's
cleanup. A physical cold boot clears the volatile patch. If the signal helper
times out, restoration is unconfirmed; inspect its log and board state before
continuing. Preserve evidence under `docs/hdmi-evidence/` after the hardware run.

## Offline validation

Five checks cover each candidate capture rate, a live-ring seam, zero/DC/noise,
swapped channels, an unsupported capture rate, weak tones, host-rate mismatch,
missing IRQ evidence, and exact WAV rate/format/silence. The analyzer also
accepts the three recorded successful 48 kHz rings and recognizes the recorded
post-tone ring as silence. These checks validate the test's discriminators;
they do not establish 32/44.1 kHz support on the board.
