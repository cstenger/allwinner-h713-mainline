# Speaker power plan — no pops, amp up while awake

**Status, 2026-11-17: phases 0–3 DONE.** Kernel 0212 is installed and the standby hook is live. Zero flagged pops in 46 events and 2 reboots (one pop on the first reboot was the old kernel going down); the positive control is still caught ([evidence](speaker-pop-evidence/2026-11-17/README.md#after-0212-same-day)). A mains power cycle (`run-cold1`) is also pop-free, by microphone and by Chris's ear; every flagged event there was his own typing or mic handling.

## Requirement

The speaker must never pop: not at boot, not at power-off, not entering or
leaving standby, and not when any player starts or stops. Making a pop
quieter does not meet this.

## Where we are (measured 2026-11-17)

| Path | How it reaches the codec | Pop protection today |
| --- | --- | --- |
| HDMI speaker (installed: `pipewire-speaker.py`, a `pw-loopback`) | PipeWire codec sink, running from boot | Kernel 0180/0181 only. (`hdmi-speaker.c`, the older route with a pre-roll and fades, was never installed in production; now removed.) |
| mpv, `gst-plane-play`, Kodi | PipeWire, mixed into the same sink | Same; while the loopback runs, there are no device edges |
| Standby (`tools/standby/h713-standby`) | Stops the players, but not the speaker service | PA stays up in standby |
| Power-off, reboot | Speaker service stop, then the rails | **Pops** (see below) |

Kernel 0180/0181 (both still marked EXPERIMENT) turn the external amp (PA,
PL2) on and off with each stream. The DAPM `Speaker` event sleeps 700 ms for
the analog path to settle. PA rises 200 ms after trigger START and falls on
STOP. DAPM powers the DAC and the headphone amp down five seconds later.

**The baseline** ([evidence](speaker-pop-evidence/2026-11-17/README.md)):

- Speaker start is silent.
- **Every speaker stop pops:** flagged 8 of 9, +31–40 dB above the room with
  the fan off. It isn't sample content: the samples are digital zero, and
  muting the DAC first doesn't help.
- The cause is `sun4i_codec_shutdown()` stopping the codec **module clock** at
  PCM close, a few microseconds after STOP drops PA, while the amp is still
  winding down.
  - A raw-ALSA test that splits STOP from close shows STOP alone is silent.
  - Close pops at gaps of 0–10 ms, faintly at 30 ms with the fan off, and is
    silent at 100 ms and above.
- PA up with nothing playing: no hiss measurable above the fan-off room.

So the pops we have today come from the clock, not the analog bias. Any
PCM close is a pop: power-off, reboot, the speaker service following its HDMI
services down, and PipeWire releasing an idle sink.

## Design

The pops are power edges: the clock, the bias and PA changing state. Only the
kernel sees them, and every path goes through them, so the fix lives there and
nothing in userspace fades or pre-rolls.

### Kernel: one speaker power state, not one per stream

Replace 0180 and 0181 with one non-experimental patch in the H713 part of
`sun4i-codec.c`:

- **State.** `OFF` → `ANALOG_UP` → `ON`, and back. On power-up: force the
  `DAC Enable`, `Left DAC`/`Right DAC` and `HP Amp` widgets on, wait for the
  bias to settle (700 ms today; re-measure), then raise PA. On power-down: PA
  off, a short hold (to be measured), then release the analog widgets. PA is
  never high while the analog path changes state.
- **Clock with the power state.** The module clock is taken on power-up and
  released only at the end of power-down, at least 300 ms after PA falls (100 ms
  measured silent, 30 ms still faint). PCM `startup`/`shutdown` stop owning
  it, so closing a PCM can never stop the clock under a live amp. This is the
  fix for the measured pop.
- **No per-stream gating.** Trigger START/STOP no longer touch PA. This removes
  the 200 ms that clips the start of every sound and the per-stream power
  edges. Closing the PCM, PipeWire suspending its sink, and `pmdown_time` stop
  mattering to the speaker.
- **Control.** A new boolean ALSA control, working name `Speaker Power`,
  default on at probe. It must be separate from `Speaker Switch`, because
  `Speaker Switch 0` freezes the PCM DMA. Writing it runs the sequence above
  from a work item and returns. The current state can be read back.
- **System PM.** Run the power-down sequence in suspend (s2idle, opt-in).
  On resume, run power-up only if the control is on.
- **Shutdown.** A platform `.shutdown` runs the power-down sequence so that
  power-off never cuts the rails with PA high. Reboot goes through the same
  path.

### Userspace

- **`h713-standby`:** after `stop_players`, set `Speaker Power` off; on leaving
  standby, set it on before anything can play. The HDMI loopback keeps running
  silently through standby. (Done.)
- **HDMI speaker:** the installed `pipewire-speaker.py` (`pw-loopback`) has no
  fades and needs none. The older direct-ALSA consumer `hdmi-speaker.c`, with
  its pre-roll and fades, was removed along with its build and install steps.
  (Done.)
- **PipeWire:** no change.

## Measurement rig

Use the host's Scarlett 2i2 with a microphone close to the projector's
speaker, gain fixed for every run. This replaces phone recordings for
iteration:

- `pw-record` runs on the host while the board's events are triggered over ssh
  from the same script. Each event is logged with a host timestamp, and the
  kernel logs the PA and analog edges with monotonic timestamps (debug build
  only). That lines up each event's window in the recording.
- **Metric:** the peak in a ±50 ms window around each edge, against the room's
  RMS noise floor with the projector on (fan running). well0nez reported 42×
  for their loud pop and 9× for the faint one; ours must sit within the
  room's own variation.
- **Positive control:** an abrupt stop of a loud 1 kHz tone, which must be
  flagged. Otherwise the rig hasn't been shown to be able to fail.
- **Final check by ear:** a cold boot, a power-off and one standby round trip,
  done by Chris in person. The microphone rig doesn't replace this.

## Phases

0. **DONE 2026-11-17, see the evidence above.** Rig and baseline on the installed 0210 kernel. Measure the positive
   control, then each event 10 times: mpv start/stop and pause mid-content,
   plane route start/stop, HDMI speaker start/stop, standby enter/leave,
   power-off, cold boot. Also record 60 s of idle hiss with PA on (during a
   silent stream). This tells us what pops today, including paths nobody
   has checked.
1. **Register check.** Read-only: does H713 implement `DAC_VOL_CTRL` (`0x04`),
   and what does the DAC output with DRQ off (zero or the last sample)?
2. **Kernel patch.** Replace 0180/0181. Host build, plus helper tests of the
   state machine (ordering, races between the control, suspend and shutdown).
   Include mutation checks that fail when PA is raised before the analog path
   has settled.
3. **Install and measure.** Run the phase-0 matrix again, plus 30 standby
   round trips and the idle-hiss comparison. Pass: zero flagged events, and
   the positive control still flagged.
4. **Userspace.** Standby hooks, `hdmi-speaker` simplification, then the
   phase-3 matrix again.
5. **Chris's listening pass**, as above.

## Open risks

- **Idle hiss** with PA up and nothing playing: not measurable at the mic,
  even in standby with the fan off (−42.3 vs −41.7 dBFS). Chris's
  listening pass still decides.
- **PL2 state before the driver probes.** If U-Boot or reset leaves PA high
  while the bias comes up, the boot edge happens outside our sequence.
- **Crashes and watchdog resets** skip `.shutdown`. The rails drop with PA
  high. Probably unavoidable; it gets measured once to know its size.
- **The DAC's idle output.** If the DAC holds the last sample when DMA stops,
  a stream cut mid-content leaves a DC step in front of a live amp. Phase 1
  answers this.
