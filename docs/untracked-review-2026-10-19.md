# Final untracked-file audit — October 19, 2026

Refreshed at `76b90b6`, after the cold-resume/DSP bring-up evidence commit.
**All 546 remaining untracked, non-ignored files are local-only. No unresolved
code or evidence commit was identified.** Their total size is 9,749,880 bytes.
All 546 match their original October 18 inventory hashes; there are no new or
changed historical inputs. Every path is under `docs/`, including six historical
C/header snapshots rather than unreviewed active module/tool source.

This audit document was excluded from the count while it was untracked. Its
separate documentation commit leaves the 546 local files untracked. The audit
did not execute historical scripts, access hardware/network, move/delete files,
change ignore rules or apply checkout-local excludes.

| Disposition | Files | Bytes | Decision |
| --- | ---: | ---: | --- |
| Originals with committed curated exports/snapshots | 369 | 5,535,127 | Keep local; do not commit duplicate originals |
| Explicit local dispositions in committed manifests | 158 | 2,837,463 | Keep local under the documented decisions |
| Remaining original local-research entries | 19 | 1,377,290 | Keep local snapshots/bookkeeping |
| Unresolved code/evidence candidates | 0 | 0 | No substantive follow-up identified |
| Total | 546 | 9,749,880 | All accounted for as local-only |

## Local originals and research

For every one of the 369 archived originals, its source hash matches a committed
curation manifest. The corresponding export is tracked and matches the recorded
export hash. These include original scripts/notes with non-executable snapshots,
raw logs with normalized text exports, and byte-identical copies mapped to a
single canonical export. Copies are not independent hardware trials. The five
October 18 raw per-trial serial logs are covered by
[support-files.json](hdmi-evidence/2026-10-18-panel-initial-state-trial/support-files.json).
The original October 17 notes, including two superseded drafts, also have
committed historical snapshots.

The 158 manifest-local files comprise:

- 49 broad repeated R-domain register sweeps.
- 32 earlier rail-cut/off-time exploratory captures.
- 25 generated research disassemblies.
- Seven duplicate raw continuous UART streams.
- One known garbled UART attempt with a usable later comparison retained.
- 44 empty companion stdout/stderr/log files, including the DSP command log.

Selected evidence and chronology already cover those exploratory captures.
Empty outputs do not imply failed or skipped commands. Do not promote these
files as new controlled trials or delete originals merely to quiet Git status.

The other 19 local-research files are six DSP completion `.c`/`.h` snapshots
and 13 serial offset/aggregate/process logs. Keep source snapshots for provenance
rather than creating alternate active implementations. Keep offsets and parent
captures together so exported trial excerpts remain traceable.

Committed disposition/provenance records are in the
[panel history](panel-investigation-history/manifest.json),
[audio tracing](audio-trace-diagnostics/manifest.json),
[retry/init](audio-pll-experiments/manifest.json),
[PLL access](pll-access-experiments/manifest.json),
[October 8 history](audio-oct8-history/manifest.json), and
[early audio/DSP history](audio-bringup-history/manifest.json) manifests, plus
the panel support manifest above. Their interpretation limits still apply.

## Cleanup completion

The earlier audit at `86c6701` counted 562 files: 501 local files and 61 evidence
candidates. Commit `76b90b6` resolved those 61 candidates with 54 unique exports,
six mapped duplicate originals and one empty command log retained locally.
Five already-local disassemblies were also recorded in that manifest.

Thirteen original JSON paths and three README paths became tracked, reducing
the untracked count by 16, from 562 to 546. Retained raw originals account for
the rest; the number of new exports is not the reduction in untracked paths.
The earlier five research disassemblies now have explicit manifest-local
entries, so the category totals have changed as well.

All planned tool/evidence groups from the original review are now handled.
There is no remaining substantive follow-up commit from this audit. Any later
local-file relocation or checkout-only exclusion is optional housekeeping and
must preserve provenance; none is necessary to complete the evidence cleanup.

## Ignore rules confirmed

Against the original 1,214-file inventory, `git check-ignore` still matches
exactly **155 files: 79 module build outputs and 76 raw-media files**. Existing
rules also cover generated `build/`, private `local/`, binary boot artifacts
and Python caches. Previously ignored trees were not exhaustively inventoried
or hashed and are outside the 546-file count.

Scoped probes confirm that module `.c`/Makefile files, Python tools and ordinary
`.log`, `.stderr`, `.json` and `.asm` evidence remain visible. Module `.ko`,
bench WAV, build-output and private-local probes are ignored. Tracked files
remain tracked regardless of ignore rules.

No additional shared `.gitignore` rule is needed. Do not add global ignores for
`.log`, `.txt`, `.json`, `.asm`, `.c`, `.h`, `.py` or `.stderr`; these can contain
useful future evidence or source. The local originals intentionally remain
visible in Git status under the current rules.

## Saved audit artifacts

The refreshed per-file inventory and category lists are local under
`build/untracked-review-2026-10-19-final/`, separate from the earlier snapshot:

- `inventory.json`: all 546 paths, sizes, hashes, original-inventory comparisons
  and matching manifest/export references.
- `archived-original.txt`, `documented-local.txt`, `local-research.txt`: the
  complete disposition lists.
- `needs-review.txt`: empty, confirming no unresolved evidence candidate.
- `ignore-check.json`: original-inventory ignore counts and scoped rule probes.
- `local-exclude-candidates.txt`: the exact 546 root-anchored paths for an optional
  reviewed checkout-only `.git/info/exclude` update; this proposal is unapplied.

The inventory SHA256 for this snapshot is
`21aed80d235e8c0eb7a5c8a9ff6d39f86b7f3ba7b5e439d5e41dca0ae00ea825`.
The older `build/untracked-review-2026-10-19/` snapshot remains intact. These
ignored audit artifacts are not substitutes for the committed evidence
manifests and should remain local. Only the review documents are included in
this final documentation commit.
