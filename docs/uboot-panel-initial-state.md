# U-Boot panel initial state: build, validation and rollback

Updated 2026-10-19. The normal build includes the panel initial-state fix tested
on the HY200 QZ713DF_A1 DDR3 bench board. It establishes quiet LVDS, held reset
and an off panel-supply control state before logo register replay, then waits
at least three seconds (or a larger DT `off-on-delay-us`). Normal on-side timing
is retained. The cold-HDMI firmware-only relaunch keeps the panel powered.

The previous 550 ms wait preceded first regulator acquisition. First probe can
turn PF6 off, and a disable returning `-EALREADY` need not wait at all. The fix
starts its explicit hold after reset/supply-off readback. Readback verifies
control state, not physical rail discharge; three seconds is a conservative
bench interval, not a measured minimum. It adds at least three seconds to each
stock panel-power startup. The precise panel-internal fault remains unproven.

## Normal build

```sh
JOBS=8 tools/build/build.sh uboot
# -> build/out/u-boot-sunxi-with-spl-ddr3.bin
# -> build/out/u-boot-ddr3.inputs (source, patch, DT, config, BL31, image hashes)
```

The build exports `UBOOT_SOURCE_COMMIT` from `config/versions.env`
(`320a17f71d41ed0d4be7aab25947ce015c98c48e`), applies
`patches/u-boot/series`, then synchronizes the prepared kernel's H713 DTS,
bindings and generated CCU table. Its source cache is keyed by the actual
inputs; the source submodule and diagnostic worktree are left untouched.
The later submodule HEAD `9d35a4e` trace change is deliberately excluded from
this tested baseline. The upstream provenance pin `UBOOT_BASE` is separate.
Kernel prerequisites 0182–0187 describe PF6, panel supply/reset and shutdown,
USB, watchdog and UART pins. Independent audio experiments and filesystem ACL
changes are excluded from this integration commit. Audio results below were
measured on the existing bench kernel, not a new kernel installed by this work.

`0000` carries the tested shared-DT/DM regulator prerequisites and DDR3 lamp
policy. `0001` is the focused initial-off change. DDR3 keeps PB5 lamp/fan off
until the guarded logo script enables it; if stopping manually at U-Boot,
`gpio set PB5` turns the shared lamp/fan line on. No independent fan line is
introduced. Preserve the existing guarded HDMI startup script and kernel panel
supply/reset/shutdown support; this patch does not install those components.

```sh
UBOOT_TREE=$(tools/build/build.sh uboot-tree)
python3 patches/u-boot/tests/test-panel-initial-state.py \
  "$UBOOT_TREE/arch/arm/mach-sunxi/h713_mips.c" \
  build/panel-initial-state-review/normal-tests
# Alternative helper uses the same prepared source:
tools/build/uboot-build.sh /absolute/output/dir hy200_qz713df_a1_defconfig
```

`uboot-tree` prepares the kernel source if needed, but does not compile Linux.
`BOARD=lpddr3` retains the separate V2 profile; its build is checked, but this
hardware validation applies only to the DDR3 A1 board. Build commands do not
flash anything. The banner identifies the base commit and input-digest prefix.
New build banners/timestamps differ from the tested binary;
the tested display/clock/PHY/DT sources and DDR3 configuration match.

## Hardware results

Detailed logs and qualifications are in
[the trial record](hdmi-evidence/2026-10-18-panel-initial-state-trial/README.md).
The [October 16/17 investigation history](panel-investigation-history/README.md)
keeps the earlier controls, failed outcomes and superseded hypotheses separate
from this October 18 validation set. Archival cleanup adds no new trials.

| Test | Result |
| --- | --- |
| Three independent cold/first-warm pairs, HDMI connected | 3 cold + 3 first-warm visual passes |
| Extra second warm in pair 1 | Logo/console pass; request uptime 147.26 s |
| Patched hold and Linux adoption | About 3.007 s UART off-log-to-first-record interval; Linux 1280x720 |
| Live video samples | Eight distinct 720p frame IDs; matching bands/stripes, single-copy diagnostic |
| Digital HDMI audio | 48/32/44.1 kHz input tests pass stereo tone/silence checks; fixed 48 kHz capture, zero XRUNs |
| Clean cold-start speaker listening | Audible pass before consumer restart/direct codec intervention; zero XRUNs |
| Immediate abnormal reset with HDMI services and PCMs live | SysRq-b at 465.752331 s after filesystem sync; logo/console returned |

First-warm request uptimes were 55.54 s and 70.41 s; pair 3's exact request
uptime was lost with its SSH output (kernel restart captured at 77.788714 s).
The extra second warm was not a matched 54 s prompt-control trial. UART
commit messages alone were not counted as visual passes.

