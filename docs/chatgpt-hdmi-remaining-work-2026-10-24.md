# HDMI-in: remaining work, for ChatGPT (2026-10-24)

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
  Never touch `0x06940000`. Never write RTC GP7. GP6 is the startup latch.
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

Design §5 (chosen option b). Replace `h713-hdmi-speaker` with a PipeWire
loopback from the HDMI capture node to the codec sink, set its delay to
match the video latency, then measure:
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
