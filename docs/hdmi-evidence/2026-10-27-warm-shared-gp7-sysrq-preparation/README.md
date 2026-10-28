# GP7 + SysRq-b warm trial: offline preparation, October 27

**PREPARED, NOT RUN. No board access or actions.** User authorized offline
preparation/tests using GP7 for the existing boot-stop purpose and reported
board off. No SSH, tty access, GP7 write, reset, install, commit or push.

## What changes from the passing October 24 orderly trial

SysRq-b bypasses reboot notifiers, so the kernel bootloader reboot argument
cannot set GP7 for it. New `--reset sysrq-b --boot-stop gp7` uses the RTC
nvmem provider to arm the same one-shot boot-stop word before writing `b` to
/proc/sysrq-trigger. No service stop, driver teardown or ordinary reboot runs.
Storage is synced first: this is a **synced abrupt reset**, not a power-loss
or unsynced-filesystem test.

The installed U-Boot preboot, production kernel/FIT/services and RAM warm
startup image stay unchanged. GP6 is only read by the arming code. Existing
U-Boot consumes GP7, sets volatile bootdelay=-1 and stops before logo/MIPS
initialization, with no timed key or manual operator interrupt.

## Source review and arm guards

Reviewed production kernel tree build/linux-6.18.38-edffad3c…:
* drivers/rtc/rtc-sun6i.c: 32-byte GP nvmem bank, word_size=stride=4;
  reg_read/reg_write operate on aligned 32-bit words at RTC base + 0x100 + offset.
* drivers/rtc/nvmem.c and drivers/nvmem/core.c: provider uses the RTC platform
  device and its DT of_node, so provider identity can be pinned by DT link.
* arch/arm64/boot/dts/allwinner/sun50i-h713.dtsi: RTC compatible
  allwinner,sun50i-h713-rtc, range 0x07090000/0x400, reboot cell offset 0x1c,
  size 4, nvmem-reboot-mode phandle and bootloader magic b007c0de.

Generated detached target trigger (example saved alongside):
1. Require expected cold boot ID, all five HDMI units active, both audio PCMs
   RUNNING, DSP healthy and signal locked 1280x720.
2. os.sync(), then repeat that guard. No service manipulation.
3. Validate RTC DT compatible/range, GP7 cell offset/size, reboot-mode
   compatible/magic and matching four-byte phandle reference. Find exactly
   one nvmem provider whose of_node resolves to this RTC. Its parent must be
   bound to sun6i-rtc. Open only that provider's nvmem; require size 32.
4. Read GP6+GP7 at offset 0x18, length 8. Require little-endian GP6=48444d49
   and GP7=0. Repeat boot/health guard immediately before arming.
5. Exactly one os.pwrite(fd, bytes.fromhex('dec007b0'), 0x1c), count **4**.
   Read back the same 8 bytes: GP6 must be unchanged, GP7=b007c0de. Close fd.
   Repeat boot/health guard after arming. No /dev/mem or devmem access.
6. UART acknowledgement `H713_WARM_SHARED_SYNC_DONE gp7=b007c0de gp6=48444d49`
   with expected boot ID, then exactly one write of `b` to /proc/sysrq-trigger.
   Returning unexpectedly is failure. No automatic retry or GP7 rollback.

On failure after arming, GP7 may remain set. Leave the board untouched,
report intent/readback evidence and obtain separate recovery approval.
Do not clear GP7, reset again or rerun the trigger to make a guard pass.

Runner persists reset intent before the detached SSH submission, saves exact
trigger text, requires the special UART acknowledgement plus sysrq: Resetting,
exactly one SPL and complete early census. Early GP7 must be b007c0de; prompt
GP7 must be consumed to zero. GP6/MIPS/PPU, preboot/bootcmd, bootdelay=-1,
FIT and script CRC, and one-source guards are retained. Missing serial
markers stop rather than bypassing checks, even if U-Boot is visibly waiting.
The earlier capture-loss cause remains unresolved; GP7 removes only the
keypress timing dependency.

## Offline validation

* `python3 tools/hdmi/test-warm-shared.py`: **45 PASS** (39 earlier + 6 new).
  Full output tests.log; existing temporary-directory warnings remain benign.
