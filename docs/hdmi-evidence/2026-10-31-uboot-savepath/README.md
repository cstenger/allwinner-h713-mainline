# U-Boot save-path preparation — October 31, 2026

**Later controller preparation:** the UART controller is complete and tested
offline, including probe/cleanup PTYs and fault injection. It is not armed;
the operator now reports the board off. No board action occurred during this
work. [Controller package, results and later execution procedure](uart-controller/README.md).
The powered-on backup/health state below records the earlier collection.

**PASS backups and offline checks. No native environment save, reboot, UART
transmission, latch change or source/configuration change was performed.**
Fresh read-only collection and health checks match current healthy warm boot
`b6849123-0398-4736-b06f-cfe25b19e593`; the host desktop remains active at
1280×720. Source and preparation changes are uncommitted.

[Review the complete protocol, boundaries and recovery plan](../../uboot-savepath-validation-2026-10-31.md).
[Machine-readable result](RESULT.json).

## Backups and packet

Fresh capture, exact migrated 64-KiB environment backup, immutable full storage
ranges and private identity are preserved under
`local/recovery/2026-10-31-uboot-savepath/`. Both environment copies are identical
with valid CRC and SHA-256 `6eb7b795…`; 72 entries, no test probe. Installed
proper and all originally protected ranges match; startup/filesystem/runtime
checks and all 56 file/metadata pins pass. Nothing was staged on the board.

Authoritative packet: `final-packet/` and `final-packet.tar.gz`. It pins one
mutable slot (LBA `0x49ec00`, 128 sectors) and nine protected ranges: the
original eight plus the now-immutable installed proper. It includes exact
environment-only recovery bytes, config/source/provenance, native-save and
semantic test tools, an offline checker and explicitly non-installable model
images. Earlier `packet/` is a development checkpoint, not the final packet.
Raw environment/firmware/CID are private, ignored and not in this evidence
folder. SHA256SUMS and durable source/validation archives identify the packet.

The source audit found the installed build supports `env save`, MMC, memory
compare, GPIO and `crc32`, but not `hash`, `env info` or `env load`. Do not use
unsupported commands from older recovery notes at the current prompt. New
environment-only recovery uses supported CRC32/compare plus host SHA-256 and
identity/protected-state checks. It preserves the migrated proper and old
environment in `super`; it does not apply the migration's zero-filled rollback.

## Offline validation

| Check | Result |
| --- | --- |
| Actual native save/address/export/device C routines, fake MMC | 8 cases pass |
| Native-save source mutations | 10 caught; every case fails under a relevant fault |
| Environment semantic/CRC/guard validator | 17 cases pass |
| Semantic-validator mutations | 15 caught |
| Full-geometry sparse host image | Probe and cleanup pass; all nine protected ranges and every potentially nonzero outside byte preserved |
| Deliberate wrong-slot/adjacent-margin model writes | Both caught; no hardware injection |

The native test compiles selected actual source routines from the installed
prepared tree, preserving the nonredundant 64-KiB layout. Fake device/block
callbacks write only regular temporary host files. The actual `env_export`
body computes CRC over 65532 data bytes; its hash-table serializer and MMC
initialization/switch callbacks are stubbed. This does not establish real
driver/cache/power-loss behavior. A short write remains a failure even when
unchanged zero padding would leave superficially valid bytes.

The checker rejects policy/bootdelay drift, duplicate/malformed/CRC-invalid
environments, wrong/preexisting probes, unexpected RAM variables, missing
reload evidence and incomplete cleanup. Only source-established
`fdtcontroladdr` initialization is allowed with a captured DRAM-range value.
It does not blanket-allow `filesize`/`ver`/boot changes. In particular, the
plan avoids GP7-stop `bootdelay=-1` and avoids `env export`'s `filesize` side
effect. Full private pre-save RAM snapshots must be validated before saving.

```sh
python3 tools/hdmi/prepare-uboot-savepath.py \
  --capture local/recovery/2026-10-31-uboot-savepath/read-only-backup.tar \
  --output /new/private/packet
python3 /new/private/packet/test-uboot-save-path.py \
  --packet /new/private/packet --mutations
python3 /new/private/packet/test-uboot-savepath-checks.py \
  --packet /new/private/packet \
  --capture local/recovery/2026-10-31-uboot-savepath/read-only-backup.tar
python3 /new/private/packet/test-uboot-savepath-checks.py \
  --packet /new/private/packet \
  --capture local/recovery/2026-10-31-uboot-savepath/read-only-backup.tar --mutations
```

Use a new output directory; nonce generation is unique per packet. The two
proposed hardware saves add and remove that nonce across two controlled warm
entries. UART controller/state/transport checks are now complete offline, as
recorded in the linked controller evidence. No controller has been deployed
or armed. Current evidence is preparation, not a hardware save-path PASS.
