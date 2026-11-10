# Production shared-startup installation trial, October 27

User explicitly approved production installation and GP6 policy change, then
reported the board unplugged for over a minute and still unpowered (ready).
Host preparation in progress. No installation/reset/latch write yet.
UART must report OPEN before board serial/mains reconnection; USB stays out.
Initial old-production cold video/colour/tone and inventory must pass before
installation. Subsequent physical cold cycle and installed-path soak follow
the approved production-preparation runbook.

Passive sole UART reader OPEN confirmed 2026-10-27 10:28:12 UTC.
No existing UART reader or mpv player found. Projector HDMI audio endpoint
is absent while board is unpowered; source playback/routing will be prepared
after hotplug. No board commands sent. Awaiting operator power-on.

Operator reported powered on. Complete old cold handoff/Linux captured. Host
HDMI auto-enabled 1280x720 60 Hz; moving pattern/tone started fullscreen on
HDMI-A-1 with explicit projector audio route, prior sink volume saved, test
level 100%. Saved spirits Wi-Fi reconnected. Cold digital health PASS, boot
ID f817b317-76af-419c-a43f-ba39d00d8c7f: DSP 0/0→1/1, audio ~48 kHz,
zero xruns; video locked 720p, ~59.64 fps, zero rejects, NRestarts=0.
Validated RTC read: GP6 HDMI, GP7 zero. All 18 installed backend checksums
match. Boot FAT not mounted yet; no fw_printenv/config installed. FAT/FIT and
saved-environment verification remain before installation. Await operator
picture/colour/tone confirmation. No production install/reset/latch write.

## Installation completed; first new cold boot pending

Operator confirmed moving video/colour/tone. Initial environment read at
configured LBA 0x49ec00 was all zero/CRC-invalid. Existing documented U-Boot
address narrowing defect explains this; active environment at LBA 0x32ec00
has valid CRC 370c1af1, hash 6eb7b7958139263f88cc0a0830b4ac33f4b4ca71b096081802b2f50f2cd205bc,
and exact expected preboot/bootcmd. Both locations remain untouched. See
hdmi-reset-controls-2026-10-20.md and handoff-2026-10-21-hdmi-reset-for-claude.md.
Mounted only /dev/mmcblk0p2 at /mnt/boot; predecessor script/FIT pins match.
UART reported a preexisting unclean FAT mount warning; no fsck/repair was
attempted. Candidate content subsequently verified; checked orderly poweroff
completed. Track whether warning recurs rather than claiming filesystem QA.

Bundle transferred/checksummed; installer dry-run passed, then one detached
install completed. Backup is exactly:
`/var/lib/h713-hdmi-startup/shared-20260413T194157-c5fec89a`.
The board RTC/calendar is stale (April); use the returned backup path, not
host date or guessed latest directory. Host rollback-backup.tar SHA256:
4baaa32c440b30d28859cfc2dd2a7574c06475ac4b5682e45e9e082d39f838f5.
All archive entries validated against record.json; rollback dry-run passed
without changes. New installed/FAT script pins and all backend/health checksums
match; only intended old manifest entries changed. Health unit enabled but
inactive/dead, status 0/no restarts. Same boot ID, GP6 HDMI/GP7 zero, kernel and
both environment regions unchanged. No manual acknowledgement or GP7 arm.
Current-boot digital health passed again after installation, video/audio live.

One checked sync/poweroff issued; SSH transport timed out after 15 s during
shutdown, so no retry. Passive UART confirms `reboot: Power down` at uptime
328.772452 s, host 2026-10-27 10:34:27.639869 UTC. Reader closed; host player
pause requested for cold cycle. No new startup execution/HDOK evidence yet.
User must unplug mains, board serial and USB >=1 minute, leave unpowered and
say ready. Arm fresh UART OPEN before serial-first/mains reconnection. Next
boot must be physical cold, not warm. Production soak has not started.

Operator confirmed post-install >=1 minute mains/serial/USB disconnect, still unpowered. Fresh sole passive reader OPEN (new-cold/serial-timestamped.log); no board commands. Await serial-first/mains reconnection for first installed shared-startup cold boot. USB stays disconnected.

## First installed cold boot: digital PASS; operator confirmation pending

