# Reset investigation baseline — October 20, 2026

Initial read-only SSH inventory of boot `db069b53-ae5d-41f8-9005-b05ae7aa956f`,
using instrumentation source commit `5ebc711`. That inventory changed no
firmware, environment, boot media, service state, or power/reset state. The
subsequent approved installation, shutdown and cold baseline are recorded
below. Full local snapshots,
recovery binaries and preparation scripts are under
`build/hdmi-reset-baseline-2026-10-20/`; their identities are recorded in
[result.json](result.json). Raw firmware/environment backups stay local.

## Initial running baseline

The board runs the expected October 16 6.18.38 kernel. Capture and signal
services are active and the speaker service is running. The handoff is
`48444d49 00000000 8b8f275c`. Receiver clocks=4, clients=2, firmware pin and
EDID readiness are set, with no receiver initialization error. Signal is
ready and not failed. The capture PCM is RUNNING; the later snapshot reports
`period_xruns=0` and `dsp_failed=N`. Kernel logs record DSP versions `0/0`
before the pinned patch verified `1/1` on this boot.

Both Linux snapshots have the same boot ID. These are software-state and
digital-path observations, not a new audible/visual pass or a recovery test.

Fresh raw reads match these prior artifact identities:

| Artifact | Extent checked | SHA-256 |
| --- | --- | --- |
| Installed panel-fix stage-2 FIT | LBA `0x49ac00`, 1867 sectors | `4391dfa07bcf396b5096714814e933c7b59cff408b7a9964163812f686283880` |
| Rescue stage-2 FIT | LBA `0x4a0c00`, first 1798 sectors | `c882461d5ee69128c79d99b784fde668ee4d57ab09ae308738e3f9ea91fd1ce7` |
| SPL | LBA `0x10`, 64 sectors | `cb9da87448a57aa1cafbc7ebf66200b5183304cef1eafe23d0818b99696a49ec` |
| Kernel FIT | FAT `h713-kernel.fit`, 7795668 bytes | `0877293b3a71b9ccd28c0f0ef9725752a86dffd243851a5213eb023cd3a51c70` |
| Startup script | FAT and `/usr/lib/h713-hdmi` copies, 4245 bytes | `391835c5400cc5e583be8c1b82144ff85e03b483c8502b412147c6f7d9abb376` |

The boot FAT was read directly into a host-side image and inspected locally;
it was not mounted on the board. Embedded BL31 and U-Boot DTB were extracted
from the installed stage-2 FIT and compared byte-for-byte with the candidate.
BL31 hash is `5ea11b14cc59a85b3219b4969836948a1f99ab0381d620476e557f993c78636c`;
DTB hash is `8361009b1b72345c6d03d0e7ad98b6930753aea5c387e848677bdc0e587f464e`.
Both match. The first trial can therefore retain those components.

## Confirmed environment-address defect

The old backup named `env-lba49ec00.bin` and the fresh 64-KiB read at that
location are all zero, hash
`de2f256064a0af797747c2b97505dc0b9f3df0de4f489eac731c23ae9ca9cc31`.
That is the configured environment area, not the currently active environment.

The source path explains why. In `env/mmc.c`, `mmc_offset()` holds the
configured fallback in signed 64-bit `defvalue`, but passes it through
`ofnode_conf_read_int()`, whose argument and result are signed `int`. The
installed U-Boot DTB has no `/config` node, so that helper returns the narrowed
default. `mmc_get_env_addr()` then treats a negative offset as capacity-relative
and stores the resulting address in `u32`:

| Step | Value on this board |
| --- | --- |
| Configured byte offset | `0x93d80000` |
| After signed 32-bit helper | `-1814560768` |
| Add eMMC capacity `7818182656` | `0x165d80000` |
| Truncate to `u32` | `0x65d80000`, LBA `0x32ec00` |

A bounded read at the derived address contains a valid little-endian CRC32
over the remaining 65532 bytes. Its saved `preboot` and `bootcmd` exactly match
the installed guarded bundle, with bootdelay=5. Its SHA-256 is
`6eb7b7958139263f88cc0a0830b4ac33f4b4ca71b096081802b2f50f2cd205bc`.
The GPT inventory places this address inside `super`; the Linux root is a
different partition. This is an existing layout defect, not a trial write.

This establishes the active saved environment and the address-conversion
cause with source and readback evidence. Fix the fallback-width handling and
plan an explicit environment migration before the final integrated build.
Changing the offset handling alone would make the next boot miss the saved
guard configuration. Do not save environment to the intended or derived
location as an ad hoc repair. Leave address behavior unchanged for the first
observational reset comparison, and preserve/check both locations.

## Prepared trial package

The proper-stage payload is the FIT beginning at byte 32768 of the bench
combined image, not the raw `u-boot-dtb.bin`. The FIT is 955665 bytes and fits
the existing 1867-sector write extent after zero-padding to 955904 bytes.
The padded candidate hash is
`314d81a3e17646c0250bbbadaac38762560acad8378e1f8b0b141487b068664c`.
It contains the same BL31 and U-Boot DTB bytes as the installed image; only
the instrumented U-Boot payload/FIT metadata change. The installed SPL stays
unchanged, so optional SPL probe markers will not be present in this trial.

