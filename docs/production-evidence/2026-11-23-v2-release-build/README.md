# V2 release build — November 23, 2026

**Offline build and reproducibility: PASS.** `tools/release/build.py --board v2`
builds the HY200_QZ713_V2 projector release from source in one command. Two
builds from separate clean copies of the tree (main `3f6a0806` plus the
then-uncommitted `--board v2` change) produced identical slot
images, U-Boot, rootfs tar and release metadata. The only differences are the
signed RAUC bundle and the two files that record its hash. The production
payload check passes; the AV1 probe module is gone.

## Inputs

Same pins as the [November 18 A1 release](../2026-11-18-release-build/README.md):
clang/LLD 23.1.4, signed Debian snapshot `20261102T000000Z`, source epoch
`1793693083`, the same SSH key and hotspot configuration. Board-specific:

- **Vendor:** `config/production-vendor-v2.json`, the 10 Wi-Fi and HDMI DSP
  pins (same bytes as the A1 lock). Exported with
  `export-vendor.py --board v2`. The V2's display firmware and logo stay in
  its vendor partitions, which U-Boot reads.
- **Calibration:** `config/hy200-v2-calibration.json`: 0.115 s speaker delay
  ([V2 check](../../hdmi-evidence/2026-11-23-v2-avsync/README.md)),
  `"keystone": null` (not calibrated; no `/etc/h713-keystone.conf`).
- **RAUC keys:** `--rauc-keydir local/keys/rauc`, the development CA the V2's
  installed slots already trust, and its signer.
- **Kernel:** the `production` fragment, as on the A1. The plain defconfig
  built `sunxi-h713-av1-probe.ko`, which is why `verify_rootfs` rejected the
  hand-built V2 images.

## Result

| Output | SHA-256 | A = B |
| --- | --- | --- |
| EROFS root (`slot/root-lz4hc.erofs`, 582,852,608 B) | `17df69788ade947cdbe4e28c915f4aaebb9843994b09137f6f4bcb8819746b30` | yes |
| Slot boot image (`slot/boot.vfat`, 64 MiB) | `2b8e47ee7c736bc2f93f2b00a1bc55a4036078d56e489f237a2eaa5d33b61493` | yes |
| Kernel FIT (production) | `d40844681247aa8e3595e0f3af64871e51c4f25c1be2e82a05485a569a85806e` | yes |
| U-Boot proper | `8d5ad0b7e736633899a674d33faa7eb73450fa208e2f10baabcd466efdb40921` | yes |
| SPL region | `86b17102d2ed6d13aa6e2967b314a263a5bb0ff103d094185bbbeb6658bbd5a8` | yes |
| BL31 | `837c439bfad535c8861195f8d24c99cf588121417233d106e618569fc9aa6bd6` | yes |
| Rootfs tar | `73f6d19efc98735e5203b3745060b6a8bbceada8625cbfacaeda7694709c0b31` | yes |
| `release.json` | differs only in `rauc.bundle_sha256` | yes, apart from that |
| `h713-v2.raucb` (440,390,961 B) | A `4b3bd2e4…` | no (expected) |

All 17 compared outputs: [RESULT.json](RESULT.json). The bundle differs
because its CMS signature carries a signing time and the verity format uses a
random salt. `rauc info` on both bundles, against the CA, verifies the
signature (development signer), compatible `hy200-qz713-v2`, version
`2026.11.03.0804-6157269a`, and image checksums equal to the root and boot
image hashes above.

Checks on the candidate:

- `verify_rootfs --board v2`: PASS (21 required, 18 forbidden files). No
  `*probe*.ko`; 38 modules. No elog unit, keystone file or startup script.
  `/etc/default/h713-hdmi-speaker` holds `0.115`.
- The root trusts exactly the supplied CA and carries the V2 RAUC
  `system.conf` and preinit (`verify_v2_root`). `fsck.erofs` exits 0;
  `fsck.fat -n` on the boot image: 4 files.
- A first pair of builds stopped after signing on a path bug in the
  provenance step (fixed before the recorded run). Its root, boot image,
  rootfs tar and firmware already matched the recorded run byte for byte.

## Relation to the installed board

Not installed. This is a new image: the installed slots were hand-built from
`deb.debian.org` (not the snapshot) with the plain defconfig. Its U-Boot is
also a new binary: same source version (`h713-69ace3e4`) and DTB
(`8c4dc024…`) as the installed 0022, but the installed one was linked with
LLD 23.1.5 and has a different BL31 build time; this one uses the pinned
23.1.4. Installing either needs its own qualification and Chris's
go-ahead (eMMC writes). Builds and logs:
`local/recovery/2026-11-23-v2-release-build/`.
