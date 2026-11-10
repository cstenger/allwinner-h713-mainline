# Offline rollback backup — November 3, 2026

**Backup integrity PASS. No candidate installation or repartitioning.**

The complete 7,818,182,656-byte eMMC user area was copied while held in U-Boot
after a physical cold boot, with Linux never mounted during the session.
Two complete direct device reads matched every chunk and whole-image SHA-256:
`c79e110a8e1029a69b0ca5e7e93c2108cf0aed1cbd74c780245c7ad7f3f0095c`.
The host copy was independently hashed again before extraction/verification.
The separate 4 MiB boot0 and boot1 areas were captured before shutdown; they
are separate preliminary read-only captures, not part of the two-pass user-area
comparison. All private copies remain under
`local/recovery/2026-11-03-reproducible-system/maintenance-backup/`.

The fresh layout is 27 partitions in a 28-slot GPT: Linux p26 `linux` is
2.75 GiB and Android userdata p27 `UDISK` is about 1.88 GiB. Older instructions
that flash `UDISK` would overwrite Android on this board. Both GPT header CRCs
and entry arrays verify and agree. Protected boot/environment/rescue regions
match their pre-shutdown copies. Separate host rollback extents include the
Linux filesystem, boot FAT, SPL, U-Boot proper and current environment.

The saved Linux filesystem passes `e2fsck -fn`; 69 runtime file hashes and the
accepted kernel FIT pin match the pre-maintenance inventory. The existing boot
FAT has a dirty bit, root/boot-sector label mismatch and a malformed vendor
short filename. Its legacy BPB also has zero CHS geometry fields. These are
preserved, **not repaired**: `fsck.fat -n` left the copy unchanged. The FIT is
readable using mtools with its geometry check disabled and has the expected
SHA-256 `0877293b3a71b9ccd28c0f0ef9725752a86dffd243851a5213eb023cd3a51c70`.
This is a faithful rollback capture, not a claim that the existing FAT is clean.

USB export was initially rejected by automatic approval review because it was
writable without enforced read-only protection. The operator installed a
temporary root-owned host udev rule that sets every board block node read-only
and marks it ignored by UDisks. The guarded export was subsequently approved.
All 28 nodes were verified read-only and unmounted; desktop automount was
disabled. UDisks denied a backup descriptor before data copying, so the operator
granted a temporary **read-only** ACL on the identified USB disk. The successful
client used only `O_RDONLY|O_DIRECT`, with USB/capacity/GPT identity gates.

After verification, USB storage was exited with Ctrl-C. The board remains at
the U-Boot prompt with shared lamp/fan PB5 confirmed high. Its USB disk and ACL
are gone; original desktop automount/GVFS settings are restored. The operator
removed the root-owned temporary rule in `/run/udev/rules.d/` and reloaded udev;
its absence and the restored desktop settings were independently verified.
The read-only backup window and temporary host cleanup are complete.

[Machine-readable results](RESULT.json). Hardware recovery rehearsal and
[candidate qualification](../../production-qualification-plan.md) remain pending.
No environment save, repair, format, GPT change, commit or push occurred.
