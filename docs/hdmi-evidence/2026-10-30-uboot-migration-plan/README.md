# Offline U-Boot migration planning — October 30, 2026

Prepared from `848339d`; no board contact or writes, firmware build, candidate
installation, reset, clock change or hardware test. Changes are uncommitted.

[Recovery plan and next implementation gate](../../uboot-environment-migration-2026-10-30.md).

Validation:

- `retained-input-check.json`: durable checkpoint checksums, retained current
  1877-sector diagnostic proper/FIT header, active environment hash/CRC and four
  audited startup-policy values, installed SPL backup and FEL rescue SPL pass.
  All 72 environment entries parse; their values are not emitted.
- `tests.txt`: seven host tests pass for valid/invalid environment data, saved
  policy drift, duplicate keys, blob identity, FIT header and observed address.
- `mutations.txt`: eight deliberate faults caught. These test the validation
  tool, not a U-Boot source correction or a storage transaction.

Commands:

```sh
python3 tools/hdmi/check-uboot-migration-inputs.py
python3 tools/hdmi/test-uboot-migration-inputs.py
python3 tools/hdmi/test-uboot-migration-inputs.py --mutations
```

The checker needs ignored host recovery inputs and fails if missing or changed;
it does not retrieve data from the board or reconstruct firmware. Raw recovery
archives/environment data remain local. No new source patch has entered the
shipping series. Fresh GPT/device/preimage checks, source fix/build, transaction
implementation/rehearsal and hardware approval/acceptance remain required.