New boot ID a0cdeb59-4933-41e6-bafd-b31dad5a96ca. Cold UART: GP6 zero/GP7 zero at
proper_preboot, HDMI latched before first pre_workspace, shared source-3/TCON
re-latch and handoff verified without intervention. Automatic health unit
started at 19.669 s, wrote HDMI→HDOK at 20.877 s and completed at 20.960 s;
GP7 remained zero. Dry-run then observed HDOK without writing. Unit
active/exited, status 0, NRestarts=0. No manual ack/board service restart/reset.
DSP 0/0→1/1, audio ~48 kHz zero xruns; locked 720p video 59.44 fps, zero
rejects, video NRestarts=0. See new-cold-health.json and new-cold-health-ack.log.

Host source paused across the intentional disconnected cold cycle. Resume
attempt lost IPC when player exited; first replacement used an overlong UNIX
socket path. Replaced only this host player with a short /tmp socket; verified
fullscreen HDMI-A-1, explicit projector audio device, unmuted/playing at test
100%, stream on correct sink. No board-side workaround. This first cold test
does not establish uninterrupted-host-source recovery. Host file source and
UART reader remain running. Await operator picture/colour/tone confirmation
before installed warm soak; no warm reboot has been issued.

## First installed orderly warm boot

**First installed orderly warm boot: digital PASS, soak paused for host source:**
one ordinary reboot from HDOK completed unattended through installed startup,
with no GP7 stop/RAM source. New boot `23410156-c962-4d95-99b5-ac5e2dd6e562`;
early GP6 HDOK/GP7 zero, HDMI latched before firmware, shared source/re-latch/
handoff complete. Automatic ack wrote HDOK at 21.011 s; no board service
restart/manual ack. DSP 0/0→1/1, audio ~48 kHz/zero xruns, video ~59.84 fps/
zero rejects; cold/warm comparison PASS. Host mpv lost its HDMI window report
and PipeWire moved its stream to SoundSticks while HDMI disappeared. Endpoint
returned but routing/window did not self-recover. Further reboots stopped;
host-only restoration attempts exited mpv, then a fresh host player restored
verified HDMI video/audio routing. Await operator warm picture/colour/tone.
This is functional digital recovery, **not** uninterrupted-source acceptance.
Board remains on; UART/new host player running. Four remaining ordinary runs,
SysRq-b and no-source trial not executed; fix host harness before clean soak.
[Evidence](hdmi-evidence/2026-10-27-shared-startup-production-install/README.md).

Fresh preflight (warm-01-before.json) passed; host source displayed HDMI-A-1
with stream 700→671 (projector). One detached ordinary systemctl reboot,
no GP7 arming/reset write or U-Boot stop. warm-01-dispatch.log and UART offsets
identify this run. Automatic health ack active/exited/status 0/NRestarts=0;
dry-run verified HDOK without writing. The checker also passed before host
source restoration; it validates startup and PCM transport, not audible tone.

Host failure: warm-01-host-during.json and warm-01-host-after.json record
pause=false but display-names=[] and stream 700→62 (desktop SoundSticks),
while target.object still requested the projector. Reappeared projector sink
716 was suspended. Existing stream was positively identified by original
index, media name and target.object. Host-only stream move succeeded, then
fullscreen reselection lost IPC as mpv exited. Restarted only host player;
warm-01-host-restored.json confirms HDMI-A-1, explicit projector audio,
unmuted playing stream 745→716. No board-side workaround or another reset.
This is a bench-source hotplug problem; its exact player/compositor failure
mechanism is not yet diagnosed. Preserve detailed player log, do not claim
five-run or uninterrupted-source acceptance, and do not auto-retry resets.

## Operator confirmation: first installed warm functional PASS

User confirmed moving video, correct colours and audible tone. Production
shared startup and automatic GP6 acknowledgement therefore pass the first
installed orderly warm boot digitally and on glass. Host-only player restart
was needed; uninterrupted-source/five-run acceptance is not claimed. Board
remains powered on, healthy HDOK last checked; passive UART and host pattern/
tone remain running. Further board commands/resets are paused while the host
hotplug source issue is investigated offline. Four ordinary runs, abrupt
reset and no-source trial remain unexecuted. No commit/push.

