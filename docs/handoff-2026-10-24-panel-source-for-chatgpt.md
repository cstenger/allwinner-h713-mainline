# Handoff: HDMI-in on the panel (route B + event-driven switching), 2026-10-24

## Current A/V calibration — 40 ms saved and reboot verified

**PASS with qualifications.** `/etc/default/h713-hdmi-speaker` saves
`H713_HDMI_AUDIO_DELAY_SEC=0.040`; no temporary override remains. At this
setting, `test2.mov` gives 15/15 recorded flash/beep matches, median −2.44 ms,
p05/p95 −15.07/+3.03 ms, threshold-sweep median −9.13..−0.35 ms.
Camera/export bias remains unmeasured; one-foot sound flight is ~0.9 ms.
This is calibration to the recording, not certified absolute zero, absolute
glass-to-glass latency or long-run drift.

One orderly reboot reached `c8f3308e-5c02-4be1-bc0e-3ee5991761e8`; the saved
target and actual `--delay=0.04` returned. Video, speaker and health
acknowledgment were active, with no recovery restarts or board service
intervention. Flow was 59.64 fps with zero rejected-frame increment/capture
xruns. Warm timing matched 38/38 events; electronic median −32.35 ms must
not be treated as perceptual sync. Operator confirmed normal flashes/beeps.
Host-only audio/video output reopening was required after hotplug and is
logged. A PC-end HDMI reseat was required on the initial cold boot.

Cleanup: test player and passive UART stopped; host HDMI restored to original
raw 22937/35%, unmuted. Board left powered on with saved 40 ms active.
[Results, exact installed defaults, reproduction and qualifications](hdmi-evidence/2026-10-27-avsync-calibration/README.md),
with machine verdict `CALIBRATION-RESULT.json`. Original camera MOVs remain
local; their hashes, derived signals and analysis are included.
The earlier lifecycle/reboot commit `a93a741` was pushed; this calibration
commit has not been pushed. Historical board-off statements below describe
the end of the earlier reboot acceptance, before this calibration session.


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

For whoever picks this up (ChatGPT or a later Claude session). Keep this file
updated as work lands. The full record is
[hdmi-panel-source-design-2026-10-23.md](hdmi-panel-source-design-2026-10-23.md)
§10.25–§10.26; this file is the short version.

## Latest: production shared startup prepared offline (October 27)

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

**Quiet runtime interval ended, ~11:27 PDT October 27:** same warm boot now
~7 h 46 min uptime, ~7 h 37 min after silent baseline. Final read-only checks:
~59.6 fps, zero cumulative rejected frames/capture xruns, five units healthy
with NRestarts=0; host still playing on projector at software volume zero.
15-minute scheduled checks were not established, so this is baseline/final
long-run evidence, not fully monitored soak or repeated-reset acceptance.
No further waiting. Board left on and silent; no new reset/service mutation.
[Result and limitations](hdmi-evidence/2026-10-27-shared-startup-production-install/README.md).

**Operator warm confirmation received:** moving video, correct colour and audible tone. First installed orderly warm boot is a functional digital/on-glass PASS after host-only player restart. Soak remains paused for host hotplug investigation; board stays on, no further board commands/reset. [Evidence](hdmi-evidence/2026-10-27-shared-startup-production-install/README.md).

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

**First installed cold boot now digitally PASS (operator confirmation pending):**
boot `a0cdeb59-4933-41e6-bafd-b31dad5a96ca`, shared handoff/re-latch verified and automatic
GP6 HDMI→HDOK at 20.877 s, GP7 zero. Health unit active/exited/status 0/no
restarts; dry-run observes HDOK without writing. DSP 0/0→1/1, audio ~48 kHz
zero xruns, video ~59.44 fps/zero rejects. No manual ack or board service
restart. Host player was relaunched after this physical cold cycle; no
uninterrupted-source timing claim. UART/player running; await operator cold
picture/colour/tone before any installed warm reboot. [Live evidence](hdmi-evidence/2026-10-27-shared-startup-production-install/README.md).

