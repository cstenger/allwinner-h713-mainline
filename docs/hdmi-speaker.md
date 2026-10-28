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

## Historical direct GStreamer consumer

# Persistent HDMI-to-speaker playback

The board's optional `h713-hdmi-speaker.service` forwards `hw:H713HDMI,0`
(48 kHz stereo S16_LE capture) to `plughw:Codec,0`. The computer's selected
HDMI output controls the volume; the route adds no steady-state attenuation. No computer
default selection or application routing is modified.

Each service start resolves the internal `Codec` ALSA card by identity and sets
DAC Playback Volume 43, Line Out Playback Volume 15, both Line Out Playback
Switch channels on, and Speaker Switch on. These are the settings that restored
audible HDMI music on the bench board. The original DAC setting of 63 distorted
when the source HDMI volume reached 100%; the operator confirmed clean music
at 43. This provides about 23 dB of additional amplifier headroom. The installed utility is built from
`tools/audio/alsa-ctl.c`; nothing depends on `/root/tools` or `/tmp` at runtime.

`BindsTo=` and `After=` both the signal owner and capture backend enforce
startup after HDMI is ready and stop before either owner tears down. SIGTERM
closes GStreamer's capture/playback handles; the ten-second stop timeout and
control-group kill policy bound a stalled consumer. The existing backend's
restoration and shutdown guards remain unchanged. Stopping this consumer alone
is reversible and does not stop or relaunch HDMI firmware. Normal audio
driver/DAPM behavior controls amplifier power after the PCM closes.

The `hdmi-speaker` native GStreamer consumer initially feeds zero-valued audio.
After the pipeline reaches PLAYING, it waits 300 ms and fades the samples in
over 500 ms. On SIGTERM it fades out over 100 ms, flushes 100 ms of silence
through the output ring, then closes both PCMs. This targets discontinuities
at audio startup/stop; analog amplifier power-up transients may require a driver
fix. A failed startup never fades in, and errors or unexpected EOS trigger the
service's consumer-only restart policy.

The matching device-tree handoff condition skips the consumer on the guarded
warm boot path. Only a physical cold cycle authorizes capture startup; this
service does not bypass that rule. A crash restarts only the GStreamer consumer,
not the DSP or receiver. This consumer owns the capture PCM exclusively; stop
it before running an independent HDMI recording test.

Build an independent consumer bundle, preserving the pinned backend manifest:

```
python3 tools/hdmi/build-speaker.py build/hdmi-speaker
```

Copy the bundle to the board and run `sh install-speaker.sh` inside it as root.
The installer verifies source checksums, the board model, installed HDMI units,
and GStreamer ALSA plugins; compiles the mixer utility and fade consumer with warnings as errors;
replaces only the speaker consumer; installs under `/usr/lib/h713-hdmi-speaker`
and `/etc/systemd/system`; verifies, enables and starts the unit. Target `cc`
and kernel userspace headers are installation prerequisites, not runtime ones.
An explicit `sh install-speaker.sh --update` verifies the old installed files
and unit, compiles replacements before stopping playback, and backs up the old
generation under `/var/lib/h713-hdmi-speaker`. Without that flag it refuses a
different existing bundle manifest. No bootloader, kernel, HDMI
owner or installed backend manifest is replaced.

Diagnostics: `systemctl status h713-hdmi-speaker`,
`journalctl -b -u h713-hdmi-speaker`, and
`/usr/lib/h713-hdmi-speaker/alsa-ctl list`.
Disable automatic forwarding with
`systemctl disable --now h713-hdmi-speaker.service`.

Validation and cold-boot status are recorded in
[persistent speaker evidence](hdmi-evidence/2026-10-15-persistent-speaker/README.md).

The speaker-startup kernel candidates are tracked in
[the speaker-last evidence](hdmi-evidence/2026-10-15-speaker-last/README.md).
Patch 0180 delayed external PA enable until after analog settling, but the
operator still heard two clicks on its cold test. Candidate 0181 additionally
requires running playback and delays PA enable by 200 ms after START; STOP
mutes PA immediately instead of waiting for the five-second DAPM timeout.
Its locking/deadline helper tests and kernel build pass. On the first 0181
physical cold cycle, the operator reported no startup clicks and successful
music; gain 43 was reapplied automatically. The preceding shutdown click
occurred while 0180 was still running, so shutdown-click suppression on 0181
remains unverified. See the evidence for the exact kernel and test scope.
