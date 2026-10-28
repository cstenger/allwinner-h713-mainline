# Installed HDMI reboot acceptance, October 27

Requested by user: finish HDMI reboot acceptance. Existing production shared
startup installed; prior installed cold and first orderly warm boot passed.
No new installation, bootloader prompt hold, RAM launch or GP7 arm planned.

Sequence: fresh disconnected cold baseline; four remaining orderly installed
reboots, one synced SysRq-b, then checked poweroff and a disconnected-source
physical cold boot plus runtime reconnection. Each reset dispatched once; stop
on failure. Check new boot ID, full UART launch/handoff, automatic HDOK with
GP7 zero, DSP transition, service health, video rate/rejects and audio flow/xruns.
Operator confirms picture/colour/tone. Host recovery interventions explicitly
recorded and never counted as uninterrupted-client hotplug acceptance.

Board last powered down; awaiting operator ready for initial cold cycle.
No board actions issued. Host projector endpoint absent. Previous saved volume
is 35% raw 22937 on alsa_output.pci-0000_0c_00.1.hdmi-stereo-extra2.
No commit or push authorized.

Cold boot e8ebd15e-a1c5-4c95-afb5-e814c8fb1b0a: startup/audio/video digital PASS, ~59.62 fps, zero sampled xruns; automatic HDOK at 21.154 s, GP7 zero and no unit restarts. Operator sees video but initially no tone. Host volume was 35%; player/stream and sink unmuted, board mixer 43/15 and switches on. Raised only host projector endpoint to previously validated 100% test level; awaiting audibility. Reboots remain unissued. X11 test player placed on desktop despite requested HDMI; stopped it, native Wayland replacement verified HDMI-A-1. HDMI stream has node.dont-fallback=true and actual projector sink routing. No board mixer/service changes.

Read-only missing-tone diagnosis: native Wayland player verified on HDMI-A-1,
48 kHz stereo track selected; player volume 100%, player mute false, stream
mute false, stream 876 linked to projector sink 836. Endpoint unmuted. Tone
file mean -13.5 dBFS/peak -10.5 dBFS. Raised projector endpoint from 35%
(-27.36 dB) to previously validated test 100%; restore saved 35% on completion.
Mixer via CTL=/dev/snd/controlC0 alsa-ctl list: DAC 43, Line Out 15, line
switches 1/1, Speaker Switch 1; amplifier GPIO output high. Both PCMs RUNNING,
NRestarts=0. No board mixer writes/service restarts/resets. Awaiting operator
audibility at the raised host level before any reboot.

## October 27 reboot acceptance continuation: cold audio failure

New evidence: [reboot acceptance](README.md).
Fresh physical cold boot e8ebd15e-a1c5-4c95-afb5-e814c8fb1b0a passed digital
startup/video/audio-flow gates and automatic HDOK (~21.15 s), but operator
reported moving video with no tone. Host/stream/board were unmuted; raising
only host projector endpoint 35% to 100% did not restore audibility. Board
mixer 43/15, line/speaker switches on, PA GPIO high, PCMs RUNNING.
Bounded consumer-only stop/capture/restore produced nonzero stereo tone
(RMS 0.20468, peak 0.28949). Operator confirmed tone after restoration.
No firmware restart, mixer change or reset in this diagnosis. Cold audibility
FAIL remains open; do not call this an intervention-free cold acceptance.
Proceeding with requested warm acceptance from recovered audible baseline,
with this deviation explicit. Root cause remains unresolved.

## Installed warm-02 functional PASS

One ordinary reset reached boot 711b0947-fe95-4ab6-bbe3-0bb1af1750c9.
Board services/automatic HDOK recovered with no board restart/manual ack;
~59.75 fps, DSP and audio-flow checks PASS. Operator confirmed moving
picture/correct colours/tone. Host client did not survive endpoint loss:
display-names empty, no audio stream despite endpoint return. Gate stopped
before any second reset. Explicit host IPC ao-reload, vo=gpu and loadfile
reopened existing process; no fullscreen reselection/crash. This is functional
board recovery, not uninterrupted-source acceptance. Remaining fixture now
explicitly reopens outputs once after hotplug if needed, logs intervention,
and stops on a failed source/board gate. No claim of continuous-client PASS.

Clarification: diagnostic incoming samples were captured after reopening
the capture PCM. They establish valid incoming tone in that prepared state;
they do not prove what samples the original silent consumer was receiving.
Cold root cause is unresolved, including capture/consumer/codec lifecycle.

## Warm-03 host fixture refinement

