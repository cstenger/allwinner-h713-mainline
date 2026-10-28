# One-shot GP7 stop: offline orderly-runner preparation, October 24

**OFFLINE ONLY. No board SSH, serial access, staging, shutdown, reboot or
register writes during this preparation. No commit or push.** User explicitly
authorized using the existing GP7 boot-stop mechanism, then authorized these
offline changes/tests and required stopping before board actions.

## Mechanism and scope

Existing kernel patch 0029 exposes RTC GP7 as a reboot-mode nvmem cell:
`mode-bootloader = 0xb007c0de`, GP7 physical 0x0709011c. The existing U-Boot
saved preboot consumes/clears this magic and sets **volatile** bootdelay=-1.
No saveenv or GP6 change. See docs/hdmi-normal-startup.md, docs/status.md
July 23 validation, and October 17 uboot-output-diagnostic evidence. Local
installed-environment snapshot still contains this handler. Current live
installation has NOT been rechecked during this offline work.

`--boot-stop gp7 --reset orderly` selects the new mode. The detached trigger
checks the cold boot ID, DT compatible/magic, bound nvmem-reboot-mode driver,
and systemctl support for --reboot-argument. It submits exactly once:

```
systemctl reboot --no-block --reboot-argument=bootloader
```

The kernel driver writes GP7 on the normal restart notifier path. The runner
contains no raw GP7 write. Trigger uses setsid nohup and redirects all streams
to /run/h713-warm-shared-bootstop.log (stdin /dev/null). Normal service teardown
and hold guard remain active. Intent is saved before submission. Any unknown
outcome stops; no resubmission, raw-MMIO fallback or timed-key fallback.

Warm stream verification still requires exactly one observed SPL, proper
preboot census, reset marker and prompt. It sends **no interrupt key**.
Early board trace is before preboot: expect GP6=48444d49, GP7=b007c0de, MIPS
clock/reset/status all zero. At prompt verify installed bootcmd and exact
preboot handler, bootdelay=-1; GP7 must now be zero (consumed), GP6 preserved,
MIPS status zero and PPU bus closed. All checks precede FIT/RAM loading.
Premature logo/script/kernel or extra reset is rejected.

This eliminates the keypress deadline, **not serial integrity requirements**.
If UART markers are lost again, the test stops and reports it; a successfully
consumed boot-stop word should leave U-Boot waiting for diagnosis. It does
not convert an incomplete capture into a passing run or auto-reconnect.

GP7+SysRq-b is explicitly rejected before opening UART: SysRq-b bypasses
reboot notifiers, so --reboot-argument cannot arm GP7 on that path. The existing
interrupt mode remains available for historical tests; the abrupt repeat
needs its own reviewed GP7 arming sequence later, not an orderly substitute.

## Offline verification and artifacts

* 39 tests PASS (33 earlier + 6 new); tests.log includes full output.
* 11/11 GP7 mutations caught, covering every new test (mutations.json).
  Checks cover no interrupt, early/consumed GP7, missing markers, extra reset,
  premature boot, preboot/bootdelay, boot ID, bound driver, reboot argument,
  detached one-shot submission, and resume/mode refusals.
* Earlier 8/8 mutations still caught (earlier-mutations.json); its copied
  runner was updated only for the new intent-log anchor, preserving the
  historical mutation script unmodified.
* All simulated board commands are mocked. Mutations execute source changed
  in memory only. UART regression retains transient-EAGAIN and fatal-EIO tests.
* build/hdmi-warm-shared-gp7-2026-10-24/manifest.json pins current tools/FIT.
  warm-shared.scr remains byte-identical to the October 23 tested image
  (SHA256 4c1ee8c0be5624c20195edfb79b4a043946957aa17e85142a98119dfbb568947).
* run-orderly-gated.py.txt saves the proposed host wrapper, also at
  build/hdmi-warm-shared-source-2026-10-24/run-orderly-gp7-gated.py.
  It pauses cold health for operator source confirmation; warm health waits
  for host source routing verification. Neither gate skips digital checks.
  No wrapper was started; no evidence directory for the live GP7 trial exists.

## Revised proposed live sequence

1. If the board is still running from the prior attempt, obtain explicit
   approval for checked production poweroff first. Do not pull its power
   before that shutdown. Then operator disconnects board power/serial/USB for
   at least one minute. Keep HDMI connected; host adapter stays on host.
2. Operator says ready with board still unpowered. Assistant checks the host
   tty is free, starts the sole-reader wrapper below detached, and confirms
   OPEN. Only then connect serial to board first, then mains; USB stays out.

   ```sh
   setsid nohup python3 build/hdmi-warm-shared-source-2026-10-24/run-orderly-gp7-gated.py \
     > build/hdmi-warm-shared-source-2026-10-24/gp7-runner.log 2>&1 < /dev/null &
   ```

   Underlying runner: reset=orderly, require_video=True, boot_stop=gp7;
   prepared build/hdmi-warm-shared-gp7-2026-10-24;
   fresh output docs/hdmi-evidence/2026-10-24-warm-shared-gp7-orderly.
3. Watch installed cold boot untouched, verify all-zero census, re-latch,
   handoff and Linux login/new SSH boot. Start the prepared looping moving
   720p60/440 Hz stereo test clip on HDMI-A-1, explicitly selecting projector
   audio. Verify actual fullscreen display, advancing playback and sink route.
4. Operator confirms moving picture, correct colour and tone. Save report;
   create cold-host-source-confirmed **on host**. Checker writes only its
   temporary Python/shell scripts under /run and samples installed paths.
   Startup/DSP/audio/video must all pass; otherwise no reboot.
5. Save reset intent and detach the guarded bootloader-reboot trigger once.
   Normal orderly teardown; kernel writes existing GP7 bootloader magic.
   Stop host player during reset to avoid audio migration to host speakers.
6. U-Boot consumes GP7 and waits at => without a key. No operator interruption
   is needed. Runner verifies complete reset/UART evidence, expected early
   GP7 magic, unchanged bootcmd/preboot, volatile bootdelay=-1, consumed GP7=0,
   preserved GP6, parked MIPS, closed PPU bus. Failure stops here; no launch.
7. FAT-load production FIT to RAM 0x50000000 and verify size/CRC. YMODEM-load
   unchanged warm-shared.scr to RAM 0x52000000 and verify CRC. Execute exactly
   one source 0x52000000. Existing logo -> MIPS -> source 3 -> 720p re-latch ->
   handoff -> Linux sequence is unchanged. No saved environment/media writes.
8. Require warm markers/new boot ID. After projector display/audio hotplug,
   restart test clip explicitly on the projector and verify actual routing.
   Create warm-host-source-confirmed on host; run warm startup/DSP/audio/video
   checks and compare with cold. Record journals/dmesg and service start times.
   Any deliberate host source outage is recorded; don't claim uninterrupted
   tone or directly compare wall-clock video arrival with the 21 s baseline.
9. Leave running for operator warm picture/colour/tone report; digital pass
   alone is provisional. Record black/console/logo as observed. Then perform
   the approved checked poweroff once, confirming reboot: Power down on UART.

Any failed guard, incomplete UART, extra reset, uncertain request or CRC failure
stops, with no retry. Panel-black recovery (projector-end HDMI unplug/reboot)
requires separate approval. GP6 production guard/health-ack implementation,
installation, SysRq-b arming and soak remain later work. No board action is
authorized merely by this offline preparation; present the sequence and wait.
