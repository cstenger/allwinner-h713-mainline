# Final result

The PipeWire replacement is installed and **board reboot acceptance passes
with host-source qualifications**. Physical cold startup, five orderly warm
boots, synced abrupt reset and functional no-source cold/runtime reconnection
passed digital, content and operator checks. Final checked poweroff and host
volume/player/UART cleanup completed. Exact old internal failure, unassisted
first hotplug and A/V calibration remain outside the proved result.

[Completed acceptance](acceptance/README.md). Earlier diagnosis and installation
notes follow.

# HDMI audio lifecycle: PipeWire replacement, October 27

## Diagnosis and limits

Preserved abrupt boot ccf94dbb-b82a-4b51-9ffb-2f1c812e07ac had missing acoustic
audio despite healthy host tone, advancing PCMs, correct codec gains/switches
and enabled PA. Exact upstream 1.26.2 volume layout plus read-only GDB object
inspection found mute=0, volume=1, current_volume=1, current_vol_i16=2048.
The debugger pause caused a PCM re-prime (logged), and the operator heard
pulsing static then clean tone, without consumer process restart. This is
stream-lifecycle/timing recovery, not a saved mute setting.

A bounded old-route observer showed matching nonzero input/output samples
and recovered from one forced 600 ms pause; it did not reproduce the original
boot/hotplug fault. Thus the precise old GStreamer/ALSA failure mechanism is
not yet isolated. Do not claim an upstream GStreamer or codec-driver defect.
The selected fix replaces that direct two-device consumer with the already
planned PipeWire loopback, using the same capture driver, DSP and codec.

## Installed candidate

Speaker-only bundle: build/hdmi-pipewire-speaker-2026-10-27. Installed once
after checksum verification, build and systemd validation. Exact old-generation
backup /var/lib/h713-hdmi-speaker/backup.AaUgab copied to speaker-rollback-backup.tar
on the host. Bootloader, FIT, backend modules, firmware and GP6/GP7 policy
unchanged. No commit or push.

pipewire-speaker.py resolves Codec/H713HDMI by ALSA identity and locates unique
PipeWire nodes for those actual cards. Root client uses the existing media-user
server (/run/user/1000); no new daemon/default-device selection. Explicit
stereo 48-kHz targets, no fallback, desired latency 20 ms. Optional
H713_HDMI_AUDIO_DELAY_SEC in /etc/default/h713-hdmi-speaker is finite 0..0.5 s;
default zero. Photometric A/V delay calibration is not completed by this work.

ExecStopPost refuses foreign capture clients, suspends only the selected HDMI
source and verifies its PCM closes before backend teardown. Live ordered
stop/start PASS, backend capture/signal stayed active and restarted loopback
verified. Mixer gain remains DAC=43, Line Out=15; switches on.

Health checker requires a current-boot verified stereo graph and both PCMs
owned by the actual media-user PipeWire process. Read-only routing queries
follow audio-flow settling. Initial immediate post-install query was too early;
subsequent graph verification passed without restarting the service.

## Validation so far

11 lifecycle tests PASS, 13 implementation mutants caught; warm-checker route
refusal cases PASS and 4 mutants caught. Existing 46 warm tests PASS. New
code/bundle compile, checksum and systemd validation passed.

Transient PipeWire trial: operator clean continuous tone; source RMS 0.204677
and sink monitor 0.204664, same codec and hardware capture. Trial restored old
route after bounded duration. Persistent route: live stop/start PASS; one
600 ms loopback-client pause recovered with same process and NRestarts=0;
440-Hz sample-content gate at capture and codec monitor PASS; operator picture
and tone correct. Updated flow check ~48 kHz, zero new driver capture xruns.

Cold/repeated orderly/abrupt/no-source acceptance of this implementation is
PENDING. Board will now receive checked poweroff, then physical cold cycle.
Host projector test endpoint still 100%; restore saved 35% raw 22937 when
finished. Source player and passive UART retained for the next cold boot.

Checked pre-cold poweroff completed; UART Power down confirmed in ../2026-10-27-reboot-acceptance/pipewire-pre-cold-poweroff/serial.log. Old passive recorder closed; fresh acceptance UART armed. Host source paused. Board powered down pending physical cold cycle; no reboot PASS yet.
