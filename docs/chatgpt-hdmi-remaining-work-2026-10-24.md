# HDMI-in: remaining work, for ChatGPT (2026-10-24)

<!-- pipewire-acceptance:start -->
## Current PipeWire board reboot acceptance — completed October 27

**PASS with host-source qualifications.** Installed PipeWire audio passes
physical cold startup, all five orderly warm reboots and a synced abrupt
reset, including actual 440-Hz capture/codec-monitor content and operator
picture/colour/continuous-tone confirmation. Zero rejected frames/capture
xruns and no board service recovery on these runs. Repeated abrupt audio
checks remained healthy through 156 s; final same-boot health passed at 200 s.
No-source cold startup and same-boot reconnection functionally pass. The PC
needed one cable reseat after its first reconnect remained undetected;
unassisted first-reconnect/continuous-client hotplug are not qualified.
Five warm passes span two cold sessions due to the interruption after run 3.
Exact retired direct-consumer mechanism remains unisolated; A/V delay
calibration remains separate. Board powered down, host volume restored to
35%, test player/serial recorder stopped. Source/tests/evidence included in the requested commit; no push.
[Verdict, qualifications and evidence](hdmi-evidence/2026-10-27-audio-lifecycle-fix/acceptance/README.md).
<!-- pipewire-acceptance:end -->

You are picking up the HDMI-input feature of an open Linux port for the
HY200 projector (Allwinner H713, MIPS display co-processor). Read this whole
file first, then
[handoff-2026-10-24-panel-source-for-chatgpt.md](handoff-2026-10-24-panel-source-for-chatgpt.md)
for how the video path works, then the source documents each task names.
The user (Chris) operates the board and the source PC; you plan, build,
test offline, and ask before anything touches the board.

## Where the feature stands

* **Working and installed on the board** (cold boots): HDMI video reaches
  the panel at about 60 fps with correct colour (route B: V4L2 bridge →
  NV12 dmabuf → `kmssink` on the KMS video plane). The panel switches by
  itself: signal locked → HDMI, signal lost → Linux console, short host
  mode-sets → brief black. HDMI appears about 21 s after power-on.
  Design record: [hdmi-panel-source-design-2026-10-23.md](hdmi-panel-source-design-2026-10-23.md)
  §10.25–§10.26. Commits `3a797cc` (route B + switching) and `8a6d771` (the
  investigation behind it), on branch `h713-letterbox`, **not pushed**.
* **HDMI audio** plays through the internal speaker on cold boots
  (`h713-hdmi-speaker.service`, [hdmi-speaker.md](hdmi-speaker.md)).

## Rules you must follow

**Hardware (any violation can wedge or damage the board):**
* Never read `0x07091000`–`0x07091fff` from ARM; a single read wedges the SoC.
  Never touch `0x06940000`. GP7 is reserved for the existing reboot-mode
  handoff; the user clarified on October 24 that its one-shot bootloader-stop
  use is authorized. Do not repurpose it. GP6 is the startup latch.
* PB5 drives the lamp **and** the fan: never hold it low for long.
* After any MIPS source change, re-latch the 720p TCON timing
  (`0x05880020/24`).

**Process:**
* **Ask before every board action that writes, installs, reboots or changes
  the panel.** Read-only checks over ssh are fine.
* Operator-timed tests: describe the test, end your turn, wait for the
  user's "ready". One "ready" covers the whole unattended sequence.
* **A cold boot** means: serial and USB unplugged at the board, power off
  for at least 1 minute, then power on.
* **The HDMI source PC is the machine you run on.** Never ask the user to
  log out or reboot it while a board command depends on your session; start
  long board commands detached (`setsid nohup … > /root/log 2>&1 &`).
* Negative/guard tests use dry-run modes only, never a real write.
* Fix root causes rather than adding workarounds.
* Every claim needs evidence: put logs under `docs/hdmi-evidence/<date>-<topic>/`
  with a README, and update the design doc section and the handoff file as
  each step lands, so whoever comes next can continue.
* A passing test suite must be able to fail: for each new test, change the
  code under test so the test should fail, and confirm that it does.
* Commit only files your work changed, and only when the user asks. Push only to
  `cstenger/*` forks, only when asked (git push needs the sandbox off; the
  1Password SSH agent signs it).

