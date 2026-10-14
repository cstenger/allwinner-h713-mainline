# Same-open HDMI stream recovery, 2026-10-14

**PASS: source-rate transitions and physical HDMI cable recovery with capture
kept open, followed by full audio teardown.**

After a physical cold boot/manual U-Boot stop, the guarded single MIPS launch,
verified source3 worker transition, preserved FIT and RAM-only IRQ115/113
correction passed. The firmware-lifetime receiver owner and managed TVFE/DSP
initialized. The canonical audio EDID fixture rebuilt the same extended SCP
helper SHA256325e74d77bd6ddc9d3b0558add6011f68cc95e8d4aae15818338d67f494c92ae.
The original empty firmware search path was restored.

## Source-rate transitions

One48-second ALSA capture remained open while actual host playback hardware
changed48->32->44.1->48kHz. Each host rate was verified from hw_params;
the capture stayed RUNNING with owner PID1292 and fixed48kHz stereoS16_LE
through every phase and gap. Alternating normal/swapped1kHz/2kHz channels
passed both pointer-indexed settled recording windows in every phase (8/8).
The recording has2,304,000 frames and a zero-filled last second. No recorder
overrun, no new driver XRUNs; all playback/recording/signal helper exits0.
Capture closed and transient SCP/DDC helpers restored/removed successfully.

[Successful result](bench/rate-transitions2/result.json),
[summary](summary.json), [build snapshot](build-manifest.json).

The first attempt failed in host-side status parsing before tone playback:
ALSA pads `owner_pid`/`hw_ptr` keys with spaces. Its bounded reader/helper
closed/restored. The parser now strips field names; native controls cover
this real status format, missing/stale/wrong-channel audio, incomplete frame
counts, contaminated silence and non-RUNNING capture. No DSP retry, reinit or
reload was used between tests. The failed attempt is retained in
`bench/rate-transitions`.

## Physical cable test

The successful retry (`bench/physical-reconnect2`) held HPD for one150-second
window and recorded120 seconds (5,760,000 stereo frames). The source observed
physical connector loss at20.676 seconds and return at31.656 seconds. Capture
stayed RUNNING with PID2055 and unchanged trigger_time while unplugged and
after return. The recording has17 initial normal-channel windows, then16
fresh swapped-channel windows, in order. The last second is zero-filled;
no recorder overrun and zero new driver XRUNs. Recording and signal helper
exited0; capture closed and SCP/DDC helpers restored/removed successfully.
See [physical result](bench/physical-reconnect2/result.json).

The previous attempt's40-second operator window expired without observed
cable removal. The user subsequently confirmed they had unplugged the cable,
but that action was not captured in the observation window and was not counted
as a pass. Its bounded cleanup passed and no DSP retry/reload was needed.
The new attempt allowed70 seconds to start unplugging and20 seconds for return,
within the unchanged120-second recording and150-second HPD bounds. The user
confirmed the new unplug/replug and its connector transitions were observed.
See [retry build snapshot](physical-retry-build-manifest.json).

## Final teardown and board state

After both recovery tests passed, audio unload restored all22 DSP graph words
with readback, SPDI1/bridge/AudioTop/IHB, and15 TVFE clock words plus bus/reset.
Receiver clients returned to0, firmware_pinY, edid_readyY, clock_count4,
init_error0; both receiver domains remain active and MIPS responds.
WirePlumber is active and the original empty firmware search path is restored.
Audio and transient SCP/DDC helpers are absent. No capture/listener remains.
See [teardown](bench/audio-unload.log).

The volatile DSP patch remains until physical cold boot. A new managed audio
initialization requires cold DSP versions0/0. Do not reload to bypass a DSP
failure or force receiver removal while MIPS is live.

This establishes one physical hotplug recovery and settled recovery across
source-rate changes on open captures. It does not establish gap-free audio at
transitions, repeated hotplug endurance, hours-long recording, measured clock
drift, automatic boot/shutdown or suspend. Text evidence is retained alongside
local raw recordings; the checkpoint8244151 predates these recovery changes.
