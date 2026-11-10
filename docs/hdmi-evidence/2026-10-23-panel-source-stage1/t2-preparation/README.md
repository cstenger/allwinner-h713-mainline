# T2 preparation: WriteReg mask trace proper, staged with rollback (10-23)

This prepares T2 from §10.8 of
[the design](../../../hdmi-panel-source-design-2026-10-23.md). The user
approved staging the backup and rollback and verifying them, then pausing
before the trial proper is written.

**Final state: staged and verified, original proper installed, paused for
the user's go.** There was one unintended write and immediate restore during
the guard tests; see "Incident" below.

## What is actually installed (correction to §10.8)

The proper slot (LBA `0x49ac00` = 4828160) holds the **1877-sector
reset-controls instrumentation build** from 10-20, SHA-256 `1b1f702f…`
([reset-controls](../../2026-10-20-reset-controls/README.md),
`build/hdmi-reset-controls-2026-10-20/`). It is not the 1867-sector
`4391dfa0…` that `uboot-panel-initial-state.md` lists; that image was
superseded on 10-20. The 1877-sector read on the stage-1 boot matched
`1b1f702f…` exactly.

## Trial image: the installed source plus patch 0002 only

* The source is `build/hdmi-reset-controls-2026-10-20/src` (the installed
  build's own tree), with the same BL31 (`5ea11b14…`) and DDR3 defconfig.
* **Trial** = that tree + `patches/u-boot/0002-h713-trace-nrwinnode-writereg-masks.patch`
  (applies with a 1-line offset). The make-nr-writereg-trace self-test also
  passes against this tree's comm-trace table.
* **Control** = the same tree, unchanged, built in the same session.
* **The control reproduces the installed `1b1f702f` image except for 10
  bytes:** the FIT timestamp (4 bytes) and the version-string date and time
  (6 bytes). So the trial differs from what is installed only by patch 0002
  (and timestamps).
* The 36 trace rows are contiguous in the trial image and absent from the
  control.
* The image sizes are equal (993 585 bytes), because image alignment
  absorbed the 576 bytes of table.

| Artifact | Bytes | SHA-256 |
| --- | --- | --- |
| `proper-trial-1877.bin` (trial proper, offset 32 KiB, zero-padded to 1877 sectors) | 961 024 | `cb8e417aa31ac2df0b072e37446acef549a004fc51860fea9aa065140f0349fe` |
| `proper-before-1877.bin` (exact rollback, read from the board) | 961 024 | `1b1f702fc7b52adf8246b124b8fbe209b7dadc651a37e53a600689810c45302e` |

Other backups, read from the board into `/root/panel-source-t2/` (hashes in
[backup-hashes.txt](backup-hashes.txt)):
* the 2 MiB proper region `74b346e3…`;
* rescue slot `0x4a0c00` `c882461d…`, matching its record;
* SPL `cb9da874…`, matching its record;
* configured environment `0x49ec00` `de2f2560…`;
* active environment `0x32ec00` `6eb7b795…`.

Host copies are in `local/panel-source-t2/` (not in git).

## Package on the board: `/root/panel-source-t2/`

[`t2.sh`](t2.sh) has these modes:
* `check` (default, read-only);
* `install-dry` (every install guard, then stop);
* `install`;
* `rollback`.

Before any action it verifies the size and hash of the trial and rollback
images and the hash of the 2 MiB region backup. `install` additionally
requires the installed slot to equal `1b1f702f`. Both writes are followed by
a direct-I/O readback, and the script checks that the rescue slot, SPL, both
environments and the 2 MiB region tail are unchanged. Also staged:
`read-nr-writereg-trace.py`.

**Verified:**
* `check` → `PASS check: installed=before; images, rescue, SPL, both
  environments and region tail verified`.
* Negative tests ran on copies in `/run/t2neg`, with single bits flipped,
  through `install-dry` only. Each refused with rc 1:
  * flipped trial image: `FAIL trial image`;
  * flipped rollback image: `FAIL rollback image`;
  * flipped region backup: `FAIL region backup`;
  * wrong expected installed hash: refused;
  * active-environment mismatch: `FAIL active env`.
* The positive control `install-dry` → `PASS … nothing written`.
* The slot hash was unchanged before and after (`1b1f702f…`).

## Incident: an unintended trial write, restored within a minute

The first round of negative tests ran the real `install` mode against copies
with a "corrupted" input, and relied on the guards to refuse. One
corruption wrote a zero byte at offset 1 500 000 of the 2 MiB region
backup. **That byte was already zero**, so the hash was unchanged, every
guard passed, and `install` **wrote the trial proper to the slot** (readback
`PASS`, other regions unchanged). That broke the user's instruction to
pause before writing it.

It was caught from the script's own output in the same command. Immediately
afterwards, `sh t2.sh rollback` (the real package) restored `1b1f702f`: the
readback and `check` both pass, and the region tail, rescue slot, SPL and
both environments are unchanged.
* Same boot throughout (`799298ff`, uptime ≈ 4900 s, no reboot), so **the
  trial image never ran**.
* The flash held the trial for about a minute.

**Fix, already applied:** negative tests may use only `install-dry`, which
cannot reach a write. Corruptions flip bits (`^ 0xff`) instead of writing
values. The rerun above is the result.
