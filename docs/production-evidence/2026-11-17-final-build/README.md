# Final production build — November 17, 2026

**Offline build/reproducibility PASS; hardware qualification pending.** No
board files, storage, services, environment or power state were changed.

Two clean clones of `cb939748` were built concurrently in separate work
directories, each with its own copy of the Debian package cache and the
Linux tarball, using the [documented workflow](../../reproducible-production.md):
signed snapshot `20261102T000000Z`, source epoch `1793693083`, clang/LLD
23.1.4 (the cached copy, not the host's 23.1.5). All 38 compared outputs
match byte for byte: kernel FIT, TF-A, SPL, U-Boot proper, combined U-Boot
image, kernel/U-Boot provenance, boot archive and boot files, rootfs
tar/ext4/sparse, source lock and release metadata. The 32 MiB FAT boot
images also match and pass `fsck.fat -n` (24 files).

| Output | SHA-256 |
| --- | --- |
| Kernel FIT | `966eba3c8b5d13cc14d92469810849c513d823d8eaa502e33bf53225c2453245` |
| SPL region | `a03a06c44c27d5a8f1e14e104e2861afbb9dfe9042dd5132c4d3460687185288` |
| U-Boot proper | `265d4062401994d51a078b593def0c337949a80f548b39fe8df73b56c8aa6a03` |
| BL31 | `837c439bfad535c8861195f8d24c99cf588121417233d106e618569fc9aa6bd6` |
| Boot FAT image | `ce65b838ad360042eda38ac4617f50b948000dc301a10de6aac4d65473594c9f` |
| Rootfs ext4 | `667235d3179f561cf3040536f70345ec0870819af555efd5680c62ccc8c7a0c5` |
| Rootfs sparse | `3cff7f7832daf67884de7aa1f4e68bc39e054b3538eacbdc86ee1ee11b368feb` |
| release.json | `4fed77bb567e0ebe8f58b564e33f569ec81f03a67c73ed06e2961c0f0cbf40ca` |

The image has 38 runtime modules (30 in-tree, three AIC8800, five HDMI) and
the lamp helper. Production payload checks pass (21 required / 12 forbidden
paths). Vendor inputs match all 30 pins in `config/production-vendor.json`;
private inputs (SSH key, calibration, hotspot) have the same hashes as the
November 3 candidate. BL31 is unchanged from November 3; SPL, proper, FIT
and rootfs are new.

## Two build fixes this run needed

- **`dd8437fc` — U-Boot 0007.** The host's OpenSSL 4.1.0 (upgraded
  2026-11-15) removed the ENGINE API that mkimage's signing code links, so
  both the FIT step and the board U-Boot stage failed. The images are
  unsigned; both H713 defconfigs and the tools-only build now turn off
  `TOOLS_LIBCRYPTO`/`TOOLS_KWBIMAGE`. From the same patched tree, SPL, proper
  and combined image are byte-identical with libcrypto on (OpenSSL 3.6.5)
  and off. The U-Boot version string carries a digest of the patch set, so
  any added patch changes it (`-h713-1f7d7a1a` → `-h713-32671ea3`).
- **`cb939748` — rootfs check quoting.** Two image checks added by
  `afd611a1` (11-09) used single quotes inside the single-quoted
  `bash -ceu '...'` block, so they failed on every image with no message.
  This was the first production build to reach them.

## What this does not establish

Repeatability on this host and toolchain only, not on other hosts. This
build's hashes are new and none of them is hardware-qualified; the November 3
attestation does not carry over. Deployment packet, rollback copies and
qualification on hardware follow the
[qualification plan](../../production-qualification-plan.md).

Private candidate and logs (not committed: images hold private device
configuration): `local/recovery/2026-11-17-final-build/work-A3` (candidate)
and `work-B3`, with `comparison-A3-B3.json` and build logs.
[Machine-readable result](RESULT.json).
