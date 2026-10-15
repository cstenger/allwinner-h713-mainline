# Normal-startup integration candidate, 2026-10-14

## Latest: corrected script cold run, automatic Linux startup and capture PASS

The first cold autoboot stopped at U-Boot on the bare-PID handoff
(`cold-autoboot-1-fdt-pid-failure.txt`). After the fix, the operator
cold-cycled again (serial and USB unplugged). Plugging the adapter back in
interrupted autoboot before the script ran; `resume-1/` shows the read-only
guard refusing to resume (no `hdmi_*` variables) and the state that was then
read: MIPS status 0, GP6 0. That is a confirmed cold prompt. The fixed
`h713-hdmi.scr` (sha256 1e677d4b…) was loaded to 0x52000000 over YMODEM
(`tools/serial/ymodem-send.py`, U-Boot CRC32 2235e726 matched) and sourced,
exactly as bootcmd does after its fatload.

- U-Boot: source-3 transition verified, "cold startup handoff verified",
  kernel started (`resume-1/source-fixed-script-serial.log`).
- Linux, no manual step: handoff `48444d49 00000000 8b8f275c`, both units
  active, DSP 0000/0000 -> 1/1, 22-word graph verified, receiver clocks 4 and
  clients 2, EDID ready, signal ready/failed=N, DDC held, no diagnostic
  modules (`resume-1/check-startup.log`, `tools/hdmi/check-startup.sh`).
- `update-startup-script.sh` installed the fixed script to the FAT and
  /usr/lib/h713-hdmi; previous generation kept under /var/lib; FIT checksum
  re-verified (`resume-1/update-script.log`). /mnt/boot unmounted cleanly
  afterwards (the FAT carried an earlier dirty flag).
- `run-alsa-capture-test.py --persistent-signal` passed 48/32/44.1 kHz host
  HDMI tones through the running signal owner: no bounded helper, valid host
  ELD, tone fraction 0.99999 on both channels, 0 XRUN, final second silent
  (`resume-1/capture-3-rates/`). Recorder staged in /tmp only.

Active-recording poweroff with the persistent signal owner PASSED the
strict checker (`poweroff-1/`, tools in `poweroff-tools/`, adapted from the
2026-10-14 active-recording-poweroff run): live 48 kHz tones, recorder RUNNING
at the request marker, then recorder stop -> signal module restored
peripheral/SRAM/vectors, SCP stopped, client released -> DDC pins released ->
signal unit stopped -> backend restored 22 DSP and 15 TVFE words, parked,
receiver removed -> Power down, 90.03 s without reboot. The operator confirmed
lamp and fan off and the board stayed off (`poweroff-1/operator-confirmation.json`).

Fully autonomous cold autoboot PASSED (`autonomous-1/`): serial and USB
unplugged, power off >= 1 min, no interaction. bootcmd FAT-loaded the fixed
script; Linux handoff 48444d49/0/8b8f275c. At 14 s uptime the capture unit was
still activating (`check-startup-early-14s.log`); at 23 s `check-startup.sh`
passed every condition. 48/32/44.1 kHz capture through the persistent signal
owner passed again (tone fraction >= 0.999999, 0 XRUN).

## Earlier record

Persistent startup bundle and enabled capture/signal units are installed.
The original kernel FIT and bootloader binary are unchanged. Saved U-Boot
preboot/bootcmd now select the separate script, retain GP7 reboot handling,
preserve the five-second recovery window, and keep previous commands as
rollback environment values. Full original environment is under activation/.

Passed so far:

- Confirmed cold RTC GP words all zero, exact MIPS parked status.
- Existing managed source-3 boot, capture backend startup and terminal stop:
  22 DSP words and 15 TVFE words restored, MIPS parked, receiver removed.
- Installed bundle hashes, unchanged FIT checksum, script byte comparison,
  and target systemd verification of both persistent units.
- RTC GP6 latch survived a real warm reset. Saved bootcmd executed the script,
  skipped every display/MIPS launch, and booted the original FIT. Capture
  remained inactive with ConditionResult=no and no current-kernel handoff.
- 19 session tests, 7 existing boot tests, 4 signal-service retention/order
  tests, payload preservation test and clean W=1 signal module build.
- The continuous signal owner's SCP code/EDID header is byte-identical to
  the previously tested endurance header (SHA256 89627ae0dc603d8909a02daff92b1ddfce63febca43457b6e509c97db70f0109).

The warm-check.log ends with an unavailable guessed nvmem sysfs path; warm
retention is established by the UART skip path, not that failed read. The
first signal-install.log ends with a FIT check before the FAT was mounted;
subsequent mounted verification in warm-check.log passed. These original
logs are retained without hiding their failures.

Pending: autonomous physical cold boot, continuous signal owner ready,
real capture through this startup path, and signal-before-backend shutdown.
The operator was asked to cold-cycle and allow autoboot. No persistent UART
listener is running, and no warm firmware or DSP reinitialization was tried.