**Board access:**
* ssh: `ssh -F /dev/null -o BatchMode=yes root@192.168.4.1`
* Serial: `/dev/ttyUSB0` (the adapter stays on the host)
* Board root fs has only ~170 MB free: never stream video frames to a file
  there.

## Tasks, in priority order

### 1. HDMI after a warm reboot (highest value)

**Problem:** `systemctl reboot` leaves the panel on the console with no HDMI
video or audio until a cold boot. The installed U-Boot's warm path doesn't
set `/chosen/h713,hdmi-boot-v1`, so `h713-hdmi-capture`, `-signal`,
`-speaker`, and the new `-ring`/`-video` units all skip (condition unmet).
Evidence: `docs/hdmi-evidence/2026-10-23-panel-source-stage1/stage5-install/warm-reboot.log`.

**Already done:** one warm boot that runs the *same* sequence as a cold boot
(logo → MIPS launch → source 3 → 720p re-latch → handoff) passed on
2026-10-23 from a RAM copy of the script, with HDMI audio after the warm
reboot (commit `3f85b93`). Plan and safety rules:
[hdmi-shared-startup-plan-2026-10-23.md](hdmi-shared-startup-plan-2026-10-23.md)
("First direct warm test", "After the first pass"). Tools:
`tools/hdmi/build-startup.py`, `tools/hdmi/build-warm-shared.py`,
`tools/hdmi/check-warm-shared.py`, `tools/serial/run-warm-shared.py`.
Note: that plan file has uncommitted edits from another session; read it,
don't overwrite them.

**Steps:**
**October 27 production preparation:** step 3 is complete **offline only**:
shared branch, GP6 four-state crash-loop guard, health-ack unit, guarded delta
update and verified rollback. 70 tests pass, all 17 new mutations caught,
combined systemd verification and bundle hashes pass. [Evidence and exact
proposed install/test sequence](hdmi-evidence/2026-10-27-shared-startup-production-preparation/README.md).
No board actions or production installation. Next is explicit GP6-policy and
install approval, followed by operator ready/OPEN. Proposed installed-path
soak: five orderly warm boots, one synced SysRq-b and no-source cold boot with
runtime reconnection. Initial post-install boot and rollback both require a
physical cold cycle. No real forced-GP6 negative tests.

**Latest, October 27 clean repeat:** synced GP7/SysRq-b repeat **PASS** with
complete drained UART acknowledgement and automatic census/transfer/one RAM
launch. Cold and warm picture/colour/tone confirmed, warm ~59.8 fps, zero new
rejects/xruns and no speaker restart/mixer changes. [Clean evidence](hdmi-evidence/2026-10-27-warm-shared-gp7-sysrq-clean/README.md).
Checked poweroff done; board powered down. Orderly and abrupt RAM-only repeats
now pass. Next work is step 3 offline (GP6 crash-loop policy/shared branch and
health ack), then explicit production policy/install approval and soak.

**Progress, October 24:** orderly RAM-only warm repeat **PASS with video and
audible audio**, using the existing GP7 boot stop (user-authorized), no timed
interrupt. [Evidence](hdmi-evidence/2026-10-24-warm-shared-gp7-orderly/README.md).
Warm video service started at 21.255 s, ~59.8 fps, zero new rejected frames,
zero audio xruns. Operator confirmed console -> host desktop -> video/tone;
no black reported. Checked final poweroff completed. SysRq-b remains: its
GP7 arming must be reviewed separately because it skips reboot notifiers.

**October 27 preparation:** the synced SysRq-b/GP7 path is ready offline,
not run: [exact test sequence](hdmi-evidence/2026-10-27-warm-shared-gp7-sysrq-preparation/README.md).
RTC nvmem arming pins provider/cell identity, requires GP7=0/expected GP6,
writes exactly four bytes to GP7, verifies readback and unchanged GP6, then
resets without teardown. 45 tests pass; 12 new mutations caught. Awaiting
operator ready for the disconnected cold cycle; board remains off.

