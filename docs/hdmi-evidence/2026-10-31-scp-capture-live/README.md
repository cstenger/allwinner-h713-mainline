# One guarded live SCP capture — October 31, 2026

**PASS: exactly one capture completed and fresh read-only verification passed.**
The companion remains loaded with its owner-stop mutex held; the SRAM guard and
scratch remain resident. Preservation was not released. Do not repeat capture,
unload either module, restore the preimage or reset as a cleanup action.

[Verified result](RESULT.json), [sampled words](registers.json),
[handoff comparison](handoff-comparison.json), [event summary](events.jsonl), and
[consumed-attempt record](LIVE-ATTEMPT-CONSUMED.json).
The [sealed preparation packet](../2026-10-31-scp-capture-v2/README.md) is a
historical preparation checkpoint and was not modified by execution.

## Execution and verification

The user explicitly authorized one guarded live capture. The working package
was compared byte-for-byte with its checksum-verified sealed archive. The
driver then checked current host no-EDID/disconnected state, board identity and
boot, kernel/owner builds, all 56 installed-file/metadata pins and the complete
SRAM preimage. It durably saved the preimage on the host before loading the
inert matching-kernel companion through a memfd, and durably recorded capture
intent before sending one trigger. No persistent board file was installed.

The capture reached `CAPTURED_HELD` (`status=8`, `reason=0`). Bootstrap and monitor
both observed SR `0x00008001`. All 14 receiver loads completed; the fresh
post-data challenge echo passed. The original entry word was restored, the
SRAM-only guard and monitor fragments remained exact, owner stop/error/exception
markers stayed clear, and all SRAM outside the permitted resident regions
matched the preimage. Host and remote stderr are empty.

A separate read-only observation checked the companion's own status/result,
SRAM, boot/build identity, board signal and all 56 file pins. Its SRAM was
byte-identical to the saved capture. Board signal remains `none`; host HDMI
remains disconnected/disabled with zero EDID. The boot is unchanged:
`2d8c3970-4164-4a38-8e86-375bb440c971`.

No retry, release, unload, reseat, HPD pulse, service restart, SCP reset, board
reboot or UART transmission occurred. Original signal-owner parameter reads
and ordinary startup checking were deliberately avoided after capture because
they block on the retained owner mutex.

## What the sample establishes

All 11 words with corresponding original handoff records still match those
records. The HPD control word reads zero, the DDC-enable word reads
`0x07000007`, and the programmed timing/configuration words match handoff.
These are register values; they do not measure the external HPD voltage or
establish that the host has detected the sink.

The six sampled EDID-bank words read zero. Crucially, the first word of each
bank was already recorded as zero in the original post-enable handoff frame.
The retained SRAM EDID payload still has its correct header and valid checksums;
the original pre-enable bank verification/first-word records remain intact.
The live zeros therefore do not establish EDID loss. Their access-mode or
hardware meaning remains unresolved; no register setting was changed to test it.

## Retained endpoint

The one-shot attempt is consumed. Use the companion's own read-only status/result
or saved evidence for analysis. The owner mutex, helper self-reference, guard
and scratch stay resident. A later separately authorized release would end
preservation and may unblock a queued owner stop; it was not requested or run.
U-Boot save-path validation remains on hold.

Private raw events, before/after SRAM, authorization, driver/SSH logs and the
post-check are under `local/recovery/2026-10-31-scp-capture-v2/live-01/`, with an
adjacent sealed evidence archive. The prepared package and rejected first
prototype retain their original checksums.