The video double-copy attempt did not obtain a stable 720p frame; single-copy
samples passed probe-page and frame-content checks. This is not full-rate V4L2
or continuous video validation. Earlier transient audio silence remains
unexplained; a subsequent clean cold-start listening trial passed. The SysRq
trial skipped normal service/device shutdown but synced filesystems first;
it does not establish autonomous watchdog expiry or hung-kernel recovery.
Long-term reliability and all possible reset faults remain outside this set.

After a warm reset, the retained GP6 latch intentionally disables HDMI capture
until a physical cold cycle. Panel/logo/console recovery is expected; the
HDMI services being inactive on that warm boot is not a regression. Never
clear GP6 in software to bypass this guard.

## Installed image and rollback

To omit the fix from a future source build, comment out the `0001` entry in
`patches/u-boot/series` and rebuild, retaining `0000` and the shared kernel DT.
The series change selects a new source cache and banner digest. This does not
change the installed board; use the saved binary rollback below for that.
Re-enable the entry to restore the normal fixed build.

These locations and sizes are for this bench board's existing split layout,
not a generic flash recipe. The normal build's combined SPL+proper image must
not be written wholesale over this installed layout. The validation session
updated **only U-Boot proper**; no SPL, environment, kernel or startup script
was replaced by the trial installation.

| Artifact | Region / size | SHA-256 |
| --- | --- | --- |
| Installed validated trial proper | LBA `0x49ac00`, 1867 sectors / 955904 bytes | `4391dfa07bcf396b5096714814e933c7b59cff408b7a9964163812f686283880` |
| Previous stage-2 proper (exact rollback) | Same region and size | `cf1941d6f94441e55607f96ca83239b1c895b9b92166ccf2d6914aac46001423` |
| Existing older rescue proper | LBA `0x4a0c00`, 1798 sectors | `c882461d5ee69128c79d99b784fde668ee4d57ab09ae308738e3f9ea91fd1ce7` |
| Previously rehearsed FEL rescue SPL | `build/out/h713-rescue-spl.bin` | `dab3b1585a8d05d30d87a57795fa505409304ce7287cfa58d5c8deed1bcf75f0` |

The trial installation verified the full readback and unchanged surrounding
2 MiB region tail, rescue slot, SPL and environment. Fresh backups and scripts
are saved both on the board (`/root/panel-initial-state-trial/`) and host
(`docs/hdmi-evidence/2026-10-18-panel-initial-state-trial/`). Firmware backups
and large media captures are local recovery/test artifacts, not committed to
Git; preserve them separately before moving to another checkout. New builds have
new hashes; the table identifies the actual installed and backup artifacts.

### If Linux still boots

On the board, the saved script checks the exact rollback image size/hash,
writes only the 1867 sectors at LBA `0x49ac00`, then checks direct-I/O readback:

```sh
sh /root/panel-initial-state-trial/rollback.sh
# Only after its PASS:
systemctl reboot
```

If that backup is missing from the board, copy the host's
`proper-before-1867.bin` and `rollback.sh` into the same board directory first.
Verify the backup hash above. A failed guard/readback means stop and inspect;
do not continue to reboot or substitute a differently sized image. This
restores the pre-fix stage-2 proper; it does not change the kernel or guarded
HDMI startup environment and reintroduces the prior intermittent panel issue.

### If U-Boot proper cannot reach a prompt

Use the already rehearsed [FEL rescue procedure](uboot-lamp-flash-plan.md#recovery):
power off, connect UART and OTG, hold FEL while applying power, release, then
on the host verify the rescue SPL hash and run:

```sh
sunxi-fel -p spl build/out/h713-rescue-spl.bin
```

This loads the older rescue-slot proper without writing storage. At its known
good prompt, transfer the **exact stage-2 rollback** `proper-before-1867.bin`
by `loady 0x42000000` plus the existing UART YMODEM sender. After issuing
`loady`, close other UART readers (including passive capture and the terminal)
so they cannot consume handshake bytes. On the host run:

```sh
python3 tools/serial/ymodem_send.py \
  docs/hdmi-evidence/2026-10-18-panel-initial-state-trial/proper-before-1867.bin \
  --port /dev/ttyUSB0
```

Restart capture/the console after transfer. Check `filesize` is `e9600` (955904 bytes),
then hash RAM and compare to `cf1941d6...` above before any write:

```text
hash sha256 0x42000000 0xe9600
# Continue only after full hash and filesize match:
mmc dev 1
mmc write 0x42000000 0x49ac00 0x74b
mmc read 0x43000000 0x49ac00 0x74b
cmp.b 0x42000000 0x43000000 0xe9600
# Only after exact comparison succeeds:
reset
```

The FEL-to-rescue-prompt path was rehearsed on 2026-10-16; this particular
1867-sector YMODEM rollback has not been executed during validation. The
older rescue-slot image is not the exact stage-2 rollback and has a different
size. Do not overwrite SPL at LBA `0x10`, environment at `0x49ec00`, or rescue
at `0x4a0c00`. Keep the existing rescue SPL and backups when cleaning build
output; preserve them elsewhere before deleting their only local copy.
