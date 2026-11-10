# Fresh read-only preflight and finalized migration package — October 30

**PASS. No installation, board files staged, service restart, environment save,
clock/latch change or reboot.** SSH ran Python from stdin with bytecode writes
disabled; raw storage was opened read-only. Backups were streamed directly to
private host files. Host UTC timestamps identify evidence; board wall time is
not trusted. New source/package/document work is uncommitted.

The DDR3 board remains on boot `7ca604ba-a805-4f0a-9bd4-2df936f50479`, the
same boot as the verified shutdown-guard update. eMMC CID is pinned privately;
the public record includes only its SHA-256. Capacity is 7,818,182,656 bytes,
logical sector size 512, Linux whole-user-area device `/dev/mmcblk0`.

## What was verified

- Both GPT headers and entry-array CRCs validate. Copies agree, reciprocal
  LBAs and partition bounds check, and all 27 populated entries agree with
  kernel partition geometry. Both planned writes and rescue are within
  partition 18, `empty`, which is unmounted and has no holders. The old active
  environment is inside `super`; it remains protected and untouched.
- Current proper FIT is 960817 bytes, padded to 1877 sectors. Its prefix and
  fresh full 2-MiB region exactly match the recorded installed diagnostic
  generation (`74b346e3…` full-region hash). Installed SPL is unchanged.
- Intended environment slot is still zero-filled. Active environment hash,
  valid CRC and accepted saved startup policy are unchanged. Fresh intended-slot
  preimage and 64-KiB margins on either side are backed up.
- Rescue FIT header gives 920169 bytes. Its full FIT hash is recorded alongside
  the known 1798-sector prefix and fresh surrounding 2-MiB region. The complete
  32-MiB boot FAT is byte-identical to the accepted audit snapshot, preserving
  the kernel, startup script and vendor display assets.
- All four installed HDMI bundle manifests pass. Fifty-six installed file and
  metadata pins, all six service states/start identities and restart counts
  pass a fresh live preview. Capture xruns and video rejects remain zero;
  GP6 is HDOK, GP7 zero, session ready and saved 40-ms calibration unchanged.
  HDMI has no source, so video remains inactive; this is not a media test.
- Mounted ext4 superblock reports `clean`, no recorded error count and no
  `EXT4-fs error` messages in this boot. Mounted `needs_recovery`/
  `orphan_present` flags are not an offline fsck result. No repair was attempted.

[RESULT.json](RESULT.json), [storage layout](storage-layout.json) and
[read-only live preview](live-preview-result.json) preserve public verdicts.
Raw captures, CID, environment and firmware remain in the ignored private
recovery directory; they are not included in this evidence folder.

## Final package and deployment guards

Durable private package directory:
`local/recovery/2026-10-30-uboot-migration-live/package/`.
Archive: `local/recovery/2026-10-30-uboot-migration-live/package.tar.gz`.
The previous offline-only package is retained as history.

The candidate is unchanged from the tested normal DDR3 build: 955665-byte FIT,
1867 sectors, written within the full 1877-sector old proper extent. BL31/DTB
remain exactly matched. Every rollback preimage and protected raw region now
comes from fresh collection. The finalized manifest replaces synthetic disk
markers with real GPT/SPL prefix, backup-GPT suffix, active environment, rescue,
proper tail, intended-slot margins and boot FAT (eight disjoint protected
ranges). Package tool hashes are bound into its manifest identity.

The prepared transaction has an explicit live `--device /dev/mmcblk0` mode.
Every live action requires the pinned `--expected-boot-id`; a write additionally
requires full manifest SHA-256 via `--confirm-write`. It checks model, CID,
user device/geometry, reserved-partition use, protected bytes, file metadata,
service/runtime generation, session, safe RTC nvmem latches and filesystem
health. Wrong boot/state requires recollection, not overriding a guard.
Preview opens read-only and does not create a journal. Fault injection is
refused in live mode. Actual live use still requires user authorization.

Install stages the unchanged environment first, then proper; rollback restores
proper before removing the new environment copy. Journal intent is durable
before writes, every write is flushed, and block readback uses direct I/O.
The final read-only stdin preview tested direct reads of both write preimages
on this board, without copying tools to it. No task write occurred. No reboot
is automated; hardware write/rollback and power-loss behavior are unqualified.
The current-boot pins also apply to Linux rollback: after a reboot, prepare a
new reviewed recovery generation. `RECOVERY.txt` includes the exact 1877-sector
FEL fallback, with raw-image/RAM hashes, device selection and protected-range
checks; that complete hardware procedure was not executed in this work.

## Validation and reproduction

Twenty fresh-preflight tests pass; 19 deliberate identity/storage/live-mode
faults are caught. Tests cover GPT corruption/disagreement, kernel geometry,
reserved ownership/use, changed boot/CID/device geometry, environment drift,
filesystem/latches, direct readback/short reads, explicit write confirmation
and hardware fault-injection refusal. Block readback command tests use mocks;
the separate live preflight verifies actual read-only direct I/O.

The delivered package passes 31 sparse-disk rehearsal cases and catches all
14 transaction mutations. These reuse the earlier transaction coverage with
fresh GPT/boot bytes and eight real protected ranges, including full boot FAT.
Every potentially nonzero byte outside the two transaction spans is compared;
rollback restores exact bytes. All image writes and injected failures occurred
on regular host fixtures. Prior source/panel build tests remain applicable:
[13 source cases, 11 panel cases and build provenance](../2026-10-30-uboot-migration/README.md).

```sh
python3 tools/hdmi/finalize-uboot-migration.py \
  --source build/uboot-migration-2026-10-30/package \
  --capture local/recovery/2026-10-30-uboot-migration-live/collection-final.tar \
  --output /new/private/package
python3 tools/hdmi/test-uboot-migration-live.py \
  --capture local/recovery/2026-10-30-uboot-migration-live/collection-final.tar \
  --package /new/private/package
python3 tools/hdmi/test-uboot-migration-live.py \
  --capture local/recovery/2026-10-30-uboot-migration-live/collection-final.tar \
  --package /new/private/package --mutations
python3 tools/hdmi/rehearse-uboot-migration.py \
  --package /new/private/package --work /new/host/rehearsal
python3 tools/hdmi/rehearse-uboot-migration.py \
  --package /new/private/package --work /new/host/mutations --mutations
```

Use new output/work directories. The collector is a read-only stdin tool;
do not re-run it as a deployment command or stage it on the board. Collected
archives are retained; generated sparse fixtures may be removed after saving
logs/results. The durable package and source/evidence snapshots are outside
the disposable build cache. Nothing has been committed or pushed.
