# Handoff for RAUC A/B updates and signing on the H713 projector

Updated 2026-11-21. HY200_QZ713_V2 (Allwinner H713).

## Decision

Keep Debian RAUC 1.13 with U-Boot 2026.07-rc5 `bootmeth_rauc` and RAUC's
`uboot` backend. Sign verity update bundles and use signing-time certificate
validation for offline installation. Keep SHA-256-checked, unsigned kernel
FITs and the legacy boot script. Boot-ROM secure boot remains disabled and
FEL remains available for service recovery.

RAUC fits the existing A/B layout and authenticates updates from a USB
stick and over the network. The proposed systemd-sysupdate design would
require its own offline verification and staging, plus a new boot-selection
integration. The EFI timing measurements below are useful background if
that design is revisited.

## The product and its constraints

- **Board.** Allwinner H713: 4× Cortex-A53 with the ARMv8 crypto extensions,
  1 GiB LPDDR3, an eMMC (Samsung eMCP), and one USB-A port.
- **Sealed product.** The user has no UART or buttons. It has to boot and
  recover unattended.
- **Software.**
  - Debian 13 "trixie", arm64, systemd 257.13.
  - U-Boot 2026.07-rc5 with our patches.
  - Linux 6.18.38 with our patches.
- **Root and data.**
  - A read-only EROFS root (lz4hc, 556 MiB) per slot.
  - One ext4 data partition (`/data`) holds the overlays for `/etc` and `/var`.
- **USB.** The one USB-A port is chosen as host or device in software (USB
  device mode is done and tested this session). Updates must be possible:
  - from a USB stick (host mode);
  - over SSH on USB networking (device mode);
  - over Wi-Fi.