**Installation now complete, first new cold boot pending:** approved delta
installed once and verified; health unit enabled but inactive, GP6 HDMI/GP7
zero. Exact backup `/var/lib/h713-hdmi-startup/shared-20260413T194157-c5fec89a`
is copied/checksummed on host; rollback dry-run passed. FIT and saved environment
unchanged (active CRC-valid environment is documented LBA 0x32ec00, not configured
0x49ec00). Final current-boot health passed and checked poweroff confirmed on
UART at 2026-10-27 10:34:27 UTC. Reader closed. Await disconnected >=1 minute
cold cycle/ready, then fresh OPEN before power. New startup/automatic HDOK and
warm soak remain untested. [Evidence](hdmi-evidence/2026-10-27-shared-startup-production-install/README.md).

**Installation trial now authorized/in progress:** user approved production
install and GP6 policy and completed the ≥1 minute disconnected cold cycle.
UART OPEN preceded power; old cold digital baseline passes, GP6 HDMI/GP7 zero,
18 backend checksums match. Host video/tone routed to projector; awaiting
operator cold picture/colour/tone before installation. No install/reset/latch
write yet. [Live evidence](hdmi-evidence/2026-10-27-shared-startup-production-install/README.md).

**Not installed.** User authorized offline production changes/tests only;
no board actions taken. Last known board state is checked poweroff after the
clean RAM-only SysRq-b pass. [Candidate, evidence and exact proposed sequence](hdmi-evidence/2026-10-27-shared-startup-production-preparation/README.md).

Shared U-Boot branch now accepts GP6 zero/HDOK, validates cold-equivalent
MIPS/clock/reset/GP7/PPU census, and latches HDMI before firmware; HDMI/unknown
retain logo-only fallback. Existing source-3, TCON re-latch and handoff stay
unchanged. New capture+signal-ordered health unit checks current boot/session
and startup health before one validated RTC nvmem GP6→HDOK write, verifying
GP7 stays zero. No signal-lock/video/speaker requirement; shutdown unchanged.
Guarded delta installer backs up the old generation, enables without starting
health, and activates FAT script last. Verified rollback uses its recorded
transaction. Both builder entry points emit this delta; old fresh-install
bundle behavior is retired for the shared script.

70 tests pass (11 startup + 46 runner + 13 new production); all 17 new mutations
caught; systemd unit verification and bundle checksums pass. Bundle is
`build/hdmi-shared-startup-production-2026-10-27/`; candidate script SHA256
`fcea3a9589432f9b44781178d70433486aac5872a618970039b3326744e7fe7b`.
Next: explicit production-install **and GP6-policy approval**, then a separate
ready/OPEN cold-cycle gate. Proposed installed-path acceptance: initial cold
boot, five orderly warm reboots, one synced abrupt reset, then no-source cold
boot/runtime reconnection. No GP7 stop/RAM source in production soak. Forced
bad-latch tests stay offline. Physical cold cycle is required immediately
after installation and after rollback; neither updater writes RTC. Earlier
cold-audio silence and panel-black observations remain open. No commit/push.

## Goal (user requirement)

The panel shows the U-Boot logo, then the Linux console. When an HDMI source is
connected and actually sending video, HDMI becomes the panel's picture. When the
signal goes, the panel returns to the console. Switching is event-driven
(no polling loop in userspace, no boot-time choice), and the same path covers
cold boot, warm boot and runtime plugging.

## Hard rules (do not break)

* Never read `0x07091000`–`0x07091fff` from ARM: a read wedges the SoC.
  Never touch `0x06940000`. GP7 is reserved for the existing reboot-mode
  handoff; the user clarified on October 24 that its one-shot bootloader-stop
  use is authorized. Do not repurpose it. GP6 is the startup latch.
* PB5 is the lamp and the fan: never hold it low for long.
* After any MIPS source change, re-latch the 720p TCON timing (`0x05880020/24`).
  (Route B makes no MIPS calls.)
* **The HDMI source PC is the machine running the assistant.** Logging out or
  rebooting it kills the assistant and its ssh to the board. Run long board
  commands detached (`setsid nohup … > /root/log 2>&1 &`) and never ask for a
  host logout while a board command depends on the session.
* Operator-timed tests: announce, end the turn, wait for "ready". A cold boot
  means serial + USB unplugged and power off ≥ 1 min.
* Board root fs has ~170 MB free: never stream frames to a file there.
* The route B video stack is installed (see stage 5 below). New test staging
  goes under `/run` or U-Boot RAM; production changes need explicit user
  approval. Only push to `cstenger/*`.
  Route B + event-driven switching are committed as `3a797cc` on
  `h713-letterbox` (not pushed); the earlier panel-source phases (T4–T6,
  Test 1–3 tools and evidence, experimental patches 0188/0189, the
  tools/stock sweeps) are `8a6d771`.