**October 27 live update:** after approved audio diagnosis/restoration and
explicit resume, cold health passed and one GP7-armed SysRq-b reached U-Boot.
Acknowledgement was truncated by reset, so guard prevented RAM launch; **board
now held at U-Boot**, no recovery PASS. [Evidence](hdmi-evidence/2026-10-27-warm-shared-gp7-sysrq/README.md).
UART-drain fix prepared offline (46 tests, regression mutation caught), not
run on board. Further continuation/retry needs approval. Initial cold audio
silence remains unexplained despite restored audibility after speaker restart.

**Final October 27 result:** user approved held-prompt verification/continuation
without another reset. One RAM startup recovered warm video/colour/tone;
digital checks pass (~59.76 fps, zero rejects/xruns). Checked poweroff done,
board powered down. This is functional abrupt-recovery evidence with a
six-minute U-Boot hold, incomplete reset ACK and prior cold speaker restart;
repeat with UART drain for unattended evidence and diagnose cold audio before
calling release acceptance complete. No production installation.

1. Repeat the RAM-only warm test twice more: once after an orderly reboot,
   once after a SysRq-b reset. Same runner and checker.
2. Now also check the **video**: with the video stack installed, the warm
   boot should show HDMI on the panel at about 21 s. Record `dmesg | grep
   h713-hdmi-v4l2` and `systemctl status h713-hdmi-video`.
3. Production change (offline first, with unit tests): make the installed
   script's warm branch run the shared sequence, gated on GP6 as the plan
   describes, plus the health-ack unit. Cover all four GP6 states and loop
   prevention: a forced `HDMI` state must boot logo-only.
4. Install only with explicit approval; then N unattended warm reboots with
   digital checks each boot, with the operator confirming the picture.

**Watch for panel-black:** after a warm reboot with an HDMI source
connected, the panel has sometimes stayed black (see the plan's
"panel-black workstream"). Recovery: unplug HDMI at the projector, then
reboot. Record every occurrence.

**Done when:** a warm reboot from HDMI comes back to HDMI video with
audible audio, on repeated reboots including an abrupt reset.

### 2. Two decisions for the user (ask, then implement)

* **Q7: HDMI vs local video playback.** If HDMI is locked while the user
  plays a local file (Cedrus decoder → video plane), who wins? Cedrus
  traffic plus live MIPS once hard-locked the board, so they must not run
  together. Options: HDMI wins and local playback is refused during an HDMI
  session (proposal), or local playback wins and stops the HDMI unit.
  Implementation hint: `Conflicts=` between units, or an `ExecStartPre=`
  refusal in `h713-hdmi-video.service`.
* **Q9: 640×480 sources.** Today they are marked unsupported and the
  console stays. Options: keep that; show 640×480 1:1 (module parameter
  `allow_480p=1` in `h713-hdmi-ring.service`; the pipeline already follows
  the size); or remove 640×480 from the EDID (needs the signal owner
  re-pinned; bigger change).
  Design doc §8 has the full question list.

### 3. Audio through PipeWire, and A/V sync

PipeWire loopback replacement is installed and lifecycle-qualified as of
October 27. The remaining part of design §5 (chosen option b) is measuring
latency and setting its configurable audio delay. Measure:
* video latency, with the GStreamer latency tracer;
* glass-to-glass latency, with a 240 fps phone filming the host monitor
  and the projection together;
* A/V offset, with the flash+beep clip `tools/video/make-avsync-clip.sh`.

Keep the speaker's mixer setup (DAC 43, Line Out 15; see
`tools/hdmi/enable-speaker-mixer.sh`). To mute, set the DAC volume to 0;
**never** set "Speaker Switch" to 0. Video is never buffered to match
audio; only audio may be delayed.

### 4. Lower priority

* **1080p50 sources** lose about a third of their frames in capture (design
  §10.23.6). Only reachable with the wide test EDID; the production EDID
  offers 720p and 640×480 only.
* **Interlaced input:** untested; the PC desktop can't produce 1080i.
* **Push** the commits to the user's fork when asked.

## Useful commands