## Host-only follow-up after operator warm PASS

No additional board commands, resets or host source changes. Read installed
mpv version/manual, WirePlumber defined-target policy and crash metadata for
the exact failed test player PID 124264. `host-player-exit-diagnostic.log`
confirms SIGSEGV at 03:43:19 PDT in mpv's `vo` thread through libffi /
libwayland-client dispatch; the player detail log ends at fullscreen recovery.
This establishes a host crash during fullscreen reselection, not its precise
source-code defect. mpv is v0.41.0 (host-mpv-version.txt). The separate audio
snapshot shows target.object requested HDMI but stream 700 linked to sink 62;
installed policy permits fallback unless node.dont-fallback is set. Copied
policy source to host-audio-fallback-policy.lua; no policy was changed.

Next preparation should address the host fixture's HDMI reappearance and
verified audio/window ownership before resuming soak. Do not change the
board startup to compensate, and do not call player recovery an uninterrupted
source test. A host-only fixture that deliberately relaunches after hotplug
can test unattended board recovery, provided those interventions are explicit
in evidence; continuous-client hotplug qualification is a separate claim.
No host package update/global desktop policy change undertaken. Current warm
board remains on with operator-confirmed video/colour/tone, host player and
passive UART running. No commit/push.

## Quiet runtime interval closed, October 27 ~18:27 UTC (11:27 PDT)

User requested hands-off soak with tone muted, then correctly pointed out
that the proposed two hours had already elapsed. Host mpv software volume
was set to zero (quiet-soak-source.json), with video, HDMI audio stream,
capture/signal and speaker services left running. Baseline saved at uptime
529.1 s; same boot at final snapshot uptime 27957.83 s (~7 h 46 min),
27429 s (~7 h 37 min) beyond baseline. No extra waiting
required. No reboot or service restart was issued during this interval.

Final explicitly read-only snapshot (quiet-soak-final-readonly.json): same
boot ID, all five units active/success/NRestarts=0; locked 720p video
59.63 fps, zero cumulative rejected frames, zero capture xruns.
Capture and codec playback currently RUNNING at ~48 kHz, both owned by PID
404. Video advanced 1637232 frames since baseline
(average 59.70 fps). Host source still
fullscreen on HDMI-A-1, playing with volume 0, stream 745→716. Speaker service
has not restarted, but codec playback trigger timestamp is newer than the
boot; this snapshot is not proof of uninterrupted codec playback throughout
silence. No audibility or full-amplitude audio stress claim for silent phase.

**Monitoring limitation/correction:** 15-minute checks were promised but no
heartbeat/periodic automation was established before the turn was interrupted.
Only baseline/final snapshots and passive UART exist; do not claim a fully
monitored two-hour soak. This is same-boot long-run evidence with cumulative
counters, not a completed repeated-reset soak. No new timer was created now.

Automatic approval review rejected reuse of the existing collector because
it stages files under board /run. Did not rerun or bypass that write; instead
used the permitted read-only /proc/sysfs/systemctl snapshot with zero board
writes. One local read script had a syntax error and was corrected locally.
No hardware mutation or reset followed. Board remains on and silent; host
source and passive UART running. Shutdown not issued/requested by user in
this exchange. Four remaining warm runs, abrupt and no-source cases remain
unexecuted; original host hotplug issue remains. No commit/push.

## Final checked poweroff

**Final checked poweroff completed:** user explicitly requested poweroff.
Expected boot ID verified at uptime 28794.51 s; capture/signal/speaker/video/
health units all active/success/NRestarts=0. One sync and detached systemctl
poweroff, no retry/reset/GP7/GP6 write. Passive UART confirms
`[28803.057353] reboot: Power down` (~8 h 0 min uptime). Host test player
stopped; passive UART recorder closed. Board now powered down. Saved host
projector volume is 35% (raw 22937), but restoration failed because HDMI sink
vanished at shutdown; restore that exact endpoint on its next connection,
without changing other audio devices. No periodic automation was created.
[Evidence](hdmi-evidence/2026-10-27-shared-startup-production-install/README.md).

Host timestamp: 2026-10-27T18:41:04.730674+00:00 b'[28803.057353] reboot: Power down\r\n'
No further soaking or operator action required for this shutdown.
