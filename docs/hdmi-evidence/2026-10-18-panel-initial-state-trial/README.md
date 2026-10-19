# Initial panel state: recoverable U-Boot trial, 2026-10-18

Trial proper installed at LBA `0x49ac00`, 1867 sectors, SHA-256
`4391dfa07bcf396b5096714814e933c7b59cff408b7a9964163812f686283880`.
See `manifest.json`, the [historical installer snapshot](historical-scripts/install.sh.txt),
`install.log` and retained local backups.
The full 2 MiB region tail beyond the image, rescue slot, SPL and environment
were verified unchanged after writing. Kernel/startup script unchanged.

Rollback to the prior stage-2 image (`cf1941d6...`) from Linux:

```sh
sh /root/panel-initial-state-trial/rollback.sh
```

This script verifies the backup and readback; reboot separately. Identical
backup/scripts are retained in this host evidence directory. If proper cannot
start, the previously rehearsed FEL rescue SPL and existing rescue slot remain
available: see `docs/uboot-lamp-flash-plan.md`. That older rescue boots an older
known-good proper (`c882461d...`), not the current stage-2 rollback. To restore
the exact stage-2 version from a rescue prompt, transfer the saved 1867-sector
image to RAM and write LBA `0x49ac00`, count `0x74b`, with hash/readback checks.
Do not overwrite SPL, environment or the rescue slot.

## Validated trial result

Three independent cold/first-warm pairs passed visually with HDMI connected
at both ends and the PC output enabled. Trial1 also passed a second warm
reboot. In the planned pairs: **3/3 cold boots and4/4 warm boots showed logo
and console; no lit-but-black result observed.** The preliminary warm check
also reached a visible console but is separate from this count. The initial
installation reboot lacks U-Boot capture and has no visual confirmation.

| Independent trial | Cold boot | First warm boot | Extra warm boot |
| --- | --- | --- | --- |
|1|Logo + console; cold HDMI handoff/services verified|Logo + console; request uptime55.54s|Logo + console; request uptime147.26s|
|2|Logo + console; cold HDMI handoff/services verified|Logo + console; request uptime70.41s|Not run|
|3|Logo + console; cold HDMI handoff/services verified|Logo + console; kernel restart uptime77.788714s; request uptime unavailable|Not run|

Each cold boot ran the new initial-off operation once, committed the logo,
completed the cold HDMI handoff and had capture/signal/speaker services active.
Each warm boot ran the new operation, committed the logo and Linux adopted
1280x720; HDMI services inactive on warm boots as intended by the GP6 latch.
No HDMI disconnects or diagnostic TCON accesses were introduced by the agent.
Eight captured startups (including the preliminary warm check) show roughly
3.007s between the off-state log and first logo-record completion; see
`off-hold-host-intervals.json`. These UART observations do not measure physical
supply discharge. Three seconds is still a conservative bench interval.

The trial proper remains installed; rollback and the previously proven FEL
rescue remain available. Board left showing console after trial3 warm boot;
passive reconnecting serial capture left running. No further reboot requested.

This meets the initial repeated cold/warm boot check, not production
reliability acceptance. No matched54s second-warm test was run (the extra
second warm request was147.26s). Live HDMI video/audio correctness was not
verified by these service-state checks. Longer repetitions, abnormal resets,
and actual capture/audio checks remain; rail measurement is required before
claiming a physical minimum off interval. Root cause beyond the demonstrated
initial-state timing gap remains unproven.

## Capture and observations

The [original recorder snapshot](historical-scripts/serial-capture.py.txt)
records raw bytes and host timestamps and reconnects after USB removal. The first detached recorder exited with its launching process;
the installation warm boot has only late kernel output, not U-Boot, and is
excluded from sequencing evidence. It did reach Linux (see
`install-boot-linux.txt`). A foreground persistent execution session now owns
the recorder; the next warm check is fully captured.

An existing `systemd-growfs-root.service` failure was present before flashing.
HDMI units are intentionally inactive on warm boots due to the once-per-power-
cycle latch; cold trials must verify the cold HDMI handoff and active units.

## Protocol

HDMI stays connected at both ends; source remains enabled. Do not clear RTC
GP6, access TCON registers, or add diagnostic display writes. Use normal
startup throughout. Record visual results separately from serial success.

