# HDMI audio through PipeWire

**October 27: PipeWire replacement installed; board reboot acceptance PASS with host-source qualifications.**
`h713-hdmi-speaker.service` now connects the existing media-user server's HDMI
capture node to the Codec sink via `pw-loopback`. It resolves ALSA identities,
refuses ambiguous/fallback routes and checks stereo graph links plus PCM
ownership. Video continues directly through KMS. Hardware gains remain DAC 43
and Line Out 15.

On ordered stop the loopback exits, then `pipewire-speaker.py release` suspends
only HDMI capture and verifies the PCM closes before the backend can tear down.
Other capture clients cause refusal, preserving the existing shutdown guard.
The server is the established `/run/user/1000` media session.

Build/install use the existing `build-speaker.py` / `install-speaker.sh --update`
workflow. Check with `python3 /usr/lib/h713-hdmi-speaker/pipewire-speaker.py check`.
Optional `H713_HDMI_AUDIO_DELAY_SEC=...` in `/etc/default/h713-hdmi-speaker`
adds 0..0.5 s delay; zero by default, latency calibration remains outstanding.

The direct GStreamer route failed cold/abrupt audibility despite digital
progress. Its gain filter was demonstrably unmuted; PCM re-prime restored
sound. Exact old failure mechanism remains unisolated. The replacement passed
cold startup, five orderly warm boots, a synced abrupt reset and functional
no-source reconnection, with verified content and operator checks. Host output
recreation and a PC-end cable reseat are explicit source qualifications. [Design, diagnosis and evidence](hdmi-evidence/2026-10-27-audio-lifecycle-fix/README.md).

[Completed acceptance and qualifications](hdmi-evidence/2026-10-27-audio-lifecycle-fix/acceptance/README.md).

## Speaker power: no pops (kernel 0212)

The codec driver owns the amplifier. Kernel 0212 makes the module clock,
the DAC → headphone-amp → line-out path and the external amplifier (PA, PL2)
one power state. It is held while the projector is awake, independent of
streams. Up: clock, path, 700 ms settle, then PA. Down: PA off, 300 ms, then
path and clock. Streams, PCM closes and this service stopping never move PA,
so the route needs no fades or silent pre-roll.

`h713-standby` turns the codec's `Speaker Power` control off on entry and on
on exit. Suspend, reboot and power-off take it down in the same order.
Measured with a microphone: before 0212, every PCM close popped. The codec
clock stopped microseconds after PA fell. After 0212: no flagged pop in 46
events and a reboot. See the
[speaker power plan](speaker-power-plan.md) and the
[evidence](speaker-pop-evidence/2026-11-17/README.md).

## Install and diagnostics

Build the bundle with `python3 tools/hdmi/build-speaker.py build/hdmi-speaker`,
copy it to the board and run `sh install-speaker.sh` inside it as root (or
`--update` over an existing installation). The installer:

- verifies source checksums, the board model, the installed HDMI units and
  the PipeWire tools;
- compiles the mixer utility (`tools/audio/alsa-ctl.c`) with warnings as
  errors;
- replaces only the speaker consumer under `/usr/lib/h713-hdmi-speaker` and
  `/etc/systemd/system`;
- verifies, enables and starts the unit.

`--update` verifies the old installed files and unit and backs up the old
generation under `/var/lib/h713-hdmi-speaker`. Without it, the installer
refuses a different existing bundle. No bootloader, kernel, HDMI owner or
installed backend manifest is replaced.

Each service start resolves the internal `Codec` card by identity and sets
DAC Playback Volume 43, Line Out Playback Volume 15, both Line Out Playback
Switch channels and Speaker Switch on. The original DAC setting of 63
distorted at 100% source volume; 43 was confirmed clean.

Diagnostics: `systemctl status h713-hdmi-speaker`,
`journalctl -b -u h713-hdmi-speaker`, and
`/usr/lib/h713-hdmi-speaker/alsa-ctl list`. Disable automatic forwarding
with `systemctl disable --now h713-hdmi-speaker.service`.

## History

The first route (October 15) was a native GStreamer consumer from
`hw:H713HDMI,0` to `plughw:Codec,0`. It fed silence, faded the samples in
after 300 ms and out on stop, to mask startup and stop clicks. It was replaced
by the PipeWire loopback on October 27, and its source
(`tools/hdmi/hdmi-speaker.c`) was removed on November 17 once 0212 had
removed the pops at their source.

Records of that period:
- [persistent speaker evidence](hdmi-evidence/2026-10-15-persistent-speaker/README.md);
- [speaker-last evidence](hdmi-evidence/2026-10-15-speaker-last/README.md),
  covering the per-stream PA gates 0180/0181, which 0212 replaces.
