# Rebuilt production candidate — November 3, 2026

**Offline build/reproducibility PASS; hardware qualification pending.** No
board files, raw storage, services, environment or power state were changed.

Two separate work directories compiled the same complete proposed-source
snapshot without prepared kernel/module trees or historical installed bundles.
Both used the recorded host toolchain and signed Debian snapshot
`20261102T000000Z`, with source epoch `1793693083`. Kernel FIT, TF-A, SPL,
U-Boot proper, all five HDMI modules, boot archive, rootfs tar/ext4/sparse
images and complete release metadata matched byte-for-byte. Separately
generated 32 MiB FAT boot images also matched and passed `fsck.fat -n`.
This establishes repeatability on this host/toolchain; it is not a claim
about arbitrary host distributions or rebuilt Debian package sources.

The runtime image has 30 in-tree modules, three AIC8800 modules and five HDMI
modules. The production fragment disables the inherited AV1 probe and kernel
runtime-testing menu. The image omits board bench/probe bundles, Wi-Fi baseline
helper, Python regression suite, SPA test plugin, compilers/build headers,
debuggers, `v4l2-ctl`, test media and the retired GStreamer speaker consumer.
Runtime media tools, PipeWire, Python standard library, health checks,
SSH/UART/SysRq recovery, key handling and calibration are retained.

Validation: five release test groups, 11 startup generator tests, shell syntax,
Python compilation, whitespace checks, final payload checks (21 required / 12
forbidden paths plus suite/probe checks), all four bundle checksum manifests,
and full-image build comparison pass. The tightened payload gate correctly
rejects the superseded image that still contains the Wi-Fi bench helper.
Earlier full-image comparison found differences only in an APT cache and an
alternatives log; removing those transient build products yielded identical
final outputs.

[Machine-readable result and artifact hashes](RESULT.json),
[filesystem/image tool identities](host-image-tools.json),
[rebuild instructions](../../reproducible-production.md), and
[pending qualification/rollback gates](../../production-qualification-plan.md).

The private candidate is preserved under
`local/releases/h713-ddr3-production-20261103-candidate/`, with source snapshot,
source/gitlink locks, package versions, explicit private-input hashes,
verification logs and recursive package checksums. Full intermediate evidence
remains under `local/recovery/2026-11-03-reproducible-system/`. Images contain
private device configuration and must not be committed. The proposal is still
uncommitted; source tests and investigation history remain in the repository.
Installation, consistent offline rollback backup and hardware acceptance are
still pending. Neither matching bytes nor a shared kernel version qualifies
the new binaries on hardware.

## Commit preparation: source-input hygiene correction

A clean-checkout audit found five generated files in the original candidate's
source-lock inventory: four ignored Kbuild .mod.c files and the generated EDID
header. They are not authoritative inputs: Kbuild regenerates its module glue
and the release builder regenerates the EDID header from the tracked generator
and fixture. The module input enumeration now uses tracked source files for
both staging and locking, excluding these leftovers and untracked experiments.
A temporary clean-index fixture test proves that adding generated/experimental
files cannot alter the selected inputs. All actual required build sources are
in the commit. The original independent-build comparison remains unchanged;
no new full-image comparison is claimed for this source-enumeration correction.
The qualification attestation continues to identify the immutable tested bytes.