* Whole generated trigger executes on a temporary fake sysfs/proc tree.
  os.sync and reset/UART writes are mocked; the only actual nvmem I/O is to
  a temporary ordinary fixture file. Negative tests never access hardware.
* 12/12 in-memory code mutations caught (mutations.json), covering all six
  new tests: wrong GP offset, short-count acceptance, missing readback,
  ambiguous provider, wrong RTC/cell ranges, missing latch check, missing
  UART acknowledgement, wrong runner mode, missing sync/post-arm guard and
  re-enabled timed interrupt. Historical mutation logs are not rewritten.
* Fresh build/hdmi-warm-shared-gp7-sysrq-2026-10-27/manifest.json pins current
  builder/checker/runner/FIT. RAM script matches the tested October 23 image
  byte for byte (SHA256 4c1ee8c0be5624c20195edfb79b4a043946957aa17e85142a98119dfbb568947).
* Wrapper is prepared at build/hdmi-warm-shared-sysrq-source-2026-10-27/run-sysrq-gp7-gated.py,
  copied here as text. extra-sha256.json pins wrapper/tests/mutation script.
  Wrapper is unstarted; live output directory does not exist.

## Proposed exact operator trial

1. Board remains off. Operator disconnects mains, serial and USB **at the
   board** for >=1 minute; host serial adapter stays on host. Keep HDMI
   connected. Say ready with board still unpowered.
2. Assistant confirms prepared hashes and free tty, starts sole UART reader
   detached, verifies OPEN. Only then operator connects board serial first,
   then mains; USB remains disconnected.

   ```sh
   setsid nohup python3 build/hdmi-warm-shared-sysrq-source-2026-10-27/run-sysrq-gp7-gated.py \
     > build/hdmi-warm-shared-sysrq-source-2026-10-27/runner.log 2>&1 < /dev/null &
   ```

   Options reset=sysrq-b, boot_stop=gp7, require_video=True; fresh output
   docs/hdmi-evidence/2026-10-27-warm-shared-gp7-sysrq.
3. Watch installed cold startup uninterrupted; require zero cold census,
   timing re-latch, handoff and Linux login/SSH. Start prepared moving 720p60
   pattern + 440 Hz stereo tone explicitly on HDMI-A-1/projector audio.
   Verify actual host screen/routing; operator confirms picture/colour/tone.
4. Save report and release cold-host-source-confirmed gate (host file only).
   Existing checker stages only scratch Python/shell under /run. Require
   passing cold startup/DSP/audio/video flow. Failure sends no reset request.
5. Submit detached guarded trigger once: sync -> arm/read back GP7 through
   RTC nvmem -> post-arm guard -> UART acknowledgement -> SysRq-b, with HDMI
   drivers still live. Stop host test player across reset to prevent fallback
   audio to host speakers. No host logout or reboot.
6. U-Boot stops automatically. Require complete reset/census evidence,
   consumed GP7=0, GP6 unchanged, MIPS parked, PPU bus closed, unchanged
   preboot/bootcmd and volatile bootdelay=-1. No interrupt key is sent.
7. Verify production FIT after FAT-load to RAM 0x50000000. Transfer unchanged
   warm-shared.scr by YMODEM to 0x52000000 with CRC verification. Source it
   exactly once: logo -> MIPS -> source 3 -> 720p timing re-latch -> handoff.
8. Require warm kernel/login/new boot ID. Restart host clip explicitly on
   projector HDMI and verify sink routing. Release warm-host-source-confirmed
   gate; collect and compare warm startup/DSP/audio/video checks, journals,
   bridge dmesg and service start timing. Operator reports moving picture,
   colour/tone or logo/console/black. Digital PASS alone is provisional.
9. After the operator report, stop test player and perform the checked final
   production poweroff included in the approved trial. Require UART
   reboot: Power down. Record all observations and update design/handoff.

A ready authorizes only this described trial. Any failed/uncertain arm,
reset, census, transfer, startup or missing UART stops without automatic
retry. Panel-black recovery needs separate approval. No production startup
installation, GP6 policy change, health-ack deployment or soak in this trial.
Host source restart means uninterrupted-source recovery time is not measured.

**Next operator action:** disconnect board power/serial/USB for >=1 minute,
then say ready while it remains unpowered. Do not power it until OPEN.