## How HDMI reaches the panel (route B, proven on glass 10-24)

The MIPS firmware writes the HDMI input as NV16 into a 3-slot ring in DRAM
(Y slots at `0x4c3ef000 + n·0x1ff000`, C slots 3 slots later). The bridge
module `modules/hdmi-v4l2/h713-hdmi-v4l2.c` (V4L2 node `h713-hdmi-in`) copies
the finished slot, converts it to NV12 (copy Y, average chroma row pairs:
`h713-nv12.h`) and exports dmabufs. Stock GStreamer puts it on the KMS NV12
video plane:

```
gst-launch-1.0 -e -q v4l2src device=/dev/h713-hdmi-in io-mode=dmabuf ! video/x-raw,format=NV12 ! kmssink driver-name=sun50i-h713-afbd sync=false skip-vsync=true
```

* Frame completion: AFBD `0x05600320` names the slot **being captured**; the
  finished frame is `(idx + 2) % 3` and stays still until the pair moves.
  A copy is accepted if the pair is unchanged afterwards. (Production has no
  VIncap hook, so `completion=pair`.)
* Result: 59.5–59.7 fps, 0 rejected, ~3 ms CPU per frame; colours correct on
  glass (band chart, video `local/lcd-photos/test_109`).
* `kmssink` needs `driver-name=sun50i-h713-afbd`.
* If the board cold-boots while the PC has dropped its HDMI output, the ring
  stays frozen; reseat the cable at the PC.

## Event-driven switching (built 10-24)

* `modules/hdmi-v4l2/h713-signal.h`: the state machine, shared by the module
  and the host tests. Live = port 1 state 5 + non-zero size + ring moving
  (sampled every 20 ms; port object read through guarded pointers in MIPS DRAM
  `0x4B100000–0x4BF41000`). States: none → acquiring → locked (200 ms stable,
  1280×720) or unsupported (anything else; 640×480 needs `allow_480p=1`).
  locked → holding after 100 ms without the signal (bridge sends black frames)
  → locked again, or none after 1.5 s.
* The bridge publishes the state as the `signal` attribute of
  `/sys/devices/platform/h713-hdmi-ring/`, a `change` uevent per transition,
  `V4L2_EVENT_SOURCE_CHANGE` on a new locked size, and the DV-timings ioctls.
  `STREAMON` returns `-ENOLINK` unless locked.
* `tools/hdmi/71-h713-hdmi-in.rules`: device ready only while
  locked/holding. `h713-hdmi-ring.service` loads the bridge;
  `h713-hdmi-video.service` runs the pipeline above and `BindsTo=` the device.
* `tools/hdmi/stage-hdmi-video.sh` (on the board, from `/root/hdmi-video/`):
  `observe SECS` (bridge alone, no panel change), `ARMED=yes … stage`,
  `status`, `unstage`.
* Build: `python3 tools/hdmi/build-hdmi-video.py build/route-b/bundle`
  (module built separately against the production tree
  `build/linux-6.18.38-edffad3c…` with `make … ARCH=arm64 LLVM=1 W=1`).
* Offline tests: `tools/hdmi/test-signal-state.c` (18 scenarios; 18
  mutations all caught), `tools/hdmi/test-signal-traces.py` (replays
  recorded firmware captures), `tools/hdmi/test-nv12-convert.c`.

## Where it stands

| Stage | Result |
| --- | --- |
| Route B on glass | PASS (§10.25.6) |
| 1. Observe (bridge alone, host actions) | PASS (§10.26.1): correct transitions for every action; compliance 48/48; longest mode-set gap 0.56 s |
| 3. Staged rule + units | First run failed on a udev rule bug (§10.26.2: `ATTRS{}` keys must match on one device). **Rerun with the fixed rule: PASS** (§10.26.3): 7 starts / clean stops, `NRestarts` 0, every host action correct per the operator |
| 4. Coldplug | Seen working at the start of stage 3 (unit started 64 ms after load) |
| 5. Install | **INSTALLED on the board 2026-10-24** (approved). Cold boot with cable: logo → console → HDMI at 20.85 s, PASS. Warm reboot: console only, because the production U-Boot warm path doesn't set `/chosen/h713,hdmi-boot-v1`, so the whole HDMI backend is skipped (expected per §6; needs the shared warm-startup U-Boot work). Second cold boot: PC re-enabled its output on hotplug, HDMI at 21.25 s; 13-min soak 59.7 fps, 0 rejected, `NRestarts` 0, speaker active. **Stage 5 PASS on cold boots** |