For each independent cold trial: remove mains and serial/USB power for at
least60 seconds, reconnect serial first and then mains. Verify initial-off
log, logo commit, cold HDMI handoff, Linux display adoption and active HDMI
services. Then reboot around70s Linux uptime (record actual uptime), confirm
warm initial-off log/logo commit/Linux adoption, and obtain visual result.
Run a prompt second warm boot once the operator confirms the first. Repeat
at least3 independent cold/first-warm pairs; do not claim reliability from a
single pass. More cycles and abnormal reset/capture/audio checks remain before
production acceptance. UART timing indicates execution timing, not physical
panel rail discharge; a scope is needed to verify electrical hold/discharge.

## Results

Installation warm boot: Linux reachable and 1280x720 adopted; no visual result
recorded, and missing U-Boot capture excludes sequence verification.
Fully captured warm check: patched Oct17 23:54:45 banner; initial-off log,
3.006898s host interval until first logo records applied, logo committed and
Linux adopted1280x720. Operator confirms Linux console currently visible; logo appearance was not
separately confirmed. HDMI units inactive as expected
on warm boot. See `warm-check-result.json`, `warm-check-linux.txt` and
`warm-check-serial.log`.
Cold trial1: patched off-state sequence and logo commit captured, cold HDMI
handoff verified, Linux adopted1280x720, capture/signal/speaker all active at
uptime32.29s. Operator confirms logo and console visible. First warm reboot sent at
uptime55.54s with all HDMI services active beforehand. New off hold, logo
commit and Linux720p adoption captured; operator confirms logo and console visible. Second warm reboot sent
immediately after confirmation, actual uptime147.26s (not a matched54s prompt
control); operator confirms logo and console visible again.
Cold trial1 and both subsequent warm boots passed visually; this is one
independent cold-trigger pair, not three independent trials.
See `cold-01/`.

Cold trial2: operator confirms logo and console; cold HDMI handoff verified,
all HDMI services active at20.29s, PC HDMI connected/enabled720p. First warm
reboot sent at70.41s Linux uptime; patched off sequence, logo commit and
Linux720p adoption verified. Operator confirms logo and console visible. See `cold-02/`.

Status before trial3: two independent pairs had passed; see validated trial
result above for the completed three-pair outcome.

Cold trial3: patched initial-off sequence and logo commit captured, cold HDMI
handoff verified, Linux adopted720p and all HDMI services active at20.93s.
Operator confirms cold logo and console. First warm reboot executed; UART
records kernel restart at77.788714s uptime. The pre-reboot SSH client lost
output and remained stale, so exact command-request uptime is unavailable;
the stale client was terminated and no retry reboot sent. New off-state
sequence, logo commit and Linux720p adoption verified; warm visual result
confirmed: operator saw logo and console. See `cold-03/`.

## Subsequent live-media check

Fresh cold session verified managed startup and sampled live720p video
(eight distinct pattern frames, ID/stripe checks pass; single-copy diagnostic
limitations recorded). Bounded digital audio recording passed48/32/44.1kHz
HDMI input with stereo tone/silence checks and zero XRUNs. Speaker restored;
both PCMs RUNNING. Eight-second audible tone sent; operator response pending.
See `live-media/README.md`. This updates the earlier capture/audio-unverified
status only within that bounded test scope.

Listening update: operator confirmed direct-codec playback and then normal
HDMI forwarding of the identical waveform in cold sessionb3478260…. Earlier
HDMI replay was silent; diagnostics restarted the speaker consumer and
exercised direct codec playback, so unattended audible-start reliability and
cause of the silence remain unproven. See `live-media/README.md`.

Clean cold-start audible update: PASS. Operator heard the same waveform
through normal HDMI forwarding on boot4b89c33b… before any speaker restart,
direct codec playback or cable reseat. Speaker PID unchanged, restarts0,
both PCMs RUNNING and XRUNs0. One clean listening pass; earlier silence
remains unexplained. See `live-media/cold-listening-01/`.

## Abnormal-reset recovery: PASS

Single immediate SysRq-b reset at465.752331s Linux uptime after filesystem
sync, with capture/signal/speaker active and both audio PCMs RUNNING.
No normal service stop or device shutdown requested. New U-Boot initial-off
hold and logo commit captured; Linux adopted720p. Operator confirms logo and
console returned; HDMI connected at both ends throughout. Warm HDMI guard
retained, so capture/signal/speaker inactive afterward as intended.