One ordinary reset reached 66c71711-36ad-4470-a4a9-540b812fd61b. Host ao-reload
and loadfile restored audio stream to the returned projector endpoint but
display-names remained empty. Source gate stopped, no repeated reset. Explicit
vo=null then vo=gpu recreated only host video output in same mpv process and
restored display-names HDMI-A-1, without fullscreen toggling or board action.
Remaining planned host fixture now includes this explicit output recreation,
logged per boot; uninterrupted-client recovery is not claimed.

Warm-03 completed digital PASS: ~59.80 fps and no sampled capture xruns;
operator confirmed picture/colours/tone. No board service restart, manual
acknowledgement, GP7 write, prompt stop or RAM launch on either warm boot.

Final pending no-source case: after warm/abrupt checks, checked poweroff,
physical disconnected cold cycle with HDMI absent at projector, require console,
healthy startup/capture/signal and automatic HDOK with GP7 zero; runtime HDMI
reconnection then source fixture recovery plus operator picture/colour/tone.
Keep all failed initial cold-audio evidence; final pass cannot erase it.

## October 27 installed orderly acceptance progress

Four remaining installed orderly reboots now digitally pass (warm-02..05):
59.36–59.80 fps, zero cumulative rejected frames/capture xruns; automatic
HDOK and GP7 zero each boot, DSP/startup/audio/video checks pass, no board
service recovery, prompt holds, RAM launches or GP7 writes. Operator has
confirmed picture/colour/tone for warm-02..04; warm-05 confirmation pending.
The prior installed warm-01 passed in the production-install record. Host
fixture now explicitly recreates only the player's outputs after hotplug
(ao-reload, vo=null→gpu, loadfile), with actual HDMI routing/window verified.
This tests board recovery with a managed host source, not uninterrupted
client recovery. Cold audibility failure on this run remains unresolved.
[Evidence](README.md).

## October 27 installed abrupt-reset result: digital PASS

All five installed orderly warm boots now have operator picture/colour/tone
confirmation (warm-01 in prior install record; warm-02..05 in current record).
One synced SysRq-b from warm-05 reached ccf94dbb-b82a-4b51-9ffb-2f1c812e07ac
through the installed startup without service teardown, GP7 arm, prompt hold
or RAM launch. Complete UART sync marker drained before reset. Digital gates
PASS: ~59.48 fps, zero cumulative rejected frames/capture xruns; DSP 0/0→1/1,
automatic HDOK, GP7 zero, units healthy/NRestarts=0. Abrupt operator confirmation
pending; no-source cold/reconnection still pending. Managed host output recreation
remains explicit, not continuous-client acceptance. Initial cold-audio silence
still unresolved and prevents claiming complete release acceptance.
[Evidence](README.md).

## October 27 final acceptance result: FAIL — audio lifecycle

**HDMI reboot acceptance is NOT complete/passing.** Four remaining installed
orderly reboots warm-02..05 pass digital checks and operator picture/colour/
tone (prior warm-01 passed in the installation record). Managed host source
recreation is explicit; uninterrupted host-client recovery is not qualified.

Installed synced SysRq-b reached ccf94dbb-b82a-4b51-9ffb-2f1c812e07ac with
complete drained sync marker, expected HDOK/zero GP7/reset census and automatic
HDOK acknowledgement; ~59.48 fps, zero rejected frames/capture xruns, no
board service recovery. **Operator abrupt audio FAIL:** picture and colour
correct, tone started/stopped twice and then never returned. Digital flow
PASS is not acoustic PASS. Host HDMI monitor while silent has RMS 0.20993,
peak 0.29999 with exact projector routing/unmuted 100% source. Both board
PCMs RUNNING, mixer 43/15 and switches on, PA GPIO high, speaker NRestarts=0.
Saved silent PCM/mixer/GPIO, codec control registers and audio clock state.
Kernel denied the bounded read-only capture DRAM /dev/mem inspection; no
protection change or alternate raw-memory probe followed.

Initial cold boot also failed audibility until a documented consumer-only
stop/capture/restore. Incoming diagnostic tone was captured after reopening
the capture PCM and cannot establish original silent-buffer content. Root
cause remains open across capture/consumer/codec lifecycle. Do not mask this
with an automatic speaker restart or claim startup fixed.

Per stop-on-failure runbook, no further reset/poweroff/speaker restart was
issued. **No-source cold/reconnection case remains unrun.** Board left powered
on in the current silent failure, host player and sole passive UART recorder
running for diagnosis. Host projector test endpoint is 100%; saved original
35% (raw 22937) still needs restoration when testing finishes. No commit/push.
Next: diagnose/fix audio lifecycle, then requalify fresh cold/abrupt audibility
and execute the final no-source cold/reconnection case.
[Evidence and machine-readable verdict](ACCEPTANCE-RESULT.json).