**Board now:** the event-driven HDMI video is INSTALLED (`/usr/lib/h713-hdmi-video`,
units in `/etc/systemd/system`, rule in `/etc/udev/rules.d`). Revert with
`sh /usr/lib/h713-hdmi-video/install-hdmi-video.sh --remove`. After a warm
reboot HDMI stays off until a cold boot (U-Boot warm path).

## Next steps

**Latest, October 27, clean repeat:** **PASS on glass and digitally** for a
fresh GP7-armed SysRq-b with the UART-drain fix. Full acknowledgement, one
reset, automatic census/transfer and one RAM source, no manual continuation
or long hold. Cold and warm picture/colour/tone confirmed without speaker
restart or mixer changes. Warm ~59.8 fps, zero rejects/xruns, NRestarts=0,
video service start 21.279 s. [Clean evidence](hdmi-evidence/2026-10-27-warm-shared-gp7-sysrq-clean/README.md).
**Checked poweroff complete; board powered down.** Host volume restored to
35%, player stopped. Orderly and abrupt RAM-only repeats now pass; next is
offline production GP6 shared branch/health-ack, then explicit policy/install
approval and soak. Earlier isolated cold-audio silence remains tracked.

**Earlier October 27 continuation:** functional warm recovery after the single GP7-armed
SysRq-b **PASS digitally and on glass**, following explicitly approved
held-prompt continuation: one RAM source, ~59.76 fps, zero rejected frames/
audio xruns; operator confirmed picture, colour and tone. **Checked final
poweroff completed; board powered down.** Host projector volume restored to
prior 35%, player stopped. [Final evidence](hdmi-evidence/2026-10-27-warm-shared-gp7-sysrq/README.md).
Limitations: truncated reset ACK, six-minute U-Boot hold, initial cold audio
needed diagnostic speaker restart. Not an unattended-runner or clean cold-audio
PASS. Next: fresh abrupt trial to validate UART drain without long hold,
diagnose cold-audio silence, then production GP6/health-ack and install/soak.

**Preparation snapshot, October 27:** SysRq-b with the existing GP7 one-shot stop was
prepared offline, not run. [Runbook and validation](hdmi-evidence/2026-10-27-warm-shared-gp7-sysrq-preparation/README.md).
Trigger syncs, validates the RTC nvmem provider/cell and initial GP6/GP7,
writes only GP7, verifies readback and unchanged GP6, rechecks health, then
issues SysRq-b without teardown. GP7 stop/census/CRC/one-launch guards remain.
45 tests pass; 12 new mutations caught. Board reported off; no board access
during preparation. Next: operator disconnected cold cycle and ready, then
OPEN before serial-first/mains. No production change or install.

**Earlier October 27 pause before SysRq-b:** cold video/colour confirmed,
but operator heard no tone. Host HDMI sink was raised from 35% to 100% (still
inaudible). Read-only board mixer is 43/15 with switches on. Approved brief
speaker-stop/capture/restore diagnostic found clear stereo 440 Hz input,
RMS 0.204677, matching earlier successful recordings. Speaker restored active,
both PCMs RUNNING; downstream audibility cause unresolved. [Evidence](hdmi-evidence/2026-10-27-warm-shared-gp7-sysrq/README.md).
Cold source gate remains closed; no GP7 arm/reset. Await operator audibility
report after restoration. Prior host HDMI volume 35% recorded for restoration.
Operator subsequently confirmed the tone is audible after speaker restoration.
Initial silence cause is still unresolved. Latest instruction keeps SysRq-b
paused; do not release cold gate until user resumes. Recheck health before reset.

