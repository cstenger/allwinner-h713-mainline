# Release build of 4e1277b0 — November 18, 2026

**Offline build/reproducibility PASS.** This rebuilds the
[November 17 final build](../2026-11-17-final-build/README.md) with the three
changes qualified on the installed board since then:

- `h713-hdmi-readvertise.py` no longer gates HDMI re-advertising on the
  firmware's +5V flag (`b30239e7`; installation record items 13–15);
- `mips-shell.py` and `h713-mips-elog-level.service` confirm the firmware log
  level once a source sends, and the unit no longer holds boot (`db77be97`;
  items 16–17);
- the HDMI speaker delay is **0.115 s** (`4e1277b0`;
  [recalibration](../../hdmi-evidence/2026-11-18-avsync-recalibration/README.md)).

Two clean clones of `4e1277b0` were built concurrently in separate work
directories, each with its own Debian and source cache copies, with the same
pinned inputs as November 17: clang/LLD 23.1.4, signed Debian snapshot
`20261102T000000Z`, source epoch `1793693083`, all 30 vendor pins, and the
same SSH key, hotspot and keystone calibration. All **38** compared outputs
match byte for byte, and both 32 MiB boot FAT images match and pass
`fsck.fat -n` (24 files). Production payload checks pass; 38 runtime modules.

| Output | SHA-256 | vs 11-17 |
| --- | --- | --- |
| Kernel FIT | `966eba3c8b5d13cc14d92469810849c513d823d8eaa502e33bf53225c2453245` | same |
| SPL region | `a03a06c44c27d5a8f1e14e104e2861afbb9dfe9042dd5132c4d3460687185288` | same |
| U-Boot proper | `265d4062401994d51a078b593def0c337949a80f548b39fe8df73b56c8aa6a03` | same |
| Boot FAT image | `ce65b838ad360042eda38ac4617f50b948000dc301a10de6aac4d65473594c9f` | same |
| Rootfs ext4 | `7bc012311eaf4f38…` | new |
| Rootfs sparse | `ce6d5588098718c5…` | new |
| release.json | `bffe332942309871…` | new |

Full hashes are in [RESULT.json](RESULT.json). The changes are rootfs-only,
so the boot chain and boot partition are unchanged. Inside the rootfs the
three changed files match the source tree and the files installed on the
board (`31aa3177…`, `58b1183f…`, `002631aa…` in both unit locations) and
`/etc/default/h713-hdmi-speaker` holds `0.115`.

## Relation to the installed board

Every one of the candidate's 17,352 rootfs files was hashed on the board
(boot `55bced01`). Only two differ: `/etc/machine-id` (generated on first
boot) and `/usr/share/h713-release/calibration.json`, an informational copy
of the build calibration that nothing reads; the board's copy came with the
November 17 image and still records 0.040. The board therefore runs this
release's code and configuration, and the lifecycle, standby and A/V results
recorded on it since November 17 apply to these files. A fresh install of
this candidate would also replace that record file.

## Not established

Repeatability on this host and toolchain only. No installation of this exact
image was performed; its rootfs hash is new and unqualified as an image.
Private candidate (images hold private configuration, not committed):
`local/releases/h713-ddr3-production-20261118-candidate/`; builds and logs
under `local/recovery/2026-11-18-release-build/`.
