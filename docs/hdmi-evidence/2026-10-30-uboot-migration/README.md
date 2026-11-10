# U-Boot offset fix and migration package — October 30, 2026

**PASS offline preparation and rehearsal. No board contact or installation.**
Requested work is uncommitted; base checkout is `848339d`. The normal U-Boot
series includes `0003-env-mmc-preserve-configured-offset-width.patch`; the
untracked `0002` diagnostic patch remains excluded.

The source correction preserves the configured `s64` environment offset when
DT `/config` or its property is absent/unreadable, keeping explicit signed DT
override behavior and existing partition/GUID precedence. The existing singular
environment-load message now includes the selected byte address, allowing
future UART evidence of `0x93d80000` without editing environment contents.
Both load and save continue using the common `mmc_get_env_addr()` path.
No environment save was performed or hardware-qualified.

## Candidate and retained identities

The normal DDR3 build succeeds; candidate proper FIT is **955665 bytes / 1867
sectors**. The package's proper write and exact rollback cover **1877 sectors /
961024 bytes**, including zeroing the ten-sector old diagnostic tail on install
and restoring its original bytes on rollback. The candidate extent SHA-256 is
`cbd29de888e4b605e68b98de78c081525dd7d1b627abca846704efe527e8802a`.

Extracted BL31 is `5ea11b14…` and DTB is `8361009b…`, both byte-identical to
the accepted diagnostic baseline. The panel source retains validated hash
`3c44fc5a…`; reset-trace instrumentation is absent. Effective Kconfig matches
the retained installed diagnostic build except compiler version 23.1.3 → 23.1.4.
The build has warnings in other U-Boot code; it is not claimed warning-clean.
See `build.txt`, `build.inputs`, `compiler.txt` and `config-difference.diff`.
Full hashes, geometry and limits are in [RESULT.json](RESULT.json).

The builder independently checks retained current proper, active environment
hash/CRC/startup-policy values, SPL and rescue inputs. It reconstructs the
historical current full 2-MiB proper region and verifies its recorded hash;
the package protects its tail, full retained rescue region, installed SPL and
old active environment. Historical full-region inputs are not fresh readbacks.

## Test results

| Check | Result |
| --- | --- |
| Compiled actual `mmc_offset()` / `mmc_get_env_addr()` source | 13 cases pass: absent node/property, overrides, relative offset, invalid sentinel, redundancy, named/GUID priority, boot hardware partition, non-OF behavior |
| Source mutation checks | 9 faulty variants caught; every source case fails under a relevant mutation |
| Existing panel initial-state harness | 11 cases pass |
| Sparse 7,818,182,656-byte image rehearsal | 29 cases pass |
| Migration mutation checks | 14 faulty variants caught |

Migration rehearsal covers environment-first install, proper-first rollback,
read-only preview, no-op repetition, loss after preparation/each phase, partial
and short writes, readback corruption, loss during rollback and retry. It
rejects protected-range/preimage drift, wrong capacity, corrupt payloads,
overlapping ranges, missing/wrong package or wrong image journals, writes
outside durable intent, concurrent transactions, symlinks, device inputs and
implicit actions. Sparse extent comparisons check **all potentially nonzero
bytes** outside the two write ranges and exact restoration after rollback,
including unrelated gap sentinels. No real disk or fault injection was used.

## Package, recovery and reproduction

Final private package: `build/uboot-migration-2026-10-30/package/`.
Durable private archive: `local/recovery/2026-10-30-uboot-migration/package.tar.gz`.
It contains candidate/rollback payloads, the unchanged active environment,
intended-slot preimage, protected-region fixtures, manifest/hashes/provenance,
host-only transaction/rehearsal tools and identity-specific `RECOVERY.txt`.
Raw environment/firmware files and archives remain ignored and local-only.

The transaction engine refuses block devices and only operates on explicit
regular host image files. The fixture identity markers are synthetic, not a
live GPT or eMMC CID. Image inode/capacity and journal package identity bind
recovery; intent is fsynced before writes, each write is flushed/read back,
and protected ranges are rechecked. Partial proper writes still require
recovery; two-component writes are not physically atomic. No boot/reset is
automated. Interrupted host writes are simulated; real power-loss/storage
semantics and the full hardware recovery procedure remain unqualified.

```sh
JOBS=8 tools/build/build.sh uboot
UBOOT_TREE=$(tools/build/build.sh uboot-tree)
python3 patches/u-boot/tests/test-mmc-env-offset.py "$UBOOT_TREE/env/mmc.c" --mutations
python3 patches/u-boot/tests/test-panel-initial-state.py \
  "$UBOOT_TREE/arch/arm/mach-sunxi/h713_mips.c" /new/panel-test-output
python3 tools/hdmi/build-uboot-migration.py /new/private/package
python3 tools/hdmi/rehearse-uboot-migration.py \
  --package /new/private/package --work /new/private/rehearsal
python3 tools/hdmi/rehearse-uboot-migration.py \
  --package /new/private/package --work /new/private/mutations --mutations
```

Use new output/work directories. A new build may change timestamp/banner
hashes; the builder records actual outputs and verifies its input provenance.
Completed sparse disk fixtures may be deleted after saving their logs/results;
the package and scripts reproduce them. Preserve the private recovery archive.

## Remaining deployment gate

Read the [migration/recovery plan](../../uboot-environment-migration-2026-10-30.md).
Fresh read-only identity, CID, capacity, sector size, user hardware partition,
GPT ownership/hashes, boot ID, proper/tail, both environments, SPL/rescue, boot
assets and filesystem/HDMI health must precede final package generation and
deployment review. Live collection/finalization and a block-device installer
are **not included** in this offline package. Do not deploy the new proper alone,
run `saveenv`, erase the old environment in `super`, overwrite SPL/rescue, or
use older 1798/1867-sector rollback recipes. Explicit installation approval
and the operator's cold/warm video/audio acceptance remain separate steps.
