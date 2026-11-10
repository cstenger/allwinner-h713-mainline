# ALSA recovery checks, 2026-10-13

Both capture recovery checks passed using the unchanged, previously validated
ALSA module. **DSP teardown did not finish: physical cold boot is required
before further DSP commands.** No boot artifacts or persistent configuration
were changed. No listener was started.

## Stalled reader: PASS

`run-alsa-capture-test.py --stall-reader` records a 16-second WAV and suspends
only the positively identified arecord owner for one second, beyond the
341-ms DMA ring duration. A board-side finally block resumes the process.
The PCM entered XRUN, arecord reported an overrun of about 660 ms, then the
same PID/open PCM returned to RUNNING. All three tone windows, the exact
768,000-frame format and zero final second passed. See
[summary](stalled-reader/summary.json) and the saved status/log/WAV files.

This is ALSA's consumer-overrun recovery; the driver's hardware-pointer/IRQ-gap
`period_xruns` counter remained zero. It does not test every XRUN cause.

## HPD/source loss and return: PASS

`run-alsa-reconnect-test.py` uses two independently bounded, saved/restored
12-second HPD windows with a disconnected interval between them. Capture stays
open for the entire test. It is a controlled source-loss test, not physical
cable extraction. First playback uses L1k/R2k; returned playback swaps channels.
Both direct host hardware streams verified at 48 kHz with resampling disabled.

The same capture owner PID2150 remained RUNNING before and after signal loss.
Its original trigger timestamp was unchanged. Normal tones appear at about
0.34–4.10 seconds and fresh swapped tones at21.85–25.60 seconds in the saved
recording. Capture closed after the intentional38-second SIGINT bound
(timeout return124 is expected). The WAV has1,823,388 frames. See
[result](reconnect/result.json) and [fresh-audio reanalysis](reconnect/fresh-audio-reanalysis.json).
The analyzer's synthetic controls reject replayed old audio, missing returned
audio and reversed event order. This short result does not establish repeated
hotplug endurance or source-rate changes while capture is open.

## Setup and cleanup limitation

Source3/canaries and receiver holds verified before module loading. DSP versions
read0/0 after restoring/reloading audio clocks; the pinned patch was applied
and versions1/1 and all22 graph words verified. This observation does not prove
that unloading diagnostics is an acceptable substitute for a cold boot after
a DSP timeout; that remains forbidden.

After both successful captures, final counters reported10,019 owned active
interrupts,10,009 notifications,10,432,336 bytes progress and zero driver XRUNs.
The attempted graph restore timed out reading800c at completion-clear after
50,106us.20 restore rows verified before that readback; remaining graph state
must be treated as partial. No further DSP commands were sent. See
[timeout evidence](restore-timeout.log). The helper's failure latch was not
bypassed by reloading.

[Cleanup](cleanup.log) confirms DSP/ALSA/TVFE diagnostics unloaded, peripheral
settings restored and MIPS responsive. Receiver power/EDID holds remain.
Physical cold boot is required to clear the partial DSP graph and patch.

The preserved [stock read assembly](stock-dsp-read.asm), from stock module
SHA25665a8bdbbe9463aff2ae462a27fce3de1862a8039c52a22df2553fb6cd78794f5,
waits busy-clear then done-set with a49999-us bound; it does not require an
observable done-clear edge. The diagnostic's extra edge requirement can miss
a fast transition. Current logs cannot distinguish that case from a DSP command
that did not complete. The next investigation should establish reliable fresh
completion semantics before integrating automatic DSP setup/teardown; no guard
was relaxed based solely on this timeout.
