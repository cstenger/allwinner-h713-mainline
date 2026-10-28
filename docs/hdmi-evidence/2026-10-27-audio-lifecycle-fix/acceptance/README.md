# PipeWire HDMI board reboot acceptance — completed October 27

**PASS with explicit host-source qualifications.** The installed PipeWire
replacement passes physical cold startup, five orderly warm reboots, one
synced abrupt reset and functional no-source cold/runtime reconnection.
Every video/audio case passes digital route/flow checks, actual 440-Hz
capture/codec-monitor content, and operator picture/colour/tone confirmation.
No manual board health ack, service recovery, firmware relaunch, GP7 arm,
U-Boot hold or RAM startup was used during requalification.

| Case | FPS | Rejected frames | Capture xruns | Content/operator |
| --- | ---: | ---: | ---: | --- |
| warm-01 | 59.26 | 0 | 0 | PASS |
| warm-02 | 59.42 | 0 | 0 | PASS |
| warm-03 | 59.80 | 0 | 0 | PASS |
| warm-04 | 59.52 | 0 | 0 | PASS |
| warm-05 | 59.49 | 0 | 0 | PASS |
| abrupt-01 | 59.22 | 0 | 0 | PASS |

Cold baseline boot: 772696a0-8ed2-4ed7-8635-e9830aea48d7, source ready with
no board recovery; automatic HDOK at 24.518 s. No-source cold boot:
cf6a1d00-38b9-43a2-a720-f4f270499327, signal none, fbcon active/video plane
detached, automatic HDOK with GP7 zero and healthy startup units. Same-boot
reconnection eventually delivered picture/tone with no board restart.

The abrupt run has a complete drained sync marker and exact expected early
HDOK/GP7-zero/MIPS-reset census. Tone stayed healthy in repeated captures
at uptimes 105.40, 131.92 and 156.36 s, beyond the earlier failed run's
observation window; final health still passed at uptime 200.72 s. Five
units active/success/NRestarts=0, cumulative video rejects/capture xruns zero.
This is a bounded delayed-failure observation, not a long soak.

## Qualifications

* The host fixture explicitly reopens its player outputs after hotplug; this
  qualifies board recovery with a managed source, not uninterrupted-client
  recovery. Each intervention is saved in its run directory.
* The first projector-end reconnect after the no-source cold boot left the
  PC connector disconnected with zero EDID bytes. One explicit PC-end cable
  reseat restored detection. Preserve this unresolved electrical/source
  hotplug limitation; do not claim the first reconnect passed unaided.
* The five warm passes span two cold sessions due to the host interruption
  and operator poweroff after run 3; they were not five consecutive resets
  without a physical power cycle.
* The old direct GStreamer/ALSA consumer's exact internal defect is not
  isolated. Its gain/mute was correct; PCM re-prime restored sound. The
  replacement uses the same capture/DSP/codec and passed all cases above.
* PipeWire delay is configurable, zero by default. A/V latency calibration
  remains a separate task.

## Final state

Board powered down, UART **Power down** confirmed. Host projector volume
restored to **35% (raw 22937)** while the endpoint still existed, before
poweroff; test player stopped and passive UART recorder closed. Other host
audio endpoints were not changed. Installed generation and checksums verified.
Rollback backup /var/lib/h713-hdmi-speaker/backup.AaUgab is saved on the host.
Source, tests and evidence are included in the requested repository commit.
No push was performed.

[Machine-readable verdict](ACCEPTANCE-RESULT.json),
[final health](final-health.json), [host cleanup](host-cleanup.json),
[poweroff UART](final-poweroff/serial.log).

## Earlier run notes

# PipeWire speaker reboot requalification

Initial installed live checks passed. Checked poweroff confirmed. Fresh passive UART armed for physical cold cycle. Host player paused; saved original endpoint volume remains 35%, test level 100%. New cold baseline, five ordinary installed warm boots, one synced abrupt reset, no-source cold/reconnection and final checked poweroff pending.

Fresh physical cold boot 772696a0-8ed2-4ed7-8635-e9830aea48d7: exact zero preboot census, one SPL/shared launch, automatic HDOK at 24.518 s, GP7 zero, five units healthy/NRestarts=0 and installed checksums match. PipeWire capture/codec-monitor both channels 440-Hz content PASS (~0.2047/~0.2041 RMS, tone ratio ~1). Audio/startup/video gate PASS, no board service restart/manual ack. Host fixture resumed explicitly. Operator cold confirmation pending.

Operator cold confirmation: picture, colours and clean continuous tone correct. Second cold capture/codec-monitor tone-content snapshot also PASS without board intervention. Cold baseline accepted for PipeWire requalification.

Resume after host interruption: operator warm-03 confirmation recorded. Three orderly boots now digital/content/on-panel PASS. /tmp runner/socket lost, host player absent, old UART stopped; no warm-04 directory/reset intent exists. Reconstructing tools and restoring host fixture before any further reset.

Operator confirms board was switched off during interruption. Reordered remaining independent cases to use the next required physical cold cycle for no-source startup, then runtime HDMI reconnect before warm-04/05 and abrupt reset. Three previous orderly passes preserved, no reset retry/extra reset. Fresh sole UART resume-uart OPEN. No-source operator ready is pending.

No-source physical cold boot cf6a1d00-38b9-43a2-a720-f4f270499327: zero preboot census, one shared launch, GP7 zero and automatic HDOK PASS. Signal none; capture/signal/speaker/ring/health units active/success/NRestarts=0, video inactive/success. KMS fbcon active, video plane detached. No board service restart. Runtime HDMI reconnect and operator console check pending.
