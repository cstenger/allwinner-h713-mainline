# Persistent HDMI speaker consumer, 2026-10-15

The preceding transient route produced audible music after enabling the codec
mixer; the operator confirmed it. The same GStreamer pipeline and mixer values
are now installed as a persistent, enabled system service.

Installed unit: `/etc/systemd/system/h713-hdmi-speaker.service` (Transient=no).
Installed runtime: `/usr/lib/h713-hdmi-speaker`; no `/tmp` or `/root` dependency.
No host default-output or Cider-routing commands were issued.

Runtime verification in `runtime-test.log`: stopping only the consumer closes
the HDMI capture and codec playback PCMs while both owners stay active. After
deliberately muting both Line Out switches and zeroing Line Out volume, starting
the service reapplies 15/on/on and opens both PCMs RUNNING. Target systemd
verification passed. `BindsTo` and `After` include both signal and capture,
giving speaker → signal → backend shutdown order.

**Full shutdown and automatic cold startup: PASS.** From active playback on
boot `2b0fa076-afda-4362-8191-fe52c99140a5`, an orderly poweroff was requested.
`previous-shutdown.log` shows the speaker consumer stopped successfully before
signal stop began. The signal then restored EDID/HPD, SCP SRAM/vectors and DDC
ownership before backend stop. The backend reported 22 DSP and 15 TVFE words
restored, MIPS parked and receiver removed. The operator confirmed lamp/fan off.

After operator physical power removal/reconnection, boot
`6b7a06a5-63e0-413a-afdc-3f74bde6fda0` started all three enabled units without
manual intervention. `cold-start.log` proves capture → signal → speaker start
order, automatic mixer initialization (63, 15, on/on, on), and both capture and
codec playback PCMs RUNNING under PID 427. The persistent speaker unit is active
with ConditionResult=yes and its `/etc` fragment. No warm MIPS relaunch or guard
bypass occurred. Kernel journal entries for the prior boot were unavailable;
shutdown restoration evidence is the backend's saved journal summary.

**Audio-quality correction after the cold test:** automatic startup and service
ordering passed, but the operator reported clicks and then distorted music.
The HDMI capture contained music (peak 16,961, RMS 6,783.63 in a 76,800-frame
sample), capture reported zero XRUNs, and the codec clock was the correct
49.152 MHz for 48 kHz playback. The host HDMI volume was now 100%, versus 40%
during earlier clean playback; the signal was about 24 dB louder.

Reducing board DAC gain from 63 to 43, without changing the computer's volume
or routing, produced operator-confirmed clean but quieter music. This confirms
excessive board gain as the cause of the reported distortion. It does not
independently establish the cause of the initial startup clicks, which changed
after restarting the consumer for a diagnostic capture.

Gain 43 is now persistent in `enable-mixer.sh`; installed source checksums were
updated and rollback copies retained. `gain-fix.log` confirms that restarting
only the consumer reapplied 43/15/on/on/on, all three HDMI services remained
active and capture XRUNs stayed zero. A second cold cycle with the gain fix passed automatic initialization and
clean ongoing playback, as detailed below. Scope: one physical cold cycle and one ordered shutdown;
clean sound confirmed at corrected gain on that boot.

## Corrected-gain cold cycle

Boot `14e9f021-8cbd-4fe2-a052-1138d27aaefc` automatically applied DAC gain 43
and Line Out 15/on/on, Speaker on. All three services started in order with
zero restarts; both PCMs were RUNNING and capture XRUNs were zero. No route
restart, mixer adjustment, host output-selection or application-routing change
was made during verification. The operator reported: "Clean music; no clicks
or static except when the audio system is brought up." Thus repetitive
clicking/static during music is absent on this cold boot, but an audible
startup transient remains; its cause and suppression are not yet established.
See `gain-cold-start.log`, `gain-previous-shutdown.log` and `gain-cold-cycle.json`.
