# Exact installation and rollback packet — November 3, 2026

**Prepared and verified offline. No live board commands, installation, rollback
or repartitioning were performed during this preparation.** The candidate is
still unqualified on hardware.

The private, sealed packet is
`local/releases/h713-ddr3-installation-packet-20261103/`. It contains gated
`INSTALL.md` and `ROLLBACK.md` command transcripts, `RECOVERY.md`, a machine
phase manifest, payloads, complete baseline image, pinned rescue artifacts,
bundled YMODEM helpers and a standalone verification/readback tool. This is
operator/controller review data; it does not contain an automatic live flasher.
Receipts belong outside the sealed directory. Images contain private device
configuration and keys and must remain outside Git.

## Exact write scope

| Extent | Start LBA | Install sectors | Rollback sectors |
| --- | --- | --- | --- |
| Linux p26 `linux` | `0x54c400` | `0x400000` (2 GiB) | `0x580000` (2.75 GiB) |
| Boot FAT p2 `bootloader_b` | `0x22000` | `0x10000` | `0x10000` |
| U-Boot proper | `0x49ac00` | `0x74b` (1867 sectors) | `0x74b` |
| SPL, written last | `0x10` | `0x40` | `0x40` |

The proper FIT's exact length and eGON SPL checksum are checked. Proper is
explicitly padded to its existing 1867-sector extent. Temporary fastboot raw
aliases include `mmcpart 0`, have the exact byte/sector capacity, and cannot
collide with GPT names or A/B names. They are set only in RAM and never saved.
Every phase requires identity/size/slot checks and a successful MMC read/CRC32
checkpoint before proceeding. `fastboot continue` returns to the same running
U-Boot; the packet does not issue a fastboot reboot.

GPT, Android p27 `UDISK`, `super`, the active and old environments, SPL stash,
rescue proper, vendor regions and all bytes outside the selected write windows
are protected by complete-disk readback comparison. No Android space is
reclaimed. The candidate's first boot grows the 2 GiB filesystem within the
existing Linux partition; rollback restores its full original 2.75 GiB extent.

## Transfer and readback

The original candidate sparse image can contain skipped blocks. Packet root
and FAT payloads instead wrap **every logical block as RAW**, including zeros.
The pinned fastboot host splits these into transfers bounded to 16 MiB for the
32 MiB target buffer. No partition erase or bulk UMS write is used.

The installed U-Boot lacks a SHA-256 shell command. CRC32 provides immediate
UART checkpoints; **full read-only host SHA-256 comparison is mandatory before
first boot**. A board-serial-specific udev rule enforces read-only disk and
partition nodes and grants only host read access, avoiding a separate UDisks
authorization/ACL step. All 28 nodes must be read-only and unmounted. The
readback tool opens only `O_RDONLY|O_DIRECT` and records the packet hash, host
boot ID, time, mode and observed digest in a new external receipt.

Expected entire user-area SHA-256 values, calculated offline:

- Baseline and complete rollback:
  `c79e110a8e1029a69b0ca5e7e93c2108cf0aed1cbd74c780245c7ad7f3f0095c`.
- Installation before first boot:
  `bb665353bf41129f618eec2daff893c2f4d794884220c5059f1dabb3df825048`.

These are predictions, not observed installation results. After first boot,
rootfs growth and ordinary logs change the disk hash. Recovery preflight allows
unknown contents only inside the four rollback windows and cryptographically
checks every byte outside them. It cannot substitute for final installation
or rollback readback. Rollback preserves the documented baseline FAT
inconsistencies without repair.

## Offline validation

- The packet's own standalone tool verifies all 37 sealed files, both GPT
  copies, phase commands, bounded writes, complete sparse payloads, CRC pins,
  canonical transcripts and whole-device overlays.
- Applying all rollback payloads to the baseline reconstructs its exact entire
  user-area hash.
- Eight test groups cover GPT CRC/overlap/relocation and SPL overlap through
  table expansion, eGON corruption, oversized writes, path/symlink escapes,
  zero-block coverage, outside-window changes and recovery masking.
- Ten mutations of a real generated plan are rejected: Android target/LBA,
  oversized span, wrong hardware partition, environment save, missing final
  readback, early SPL, reboot, erase and escaped input path.
- The actual fastboot 37 client passed a localhost-only protocol test against
  in-memory storage: a 40 MiB transfer split into three downloads wrote each of
  10,240 blocks exactly once, including zeros. No USB device was contacted.
- Standard `simg2img` reconstructed the actual 2 GiB install and 2.75 GiB
  rollback payloads byte-for-byte, including the format's sizes above 2 GiB.

[Machine-readable result](RESULT.json). TCP test framing follows the
[primary fastboot protocol specification](https://android.googlesource.com/platform/system/core/+/refs/heads/main/fastboot/README.md#tcp-protocol-v1).
The relevant installed-base and checked-out U-Boot MMC/block fastboot source
blobs were confirmed identical during review; the release carries its source
pin, patch inputs and configuration.

## Recreating and reviewing

`tools/release/prepare-install.py prepare` takes explicit candidate, verified
backup, CID/capacity evidence, rehearsed rescue SPL, host FEL executable
(`--fel-tool`) and a **new** output path.
It verifies both source ledgers and creates private CoW copies where supported;
it never uses hard links. The packet's `packet-tool.py verify --packet DIR`
performs offline verification. Only its explicitly selected `readback`
subcommand accesses a device, read-only; no subcommand flashes one.

The bundled Linux x86-64 FEL executable has a recorded SHA-256 and all its
dynamic libraries resolved on the preparation host. Recovery invokes
`tools/sunxi-fel` from the packet directory, without relying on PATH. The
read-only rule passes udev 262 validation; that version reports a deprecation
notice for non-system `OWNER=chris`. Rule validation remains a live entry gate.

Live execution still requires a fresh or revalidated cold-held board, the
provided temporary host guard, matching preflight receipts, reply checks for
each phase, final readback, SSH host-key pinning through UART, and subsequent
[hardware qualification](../../production-qualification-plan.md). The complete
new recovery sequence has not been rehearsed; its FEL SPL is the separately
pinned, previously rehearsed recovery input. No commit or push was made.