- **No lockdown wanted.** The owner explicitly does not want to lock the
  board down: no eFuses, no boot-ROM secure boot. The vendor Android image is
  kept as a reference, and FEL (the boot ROM's USB recovery) must keep
  working.
- **Other developers use this repository.** Anything that adds setup steps or
  per-developer state counts against a design.

## Board integration

**A/B layout.**
- Two slots, each a pair:
  - slot A is boot_a (vfat: the kernel FIT plus `boot.scr`) and root_a (the
    EROFS root);
  - slot B is boot_b and root_b.
- Two redundant U-Boot environment copies sit in the GPT partition `empty`.

**U-Boot.**
- The V2 boots through Standard Boot (`bootflow scan -lb`), declared in a
  `bootstd` devicetree node: `bootdev-order = "mmc1"`, with a single
  `bootmeth_rauc` node.
- `bootmeth_rauc` takes one attempt from the first slot in `BOOT_ORDER` with
  `BOOT_<slot>_LEFT > 0`, saves the environment, and runs that slot's
  `boot.scr` with `rauc.slot=A|B` in the command line.
- `boot.scr` is a legacy `mkimage -T script` image. It reads the RTC GP7
  register for a one-boot `reboot usbdev` request, then `bootm`s the FIT. The
  FIT holds the gzip kernel and two DTBs, with sha256 hashes that `bootm`
  checks. It is not signed.
- U-Boot patches: 0012 is the A/B boot, 0013 makes a saved `bootdelay=-1`
  harmless (below).

**Linux.**
- Debian's `rauc` 1.13 and `rauc-service`, with the `uboot` backend; `fw_setenv`
  comes from libubootenv.
- A meta-rauc-style `rauc-mark-good.service`.

**Tested on the projector:**
- A boots unattended and is marked good.
- Switching to B works.
- After three boots of B without mark-good, it falls back to A.
- Slot B was written with the installer while A stayed known good.

**A real trap, found and fixed (U-Boot 0013):**
- `reboot bootloader` holds the U-Boot prompt with `setenv bootdelay -1`.
- `bootmeth_rauc` saves the environment on every boot, and so does a manual
  `saveenv`. Either one stored the `-1`, and from then on every boot stopped
  at the prompt. On a sealed product that means it never boots again. It
  happened once on the bench.
- 0013 starts PREBOOT with `env default -f bootdelay`, which runs before
  autoboot reads the value. Tested: `-1` saved at the prompt, and the next
  boot still counted down and booted.

## Bundle build and trust policy

| File | Role |
| --- | --- |
| `tools/keys/make-dev-keys.sh` | Creates and reuses a local P-256 RAUC CA and code-signing certificate under git-ignored `local/keys/rauc/`. Incomplete key directories are reported so an existing board does not lose its trust anchor through silent regeneration. |
| `tools/rootfs/make-ro-images.sh` and `tools/rootfs/ro-root.sh` | Install the public CA and daemon config under `/usr/lib/h713/` on the EROFS root. The service explicitly loads `/usr/lib/h713/rauc-system.conf`, so an old config in the shared `/etc` overlay cannot shadow it. `H713_RAUC_KEYDIR` selects an existing signing directory. `H713_RAUC_KEYRING` lets an image builder supply just the public CA. |
| `tools/v2-rauc-bundle.sh ROOT_IMAGE BOOT_IMAGE OUT.raucb [VERSION]` | Builds a verity bundle for `hy200-qz713-v2` with Debian arm64 RAUC 1.13 under QEMU user mode. The unchanged EROFS bytes are packaged as `rootfs.img` so RAUC 1.13 dispatches them to the raw slot handler. The boot member is `boot.vfat`. The builder checks the signature against the CA extracted from the input root image before publishing the bundle. |
| `patches/kernel/board/hy200_qz713df_a1_defconfig` | Enables loop devices, device mapper, dm-verity and SquashFS with zlib for mounting a local verity bundle. RAUC uses dm-verity to check the bundle payload during installation. |

RAUC 1.13 verifies signatures on its supported install paths. Host checks
with Debian arm64 RAUC verified and extracted both bundle members byte for
byte. The host checks also rejected an unrelated CA and a corrupted payload.
Per-developer keys save setup time but create separate trust domains. For
shared boards, use CI-signed development bundles and the matching public
CA. Provision release trust separately through `H713_RAUC_KEYDIR` and keep
private signing material off the devices.

The FIT-signing prototype was discarded. FIT signatures can constrain a
writer limited to the boot partitions, provided U-Boot, its boot policy and
the signing key are independently controlled. With boot-ROM secure boot
disabled, someone with unrestricted eMMC access can replace the verifier.
The extra FIT key and build coupling were judged disproportionate here.
The board retains SHA-256 checks for accidental FIT corruption.

### Why signing-time validation is enabled

On a full power cut the hardware RTC lost a date that had been set and
verified while powered. On the final cold boot, the kernel read
`1970-01-02T00:00:05Z` from the RTC. Debian's system clock started in April
2026, earlier than the development chain's November 2026 validity start.
An earlier USB install passed after a manual clock correction. The project
cannot provide a clock that continues running through power loss.

The owner accepted `[keyring] use-bundle-signing-time=true`. RAUC 1.13 checks
the certificate chain at the CMS `signingTime`, a signed attribute supplied
by the signer. It still checks the configured CA, the code-signing purpose,
the bundle signature and verity payload integrity. A bundle can remain
installable after its certificate expires, and a compromised signer can
backdate new bundles. Treat expiry at installation as unavailable offline.
A release-version floor and removing a compromised key from the trust
policy address different risks. Neither measure is implemented here. NTP is
unnecessary for this install policy and could correct wall-clock time when
online. [RAUC 1.13 keyring reference](https://rauc.readthedocs.io/en/v1.13/reference.html#keyring-section)
and [verification source](https://github.com/rauc/rauc/blob/v1.13/src/signature.c#L1261).

### Offline cold-boot USB test (2026-11-21)

1. Booted A and wrote only the new EROFS image to inactive `root_b`. Read back
   the written image and verified the existing `boot_b` matched the bundle's
   boot image. Booted B, confirmed it loaded the read-only signing-time
   config, and checked that RAUC marked B good before allowing writes to A.
2. Copied `h713-v2-signing-time.raucb` to the FAT USB stick and verified its
   SHA-256 before power-off. Disabled the hotspot across the next boot and
   performed a full power cut. UART showed U-Boot booting B, the RTC reset,
   and USB mass storage enumerating. With NTP disabled, the device clock
   unadjusted and only loopback up, mounted the stick read-only and ran
   `rauc install /run/h713-rauc-stick/h713-v2-signing-time.raucb` over UART.
3. RAUC verified the development signer, installed directly from the stick
   to `root_a` and `boot_a`, and set `BOOT_ORDER=A B`. Raw read-back hashes
   matched both build inputs. A rebooted with the same signing-time setting
   and RAUC marked it good. Both slots had three attempts left. Restored the
   hotspot after checking A and left the USB stick unmounted.

The tested bundle was `2026.11.21.0842-9ac22e7d`, SHA-256
`355a4ebce6f6fe74220d578032f7e7e0b7efc34335fdd614ed9e25551da17717`.
Local bench evidence is under `build/rauc-signing-time-test/` in
`cold-boot.log`, `install-start.log`, `install-result.log`, `reboot-a.log`
and `validate-a.log`. The install was initiated over UART. Automatic
installation on stick insertion was outside this test.

### Wi-Fi and USB networking install tests (2026-11-21)

Transferred the same signed bundle over SSH on each link and checked its
SHA-256 on the projector before running `rauc install` on the staged file
in `/data`. For each install, the RAUC journal records successful signature
verification and writes to both inactive partitions. Before rebooting,
read back each target directly from eMMC and matched its SHA-256 to the
build image over the full image length.

| Transport | Started from | Inactive partitions verified on read-back | Result after reboot |
| --- | --- | --- | --- |
| Wi-Fi hotspot (`wlan0`, projector `192.168.4.1`) | A | `boot_b`, `root_b` | Booted B, and the boot-time RAUC service marked B good. |
| USB networking (CDC NCM, projector `usbdev0` at `192.168.7.1`) | B | `boot_a`, `root_a` | Booted A, and the boot-time RAUC service marked A good. |

The Wi-Fi test reboot enabled USB device mode for one boot. The second
reboot returned the USB port to host mode. Final state was slot A running,
both slots good, and the hotspot active. Local bench evidence is under
`build/rauc-network-test/` in the `wifi-*.log` and `usb-*.log` files,
including the route, install, RAUC journal and post-reboot checks.

### Power cut during an inactive-slot update (2026-11-21)

1. Started from known-good slot A and recorded SHA-256 hashes of the full
   `boot_a` and `root_a` partitions. Started installing the same signed
   bundle into B. RAUC set `BOOT_ORDER=A` and `BOOT_B_LEFT=0` before writing
   `root_b`.
2. Paused the RAUC daemon with `SIGSTOP` once the eMMC partition counter
   showed 75,497,472 bytes (72 MiB) of the 583,835,648-byte root image written.
   Cut physical power while the install was paused and before slot
   activation. The pause made the test repeatable with an operator. A cut
   while the eMMC is actively writing or while RAUC activates the slot
   remains to be tested.
3. After power returned, the projector booted A unattended. Both full
   slot-A partition hashes matched their pre-cut values. RAUC marked A
   good, and B still reported bad with zero attempts and remained out of
   the boot order.
4. Retried the same signed bundle from A. RAUC verified the signature,
   rewrote `boot_b` and `root_b`, and selected `BOOT_ORDER=B A`. Direct
   read-back SHA-256 checks matched both build images over their full image
   lengths before reboot. The projector booted B, and the boot-time
   mark-good service restored B to three attempts. Both slots reported good.

Local evidence in `build/rauc-power-cut-test/` includes
`partial-write-2.log`, `baseline-a.log`, `recovery-a.log`,
`retry-install.log`, and `retry-boot-check.log`. The first attempt finished
without a cut because its pause check expected B to remain in `BOOT_ORDER`
with zero attempts. The measured cut used the observed `BOOT_ORDER=A`.

## RAUC vs systemd-sysupdate: facts gathered

**RAUC (review snapshot).**
- Backends on master (`src/bootchooser.c`): `barebox`, `grub`, `uboot`, `efi`,
  `custom`, `noop`.
- There is no systemd-boot/BLS backend. One is proposed in
  [rauc/rauc#1367](https://github.com/rauc/rauc/pull/1367), open since March
  2024 and rebased in April 2026; its author calls it "currently untested",
  and the maintainer's question of how it interacts with systemd's Automatic
  Boot Assessment is unanswered.
- An efibootguard backend is also open,
  [rauc/rauc#1450](https://github.com/rauc/rauc/pull/1450).

**U-Boot 2026.07-rc5.**
- Bootmeths: extlinux, pxe, script, efi/efi_mgr, android, cros, qfw, vbe,
  rauc, sandbox. **There is no BLS Type 1 bootmeth.**
- extlinux can use generic boot counting:
  - `CONFIG_BOOTCOUNT_LIMIT` with `bootlimit` makes autoboot run `altbootcmd`;
  - extlinux.conf takes `fallback <label>`;
  - bootmeth_extlinux has a `fallback` option.

  But that is one counter, not one per slot, and no RAUC backend drives it.

**systemd-sysupdate.**
- It installs versioned images into the inactive partition of a pair,
  matched by partition type and label pattern, and can write boot entries
  with tries counters. Booting and rollback belong to systemd-boot
  (Automatic Boot Assessment) and `systemd-bless-boot`.
- The proposed systemd-boot Automatic Boot Assessment design needs U-Boot's
  UEFI loader, a FAT ESP, and systemd-boot. Sysupdate transfers images
  independently of boot selection. Retaining native U-Boot would need its
  own activation, retry and blessing integration.
- Debian trixie packaging: `systemd-sysupdate` is in `systemd-container`,
  `systemd-bless-boot` in `systemd-boot`, and `systemd-bootaa64.efi` in
  `systemd-boot-efi`. None are installed on the board.
- The current man page (systemd 262) says: "This component is experimental
  and subject to change at any given moment without notice." The 257 page
  has no such note. Components and transfer features are present in 257.
  The `acquire` command arrived in 260. Version 262 adds more component and
  feature management commands.
- `sysupdate.d`:
  - **Local sources** (`Type=regular-file` / `directory`, e.g. a USB stick)
    get "no integrity or authentication verification".
  - **HTTP sources** (`url-file` / `url-tar`) check `SHA256SUMS` and its
    detached GPG signature by default (`Verify=yes`, which can be turned off).
- These sysupdate facts come from documentation and package indexes only.
  Nothing was run.

**UEFI boot cost, measured on the projector 2026-11-20.**
- The same slot B kernel was booted through `bootefi` (the kernel's EFI
  stub) instead of `bootm`, from a variant `boot.scr`. systemd-boot itself
  was not involved. `EFI_LOADER` and `CMD_BOOTEFI` were already in the V2
  U-Boot, and `EFI_STUB` in the kernel.
- Five measured boots each with `tools/boot-timing.sh`:

  | path | U-Boot→login s | kernel s | userspace s | systemd total s |
  | --- | --- | --- | --- | --- |
  | bootm | 15.08 [14.10..15.50] | 2.34 [2.27..2.37] | 8.91 [8.76..9.17] | 11.25 |
  | bootefi | 14.92 [14.40..15.70] | 2.47 [2.44..2.52] | 9.24 [8.81..9.60] | 11.71 |

- Time to login is the same within noise. The kernel phase is about +0.13 s
  every time; userspace about +0.3 s with overlapping ranges.
- The EFI variant skipped the FIT's sha256 check, which flatters its U-Boot
  side.
- Memory reservations matched, and EFI runtime services came up.
- Not measured: systemd-boot itself (scanning the ESP, and one FAT rename
  per boot for the tries counter), and the display reservations under UEFI
  (V2 U-Boot does not draw the display yet).

## Remaining validation

- Test power cuts during active eMMC writes, redundant environment saves
  and slot activation. Verify unattended retry after a bootloader-stage
  failure, an early Linux hang and a product-service failure. The existing
  mark-good unit checks boot progress through systemd ordering. Product
  health gating remains open.
- Establish release signing, version-floor and key-rotation policy. Test
  fallback after the new slot has changed persistent state in the shared
  `/etc` and `/var` overlays.
- Revisit sysupdate if a pinned Debian build demonstrates authenticated
  offline USB installation and comparable power-cut recovery with a
  concrete maintenance advantage.
