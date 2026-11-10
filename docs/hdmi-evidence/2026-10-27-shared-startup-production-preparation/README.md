# Production shared startup: offline preparation, October 27

**Offline PASS; not installed or board-tested.** No SSH, serial open, board
command, RTC access, reset, install, commit or push occurred during this work.
The board was last checked powered off in the clean RAM-only abrupt trial.
Its installed script still has the old logo-only warm branch. Policy/install
approval and a separate operator-ready gate remain required.

## Candidate and behavior

Bundle: `build/hdmi-shared-startup-production-2026-10-27/`.
Generate with `python3 tools/hdmi/build-shared-startup.py NEW_OUTPUT_DIRECTORY`.
The older `build-startup.py` entry point now delegates to this same delta
builder: it cannot emit the shared script paired with the old installer that
omits health acknowledgement. It refuses an existing output directory.
This update targets the current installed generation; it is not a fresh
installation bundle. It does not replace modules, DSP firmware, kernel,
shutdown guard, capture/signal ownership, video/speaker units or saved U-Boot
environment. The manifest records unchanged preboot/bootcmd for comparison.

| GP6 at boot | Behavior |
| --- | --- |
| `00000000` | Validate cold-equivalent census, write `HDMI`, launch shared sequence |
| `48444f4b` (`HDOK`) | Same shared sequence and pre-launch `HDMI` write |
| `48444d49` (`HDMI`) | Existing logo-only fallback, no handoff or ack |
| Any other value | Same logo-only fallback |

Census checks MIPS status `0306101c`, clock `02001600`, reset `0200160c`,
GP7 `0709011c` and PPU bus `070101ac` are zero before the GP6 write or lamp-low
operation. GP6 is latched before the first firmware operation. Existing
image/record stages are byte-identical to installed; source-3/TCON/handoff
stage differs only in its diagnostic message. Launch retains existing
firmware verification and restores PB5 on failure. See [startup.diff](startup.diff).

`h713-hdmi-health-ack.service` requires and follows capture and signal. It
checks this boot's handoff/session and the existing read-only startup checker,
validates the RTC DT/provider/driver and 32-byte bank, rechecks boot ID and
latches, then writes exactly four bytes of `HDOK` at nvmem offset `0x18`.
It verifies GP6 readback and unchanged zero GP7. Already-HDOK is idempotent;
wrong/unknown GP6, pending GP7, changed boot/latches, or failed checks refuse.
A short write or bad readback fails without retry. No MMIO or GP7 write.
The unit does not require a connected source, video, speaker or PCM consumer;
no HDMI signal is a healthy supported startup state. It has no retry or
ExecStop. Shutdown behavior is unchanged. This acknowledges startup health,
not indefinite runtime health; a later crash after HDOK permits another launch.

The dedicated updater validates bundle and installed checksums, pinned FIT,
old script and FAT agreement, then saves a checksummed transaction backup under
`/var/lib/h713-hdmi-startup/shared-*/`. It stages/fsyncs health files, installs
and enables the unit **without starting it**, updates only the installed
script/cmd checksums, and activates the FAT script last. It never writes RTC.
The old current boot is deliberately not acknowledged by installation.
Failures leave `INCOMPLETE`; do not reboot or rerun blindly. Verified rollback
restores the old script/cmd/manifest/FAT and removes this health integration.
The tested recovery paths cover enable failure and partial backend update;
these tests do not establish power-cut resilience at every filesystem boundary.

## Offline evidence

* [11 startup tests](test-build-startup.log), [46 existing warm-runner tests](test-warm-shared.log),
  [13 production tests](test-production.log): **70 passing**.
* [17 deliberate implementation mutations](mutations.log): **all caught**,
  covering every new test. Includes four-state selection, unacknowledged next
  boot, census refusal before firmware/PB5, source preservation, missing unit
  packaging, GP6 offset, current-boot health, GP7 preservation, provider
  ambiguity, latch race, readback, unit ordering, dry-run, FIT pin, enable
  failure and premature FAT activation. Mutations affect loaded code or unit
  text in memory; tests use temporary roots and ordinary fake nvmem files.
* [systemd unit verification](systemd-verify.log): **exit 0** with health,
  capture and signal units together. Sandbox initially blocked local credential
  sockets; read-only host verification outside it passed without output. No
  services were started or loaded.
* [Bundle checksum verification](bundle-verification.log): all files PASS.
  [Manifest](build-manifest.json), [bundle checksums](bundle-SHA256SUMS).
* Script SHA256 `fcea3a9589432f9b44781178d70433486aac5872a618970039b3326744e7fe7b`.
  Installed predecessor `391835c5400cc5e583be8c1b82144ff85e03b483c8502b412147c6f7d9abb376`.
  FIT remains `0877293b3a71b9ccd28c0f0ef9725752a86dffd243851a5213eb023cd3a51c70`.

## Proposed installation and test sequence — not executed

First obtain explicit approval for **production installation and the GP6
HDMI→HDOK policy**, as required by the shared-startup plan and board-action
rule. Then announce this sequence, end the turn, and wait for **ready**.
Approval for offline work is not approval to execute any step below.

1. With board off, disconnect mains, board serial and USB for at least one
   minute. Keep the host HDMI session running; prepare a moving 720p60 pattern
   and tone, save its volume/routing. Arm one UART reader and explicitly report
   **OPEN** before the user reconnects board serial first, then mains. USB
   remains disconnected. No host logout/reboot. Capture the complete old
   production cold boot; confirm moving picture, correct colour and audible
   tone before installation. Silence or black is a stop condition, not a
   reason to restart services and continue the acceptance run.