**Subsequent October 27 resume:** user authorized fresh checks and one abrupt
reset. Checks passed; one GP7/SysRq-b reached U-Boot with full early census
(GP7 magic, preserved GP6, MIPS zero). UART acknowledgement was cut at `gp7=b`
by sysrq: Resetting, so the full-marker guard prevented census/transfer/source.
Host runner/player stopped; **board remains held at U-Boot**, no second reset.
No warm recovery result. Added UART tcdrain before reset offline (46 tests;
drain-removal mutation caught). [Offline fix](hdmi-evidence/2026-10-27-warm-shared-sysrq-uart-drain/README.md).
No hardware run of this fix; further continuation/retry needs approval.
**User then approved continuation without reset:** live prompt/census and
FIT/CRC passed; first RAM source booted successfully. Warm digital checks
and comparison PASS (DSP 0/0 -> 1/1, ~59.76 fps, zero rejects/xruns, video
service 22.000 s). Board now running warm Linux; awaiting operator picture/
tone report. One SysRq-b total, one RAM source. Six-minute U-Boot hold and
earlier speaker restart are limitations; no unattended-reset timing claim.

The full task list for the remaining work, with steps and acceptance criteria:
[chatgpt-hdmi-remaining-work-2026-10-24.md](chatgpt-hdmi-remaining-work-2026-10-24.md).


1. ~~Rerun stage 3~~ done, PASS (§10.26.3).
2. Stage 5 installed; cold boots and soak passed. Warm recovery repeats are
   prepared **offline only**, not run: [exact runbook and validation](hdmi-evidence/2026-10-24-warm-shared-repeat-preparation/README.md).
   Runner now supports synced SysRq-b and required video health alongside
   the existing DSP/audio checks. 32 offline tests pass; 8/8 mutations caught.
   RAM startup image is unchanged from October 23. Next: operator-approved
   orderly trial, then separately approved SysRq-b trial. No board access
   during this preparation; no production startup change or install.
   **Orderly live attempt subsequently stopped:** cold picture/tone confirmed
   and digital health passed; one orderly restart reached warm SPL, then the
   host UART reader hit transient EAGAIN. No RAM script transfer or launch.
   [Evidence and offline fix](hdmi-evidence/2026-10-24-warm-shared-repeat-orderly/README.md).
   Reader fixed offline; 33 tests pass and reverting the fix fails its new
   regression test. Operator reported catching U-Boot; board left untouched.
   Retry needs a fresh approved cold cycle/new evidence and tool pins, plus
   host source routing checked again after HDMI hotplug (audio migrated to
   host speakers during reset; test player was stopped).
   **Retry 1 also inconclusive:** cold on-glass and digital checks passed,
   but incomplete warm UART capture omitted SPL/preboot markers, so the
   runner sent no interrupt and the installed warm fallback booted Linux.
   No RAM transfer/source. [Retry evidence](hdmi-evidence/2026-10-24-warm-shared-repeat-orderly-retry1/README.md).
   Host runner and test player stopped; read-only SSH confirms new boot,
   absent handoff and all five HDMI units inactive. Board left running.
   User was not expected to interrupt manually. Capture-loss cause remains
   unresolved; investigate before another operator cold-cycle trial.
   **Next orderly runner prepared offline:** user authorized the existing
   one-shot GP7 boot stop. `--boot-stop gp7 --reset orderly` uses the kernel
   bootloader reboot argument, no timed key or raw GP7 write. U-Boot consumes GP7
   and waits; runner verifies preboot/volatile bootdelay and consumed GP7=0
   before the existing FIT/launch guards. 39 tests pass; 11 GP7 and 8 earlier
   mutations caught. [Revised sequence and artifacts](hdmi-evidence/2026-10-24-warm-shared-gp7-preparation/README.md).
   No board actions during preparation. SysRq-b+GP7 is refused: that reset
   skips reboot notifiers and needs a separately reviewed arming sequence.
   **GP7 orderly trial subsequently PASS on glass and digitally:** complete
   UART, one automatic GP7 stop and one RAM source. Operator saw console ->
   host desktop -> video and heard tone; warm ~59.8 fps, zero new rejects or
   audio xruns, video service start 21.255 s. No black reported. [Final evidence](hdmi-evidence/2026-10-24-warm-shared-gp7-orderly/README.md).
   Host player was restarted explicitly after HDMI hotplug, so this proves
   functional recovery, not uninterrupted-source timing. Checked final
   poweroff completed; board powered down. Next: separately prepare SysRq-b
   GP7 arming and operator trial, then production GP6/health-ack and soak.
3. Open user decisions: Q7 (HDMI vs local Cedrus playback priority), Q9
   (640×480: console, show 1:1, or drop from the EDID).
4. Later: 1080p50 sources drop about a third of frames in capture;
   interlaced input untested; the PipeWire audio loopback and A/V sync (§5).

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