See `abnormal-reset-01/` for source-reviewed method, saved pre-reset state,
serial capture, before/after boot IDs and result. This demonstrates one
emergency reset recovery, not autonomous watchdog expiry or every possible
hung-kernel/reset failure. No extra reset or firmware changes performed.

The initial validation set is complete:3 independent cold/first-warm visual
pairs,1 extra warm visual pass, bounded sampled video and digital audio,
a clean cold-start audible pass, and this emergency-reset visual pass.
Earlier transient audio silence remains unexplained; long-term reliability,
full-rate video and broader fault coverage are outside this completed set.
Trial U-Boot remains installed; rollback/rescue retained. Serial capture left
running. Board left at visible Linux console after the emergency warm reset.

## Normal build integration

The validated source is now part of `patches/u-boot/series` and both normal
build entry points. `UBOOT_SOURCE_COMMIT` pins320a17f71d41…; preparation
exports that revision without modifying the submodule, applies the tested
shared-DT/regulator prerequisites and focused initial-off patch, and syncs
kernel DT/bindings/CCU inputs into a content-addressed source cache. DDR3
configuration and tested display/clock/PHY/DT sources match the validation
worktree. Full DDR3 and LPDDR3 builds pass (LPDDR3 hardware untested), along
with11 native helper cases, shared-tree drift checks and source-cache checks.
Artifacts record inputs and hashes; new build banners/timestamps differ.

No new image was flashed during integration. The board retains the validated
trial proper. [The current runbook](../../uboot-panel-initial-state.md)
consolidates build, test limitations, exact stage-2 rollback and FEL rescue
instructions. `build-integration-result.json` records the resulting artifacts.

## Committed evidence scope

The commit keeps validation summaries, selected serial/health transcripts and
the rollback script. Firmware backups, binary images, media captures and the
continuously appended parent serial logs remain local and are not in Git.
Their paths and hashes above identify retained bench artifacts; preserve them
separately for hardware rollback. Older diagnostic directories referenced by
this historical record may likewise be local evidence.


## Support-file cleanup, October 18

The [support manifest](support-files.json) identifies all 17 files reviewed
against the original untracked-file inventory. This is archival cleanup of
existing observations; no additional boot, reset, playback or capture was run.

The three cold trials now include readable `cold-01/serial.txt`,
`cold-02/serial.txt` and `cold-03/serial.txt`, plus their original setup-status
notes. The notes say when the session was armed; they are not visual results.
The command records `install-reboot-command.log` and
`warm-check-reboot-command.log` retain the original boot IDs and request uptimes.
The installation reboot still has no U-Boot capture or visual pass.

The listening trial's `live-media/cold-listening-01/serial.txt` and `status.txt`
support its existing boot/result record. `live-media/cold-serial.txt` is the
partial early-boot capture from the initial digital media session, not another
complete boot verification. The derived `live-media/video-first-frame.png`
shows sampled framebuffer content with the host taskbar over the top band;
it is not a photograph or proof of panel output, nor a full-rate video test.

Serial text views retain every decoded line: CRLF becomes LF, invalid UTF-8
bytes and non-printing controls are represented visibly. The manifest records
both original raw and exported text hashes. Original per-trial raw `.log`
files, continuous parent captures, media and byte-offset bookkeeping stay local.

The installer, reset trigger and media wrappers are retained as
[exact historical text snapshots](historical-scripts/README.md). Review found
session-specific assumptions and assertion-based guards, so they have not been
promoted to reusable hardware tools. The passive recorder alone is promoted to
`tools/serial/capture-panel-validation.py`, with explicit device/new-directory
arguments, fatal output-error handling and offline reconnection tests.


Cleanup checks: five fake-UART tests pass, including reconnect, EOF, setup
failure, existing-output refusal and fatal full/short log writes. All 17
source/evidence hashes match the prior inventory; historical Python/shell
snapshots pass syntax checks without execution. Documentation links resolve.
The four complete cold captures retain off-hold, logo-commit, cold-handoff
and Linux-adoption witnesses; the initial media capture ends before adoption.