2. Collect read-only inventory: boot ID, handoff, DSP 0/0→1/1 log, service
   state, runtime domains, RTC identity/GP6/GP7, installed manifest, FIT pin,
   FAT script hash and saved preboot/bootcmd. Require exact predecessor hashes
   above and the unchanged environment. Run `check-warm-shared.py collect cold
   --output EVIDENCE/pre-install.json` on the host. Mounting boot FAT, staging
   under `/run`, and the checker's scratch files are writes covered by the
   requested install/test approval. Mount only `/dev/mmcblk0p2` at `/mnt/boot`
   if not already mounted. A different mounted source or inventory mismatch
   stops for review.
3. Transfer the complete verified bundle to `/run/h713-shared-startup-update`
   and verify `sha256sum -c SHA256SUMS` there. Run target-local:

   ```sh
   python3 /run/h713-shared-startup-update/install-shared-startup.py --dry-run
   python3 /run/h713-shared-startup-update/install-shared-startup.py --install
   ```

   Record returned absolute backup path; copy its record/old checksums to host
   evidence before proceeding. Verify installed backend and health checksums,
   FAT candidate hash, unit text/enabled state, and unchanged FIT/environment.
   Health unit must remain **inactive** this boot. No manual ack, reset,
   capture/speaker restart or GP7 arm. If installation fails, stop and inspect
   `INCOMPLETE`; use verified rollback before any boot.
4. Checked poweroff and observe UART `Power down`. Have the user disconnect
   mains/board serial/USB ≥1 minute. Re-arm UART **OPEN** before serial/mains
   reconnection. This physical cold cycle is required: the old boot still has
   `HDMI`, so an immediate warm reboot would correctly enter fallback. On the
   first new boot expect one shared launch, source-3/re-latch/handoff, GP6
   `HDMI` then automatic `HDOK`, and GP7 zero. Capture health-ack JSON/journal
   and `systemctl show` result (active/exited, status 0, no restart). Confirm
   moving picture, colour and tone with the operator. Run startup/audio/video
   checker and collect the new cold baseline. Use health ack `--dry-run` to
   validate HDOK idempotence without RTC writes; never invoke manual real ack.
5. Five ordinary **unattended board reboots**, one at a time. Before each,
   require healthy current boot, GP6 HDOK/GP7 zero and saved evidence. Capture
   UART continuously. Issue `systemctl reboot` on the board, wait for a new
   boot ID, and require shared launch/handoff, DSP initial 0/0 then 1/1,
   capture/signal/health/video/speaker healthy and automatic HDOK on each boot.
   Use host `check-warm-shared.py collect warm --output EVIDENCE/warm-N.json`
   and `compare EVIDENCE/cold.json EVIDENCE/warm-N.json`. Verify moving video,
   colour and tone each time (operator records observations during the agreed
   sequence); target the proven ~60 fps/zero rejects and new xruns. Record
   service start relative to kernel boot (~21 s historical), and measure actual
   power/reset-to-picture separately. Do not count a host player restart as
   uninterrupted-source recovery; if the host drops routing, record/stop that
   case rather than silently masking it. No prompt hold, RAM source or GP7 arm
   is used: this tests the installed boot path.
6. One **synced SysRq-b** from a freshly verified healthy HDOK boot, after all
   orderly boots pass: drain UART evidence and record boot ID, then board
   `sync` followed by one `echo b > /proc/sysrq-trigger`. No service teardown,
   GP7 arm or U-Boot stop. Capture reset through new Linux boot and apply the
   same health/digital/on-glass gates. No automatic repeat on failure.
7. After a passing sequence, checked poweroff and one additional physical cold
   boot with HDMI disconnected at the projector (same UART OPEN procedure).
   Require console plus healthy capture/signal and automatic HDOK **without an
   HDMI source**. The existing speaker may still own the PCM: consumer
   independence is established by unit/checker dependencies, not by claiming
   this live case has no PCM owner. Then user reconnects HDMI and verifies automatic
   video/tone. This tests health independence from signal lock. Finish with
   agreed checked poweroff, restore host volume and stop the test player.

At every failure: stop resets and preserve UART, boot ID, latch and health
records. Do not force GP6 values or probe prohibited ranges. Forced-HDMI and
unknown-state negative tests remain **offline/dry-run only**. A naturally
unacknowledged boot should fall back next boot; do not turn it into repeated
retries. Track any panel-black or isolated cold-audio silence separately.

### Rollback if needed (only under board-write approval)

Use the preserved updater in `/run` while available, or its installed copy
`/usr/lib/h713-hdmi-health/install-shared-startup.py` after a reboot:

```sh
python3 /usr/lib/h713-hdmi-health/install-shared-startup.py --rollback /var/lib/h713-hdmi-startup/shared-EXACT_RECORDED_TRANSACTION
```

Use the exact returned backup path, never a guessed newest transaction. The
updater verifies the backup, permits only old/new known script hashes, refuses
foreign unit/backend changes, disables only the health unit, and restores the
old backend and FAT. Capture/signal shutdown ownership is unchanged. It does
not write GP6 or GP7. Verify restored hashes and unit removal, then checked
poweroff and a **physical cold cycle**: old startup treats HDOK as nonzero and
would otherwise take its logo-only warm fallback. If rollback cannot verify
its inputs, stop for review; do not force it. No board rollback has been run.