The local `trial-package/` contains that candidate, an exact current-proper
rollback, the actual active environment backup, identity-pinned install and
rollback scripts, and a read-only region checker. The scripts require explicit
action arguments, verify images and preimages, write only the 1867 sectors,
then verify the full surrounding 2-MiB region and protected SPL, rescue,
configured-environment and actual-environment areas. The installer additionally
requires the inventoried boot ID. Neither script reboots or changes services,
environment or latch state.

The region checker passed against the live board using direct reads. A mocked
sparse-disk fixture passed no-argument refusal, refusal after changing the
active environment, candidate installation/readback, and exact rollback.
These fixture writes touched only a temporary host file; no installation or
hardware rollback was performed. Script syntax checks and the six reset-tool
tests pass. Generated package files remain local for review before a trial.

## Next hardware step

The initial inventory had no UART device. After the user connected
`/dev/ttyUSB0`, passive recording started and received an explicit diagnostic
line emitted from the board's `ttyS0`. The boot ID and active services still
match the baseline. The exact trial package is staged in the new board
directory `/root/hdmi-reset-trace-2026-10-20`; all eight file checksums and the
live read-only region preflight pass. This copies review/recovery files onto
the root filesystem but does not write boot media or change startup policy.

The user then confirmed FEL/OTG availability and authorized installation and
orderly shutdown. `install.sh install` wrote exactly 1867 sectors at
LBA `0x49ac00`. The full 2-MiB region matched its expected after-image, and SPL,
rescue and both environment locations retained their expected hashes. The
readback checks passed; no SPL, environment or startup script was written.

At uptime 3018.87 s all three services were active and capture XRUNs were zero.
An ordinary `systemctl poweroff` request reached kernel `Power down` at
3026.147970 s. At 3025.722898 s it also reported
`ext4_mark_recovery_complete: Orphan file not empty on read-only fs` on
`mmcblk0p26`. The same error exists in the October 18 panel-trial shutdown
logs, so it predates this image; the cause and filesystem health remain open.
Do not count this as a clean-filesystem shutdown or proceed directly to an
abrupt reset. The user confirmed the lamp and fan were off, then completed
the requested physical cold cycle.

The exact previous boot's unit journal confirms speaker stop → signal/SCP/DDC
restoration → backend restoration of 22 DSP and 15 TVFE words → terminal
parking and receiver removal. Journal queries use the explicit boot ID and
monotonic output because the board's wall clock resets to an old date.
The HDMI teardown passed independently of the filesystem shutdown error.

The passive recorder was stopped cleanly after the cold baseline in
`build/hdmi-reset-baseline-2026-10-20/uart-trial/`. Installation, shutdown,
complete UART capture and Linux/journal snapshots have local hashes in
`result.json`.

## Instrumented cold baseline

Boot `fedfb946-1ce2-4617-b809-89ef2c8f53c0` reached Linux automatically with
all three HDMI services active, the expected handoff, receiver clocks=4 and
clients=2, signal ready, and zero capture XRUNs in the snapshot. DSP again
started at `0/0` and verified the pinned patch at `1/1`. No new optical or
acoustic quality observation was requested or inferred from these checks.

The installed banner is
`g320a17f71d41-reset-trace-77307168a30b`. Parsed
[cold-markers.json](cold-markers.json) retains these stages:

| Stage | GP6 | MIPS clock | MIPS reset | MIPS status |
| --- | --- | --- | --- | --- |
| Proper before preboot | `00000000` | `00000000` | `00000000` | `00000000` |
| Before logo workspace clear | `48444d49` | `00000000` | `00000000` | `00000000` |
| After logo commit/quiescence | `48444d49` | `80000002` | `00000000` | `00000000` |
| Before capture workspace clear | `48444d49` | `80000002` | `00000000` | `00000000` |

GP7 was zero throughout. Optional SPL probes were not installed. The trace
establishes that the observations occur before workspace clearing and shows
the normal cold path's two loads. It is not a warm-reset comparison or proof
of DSP reset-domain behavior.

The root mounted read-write after journal recovery, warning that it has
recorded errors. Read-only `dumpe2fs -h` reports `clean with errors`, error
count 61, with first and last recorded errors in
`ext4_mark_recovery_complete`. The growfs service failed because ext4 refuses
online resizing in that state. `needs_recovery`/`orphan_present` feature flags
were also visible while mounted; those flags alone are not an offline
consistency verdict. No fsck or repair was run against the mounted root.

Prepare an offline check with `/dev/mmcblk0p26` unmounted, retain a rootfs
backup and diagnostic output, then review any required repairs before making
filesystem changes. Do not clear the error flag or disable orphan-file
features to make the next test pass. Return to the
[paired trial procedure](../../hdmi-reset-instrumentation-2026-10-20.md) only
after the filesystem prerequisite is resolved. The board remains running on
the instrumented proper with HDMI services active; no further reset was made.
Automatic warm capture and the environment migration remain unfinished.
