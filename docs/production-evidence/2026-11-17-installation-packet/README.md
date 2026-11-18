# Offline backup and installation packet — November 17, 2026

**Backup taken read-only; packet prepared and verified offline. No board
storage was written; nothing was installed or rolled back.** The candidate is
the [November 17 final build](../2026-11-17-final-build/README.md) of
`cb939748`, still unqualified on hardware.

## Live inventory (read-only, boot `24ee80c2`)

eMMC CID `15010038475446345208604bbe691991`, 15269888 sectors, the same 27
partitions as November 3 (Linux p26 `linux` at LBA 5555200, Android p27
`UDISK`). System running, no failed units, ext4 errors 0, startup check PASS,
CPU_COMM IRQ receive, both HDMI manifests verified.

- All 24 boot FAT files are byte-identical to the candidate's, including the
  FIT `966eba3c…` (the delta installs had already put it there).
- Proper is the November 15 U-Boot 0006 build (`c37c8d23`); the candidate's
  is the 0007 build. SPL is still the November 3 one (`d593ab79…`).
- Of 17,352 candidate rootfs files, 12 differ: `/etc/machine-id` and five
  regenerated `.pyc` files (expected), plus the two HDMI `SHA256SUMS`,
  `h713-hdmi-v4l2.ko`, `modules.builtin.modinfo`, `aic8800_fdrv.ko` and
  `h713-lamp-ramp`.
- Against the November 3 capture: backup GPT, boot0/boot1 and the rescue
  proper at LBA `0x4a0c00` are unchanged; proper, environment and SPL changed
  only through recorded installs (the November 3 capture predates that day's
  SPL install). Primary GPT sectors are unchanged.

## Offline backup

Entry: `systemctl reboot --reboot-argument=bootloader` with a passive UART
listener; preboot consumes the `b007c0de` marker and sets `bootdelay=-1`, so
the prompt held with no keypress, and `gpio set PB5` read back 1. (A first
cold-boot catch missed: since November 5 the saved environment has
`bootdelay=0`, and a space sent after the autoboot line arrives too late.
Nothing was written.) `ums 0 mmc 1` enumerated with all 28 host nodes
read-only via a serial-pinned temporary udev rule, none mounted.

Two full `O_RDONLY|O_DIRECT` reads matched: 7,818,182,656 bytes,
**`b28471c260803d67df633aa2f5993fe9458d8643ea43711f4bc318504ed3ee56`**,
1510 s. The board was returned with Ctrl-C and `reset` and came back healthy
(boot `bc33d684`).

Host-copy verification: both GPTs pass CRC with identical arrays; all five
protected regions match the live pre-shutdown capture; `e2fsck -fn` clean on
Linux p26 and `fsck.fat -n` clean on the boot FAT (the November 3 FAT
inconsistencies are gone); 50 runtime files match the live inventory through
`debugfs`; the backup's FIT matches the live boot FAT. Rollback extents:

| Extent | SHA-256 |
| --- | --- |
| Linux p26 (2.75 GiB) | `4191bd4469cb71a701a725098feb7d23bcde37ee06508d2e229c9156362cddc7` |
| Boot FAT p2 | `c75adeaefd317e3b41106ca36caba04bf3e0b6049143d5deef3866839aba9abf` |
| U-Boot proper (1867 sectors) | `24d2528585a971ccdcc77bea21a49e935d30d1f14f7c3ba0b9c639ec60895abc` |
| SPL region | `d593ab799b6d422523d67a33c7427c481765e5afac71f065cc2f16e162ce18cf` |
| Environment (64 KiB, `bootdelay=0`) | `e6a56d4c6f2703c9360c29da4d1e1aec2d35bafd57bc6ca8232896e0296bc3ab` |

## Installation packet

`tools/release/prepare-install.py prepare` built the packet from the sealed
candidate, this backup, the CID/capacity evidence and the pinned rescue SPL
(`dab3b158…`) and FEL tool (`7a6deced…`). The candidate's boot environment
matches the board's, so no environment save is involved. Same four write
extents as November 3: Linux p26 at `0x54c400` (2 GiB install, 2.75 GiB
rollback), boot FAT at `0x22000`, proper at `0x49ac00` (1867 sectors; the
candidate's 955665-byte FIT is padded), SPL at `0x10`, written last.

- Baseline and complete rollback: `b28471c2…` (above).
- Installation before first boot (predicted):
  `f5e192e1ffbf3fdc66b0020c196cc16734726735af7061c15449dd9c475aaf25`.

`packet-tool.py verify` passes (37 files, checksums, layout, bounded phases,
all-RAW payloads, whole-disk overlays) and the release packet tests pass.
These are predictions, not observed installation results; a full rollback
write has still never been rehearsed.

Private, not committed: packet `local/releases/h713-ddr3-installation-packet-20261117/`,
candidate `local/releases/h713-ddr3-production-20261117-candidate/`, backup
and evidence under `local/recovery/2026-11-17-deployment-packet/`.
