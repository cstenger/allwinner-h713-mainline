# Repeated same-open HPD recovery, 2026-10-14

**PASS:** ten HPD-loss recoveries after an initial baseline connection, all
with the same capture PID1076. All eleven unique markers and channel tone
windows passed; minimum marker correlation.99863. The240-second recording
contains exactly11,520,000 stereo frames (46,080,000 raw bytes), zero recorder
overruns/new driver XRUNs and a zero-filled final second. Capture exited0.
Every signal helper and player exited0; SCP/DDC restoration/removal passed on
all windows. Actual source hardware negotiated48kHz stereoS16_LE throughout.

[Full result](bench/cycles/result.json), [summary](summary.json),
[teardown](bench/audio-unload.log), [tested hashes](build-manifest.json).

A physical cold boot/manual U-Boot stop preceded the guarded single MIPS
launch, verified live PID/source3 worker, preserved FIT and RAM-only IRQ115/113
correction. Receiver ownership/EDID and managed TVFE/DSP initialization passed.
The canonical EDID helper is staged only in RAM. No persistent boot/module
installation or serial listener is used. Initial Wi-Fi activation preceded AP
readiness; retry after AP start succeeded before board preparation.

The four-minute240-second48kHz stereoS16_LE capture stays open across an
initial baseline and ten HPD-loss returns (eleven signal windows). Each window
has a12-second bounded saved/restored HPD hold, followed by disconnected state
and a3-second gap. Actual host hw_params, same capture PID and RUNNING state
in active/disconnected phases, monotonic capture progress, healthy DSP state
and successful SCP/DDC restoration/removal are required.

Every returned source window plays a unique filtered-noise marker plus
normal/swapped1kHz/2kHz channel tones. Matched filters and post-marker tone
analysis in the completed recording must verify all eleven windows; native
controls reject replayed markers, missing/wrong-channel audio, short capture
and contaminated silence. Exact raw byte count, zero final second, no recorder
overruns and zero new driver XRUNs are required. PCM is streamed to the host,
not stored in board RAM. Audio is not reinitialized between cycles.

This is software HPD recovery. It does not establish repeated physical cable
endurance, although a single physical unplug/replug passed previously.

## Final state

Audio unloaded after all22 DSP graph words restored with readback, SPDI1/
bridge/AudioTop/IHB restored, and15 TVFE clock words plus bus/reset verified.
Receiver clients0, firmware_pinY, edid_readyY, clock_count4, init_error0; both
receiver domains remain active and MIPS responds. WirePlumber is active and
original empty firmware path restored. Audio and transient SCP/DDC helpers
are absent; no capture, player, listener or recovery remains.

The volatile DSP patch remains until a physical cold boot; new managed audio
initialization requires cold versions0/0. No DSP retry/reload occurred between
cycles. Do not force receiver removal under live firmware.

This establishes repeated software HPD recovery, alongside earlier single
physical unplug/replug and one-hour recording validation. Repeated physical
cable endurance, automatic source3 boot, parked shutdown and suspend remain
unvalidated. These changes and the one-hour endurance work are newer than
checkpoint71dca46. Raw recordings/source WAVs remain local and ignored here.