```
# rebuild the bridge against the production kernel tree (W=1 must be clean)
K=$(ls -d build/linux-6.18.38-edffad3c*/); cp modules/hdmi-v4l2/*.{c,h} build/route-b/module/
make -C "$K" M=$PWD/build/route-b/module ARCH=arm64 LLVM=1 W=1 modules
python3 tools/hdmi/build-hdmi-video.py build/route-b/bundle

# offline tests
cc -O2 -Wall -Wextra -Wno-missing-field-initializers -o /tmp/tss tools/hdmi/test-signal-state.c && /tmp/tss
python3 tools/hdmi/test-signal-traces.py /tmp/tss
sh tools/hdmi/test-install-hdmi-video.sh build/route-b/bundle

# on the board
cat /sys/devices/platform/h713-hdmi-ring/signal         # none / locked 1280x720 / holding …
systemctl status h713-hdmi-ring h713-hdmi-video
dmesg | grep h713-hdmi-v4l2
sh /usr/lib/h713-hdmi-video/install-hdmi-video.sh --update   # replace (backup kept)
sh /usr/lib/h713-hdmi-video/install-hdmi-video.sh --remove   # revert to console-only
```

If the panel stays on the console with a source connected: check that the
PC still lists HDMI-A-1 (it sometimes drops the output while the board is
off; reseat the cable at the PC), then `cat` the `signal` attribute.

## October 27 production installation update

**Installation now complete, first new cold boot pending:** approved delta
installed once and verified; health unit enabled but inactive, GP6 HDMI/GP7
zero. Exact backup `/var/lib/h713-hdmi-startup/shared-20260413T194157-c5fec89a`
is copied/checksummed on host; rollback dry-run passed. FIT and saved environment
unchanged (active CRC-valid environment is documented LBA 0x32ec00, not configured
0x49ec00). Final current-boot health passed and checked poweroff confirmed on
UART at 2026-10-27 10:34:27 UTC. Reader closed. Await disconnected >=1 minute
cold cycle/ready, then fresh OPEN before power. New startup/automatic HDOK and
warm soak remain untested. [Evidence](hdmi-evidence/2026-10-27-shared-startup-production-install/README.md).

## October 27 first installed warm-boot update

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

**Operator subsequently confirmed warm functional PASS:** moving video, correct colours and audible tone after host-only player restart. Host SIGSEGV in mpv Wayland dispatch during fullscreen recovery is now confirmed by crash metadata; fallback audio routing is also recorded. No further board commands/reset; soak remains paused for host-fixture preparation. [Evidence](hdmi-evidence/2026-10-27-shared-startup-production-install/README.md).

## Quiet runtime result, October 27

**Quiet runtime interval ended, ~11:27 PDT October 27:** same warm boot now
~7 h 46 min uptime, ~7 h 37 min after silent baseline. Final read-only checks:
~59.6 fps, zero cumulative rejected frames/capture xruns, five units healthy
with NRestarts=0; host still playing on projector at software volume zero.
15-minute scheduled checks were not established, so this is baseline/final
long-run evidence, not fully monitored soak or repeated-reset acceptance.
No further waiting. Board left on and silent; no new reset/service mutation.
[Result and limitations](hdmi-evidence/2026-10-27-shared-startup-production-install/README.md).

## Final checked poweroff, October 27

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

## October 27 reboot acceptance continuation: cold audio failure

New evidence: [reboot acceptance](hdmi-evidence/2026-10-27-reboot-acceptance/README.md).
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
[Evidence](hdmi-evidence/2026-10-27-reboot-acceptance/README.md).

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
[Evidence](hdmi-evidence/2026-10-27-reboot-acceptance/README.md).

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
[Evidence and machine-readable verdict](hdmi-evidence/2026-10-27-reboot-acceptance/ACCEPTANCE-RESULT.json).

## October 27 PipeWire speaker fix installed; requalification pending

The direct consumer was replaced by the planned PipeWire loopback after
read-only volume inspection excluded a stuck fade/mute and a PCM re-prime
restored audibility. Exact old GStreamer/ALSA mechanism remains unisolated.
11 lifecycle tests / 17 mutations plus 46 existing warm tests pass. New route
passed stop/start capture closure, 600-ms client-pause recovery, actual capture
and codec-monitor 440-Hz content, updated graph/PCM ownership checks and
operator picture/tone. No backend/firmware/kernel/startup change. Backup
/var/lib/h713-hdmi-speaker/backup.AaUgab saved on host. Physical cold and full
reboot/no-source requalification remain pending; no PASS claimed yet.
[Evidence](hdmi-evidence/2026-10-27-audio-lifecycle-fix/README.md).
