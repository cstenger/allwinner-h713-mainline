# MIPS scalar PLL access experiments

Reviewed October 19, 2026. These cold-start bench experiments build on the
[metadata retry/init tools](../audio-pll-experiments/README.md). Their supporting
October 7 results are historical; this cleanup used offline builds, simulations
and evidence checks only. No board access, installation or new hardware trial
was performed.

| Mode | Source in `tools/mips/` | Scope |
| --- | --- | --- |
| Word-write | `audio-pll-word-write.S`, `make-audio-pll-word.py` | Replace stores in two stock helper epilogues with aligned read/modify/word-write for PLL offsets 0..7 and c..13 hex; other addresses retain byte stores |
| Byte-read | `audio-pll-byte-read.S`, `make-audio-pll-byte-read.py` | Replace firmware `regr` load only at exact PLL addresses BB880000/4/c/10 with four LBU loads packed into a word; retain stock PLL stores and other LW reads |

The word-write experiment tested a collapsed-byte-store hypothesis that was
later withdrawn. Its RMW assumes meaningful packed word reads; the later
byte-read result undermines that premise. It is not a production fix. The
byte-read shim is a read-width diagnostic, not a PLL-lock or capture test.
Both retain the functional metadata retry/init-on-zero layer and RTT printf
redirect; neither publishes monitor fields. They are alternative profiles,
not cumulative word-write plus byte-read changes.

Each candidate replaces the preceding 42-record table and nine progress-marker
groups (54 more records). The 96 records preserve both table extents, the
16-base/16-store census of the replacement records and the unchanged
61-base/80-store census of the checked ownership window (using `cap.census`).
The original notes quote a global 62/84 count; this cleanup records the
measured window and helper predicate rather than assuming that broader count. Nine progress markers are removed; CPU_COMM, source-3
return witnesses and canaries remain. The word shim preserves stock epilogues,
callee state, v0 and return behavior. The byte shim preserves the displaced a1
load and original return path and performs no stores.

## Reproducible host builds

From the repository root with private pinned inputs:

```sh
python3 tools/mips/make-audio-pll-word.py /path/to/uboot-readback.bin /path/to/display.bin build/pll-word-new
python3 tools/mips/make-audio-pll-byte-read.py /path/to/uboot-readback.bin /path/to/display.bin build/pll-byte-new
```

Build dependencies are Clang with MIPS support, `ld.lld`, and pyelftools. The
review used Clang/LLD 23.1.3 and pyelftools 0.33. `--clang` and `--linker` select
alternate executables. Each build uses a unique temporary directory, links at
0x8b100c50, checks the ELF layout and unresolved relocations, and requires an
exact reviewed shim hash. A compiler producing different bytes is refused.
The assembly sources are committed; prebuilt shim binaries are local outputs.

The generators inherit the exact firmware/U-Boot pins and initial-table guards.
They additionally validate marker/hook preimages, new cave words, address
ownership, second-table boundaries, record uniqueness and local/global
relocation census. These guards use exceptions and remain enabled with
optimized Python. Candidate changes must stay in the two fixed table ranges
[601380,602052) and [603476,604340). Only the pinned 920576-byte U-Boot prefix
participates; any suffix in a full readback is excluded.

Outputs require a new directory and include `shim.bin`,
`audio-monitor-profile.json`, `uboot-audio-monitor.bin`, `uboot-before.bin`, and
`candidate-manifest.json`. The rollback bytes come from the same validated
input read. The manifest records both change ranges, candidate/shim hashes and
`storage_modified: false`. These tools write host artifacts only; historical
installation/restore scripts are archived as text, not active entry points.

## Explicit on-board verification

Use the verifier matching the cold-start profile, passing its generated JSON:

```sh
python3 verify-audio-pll-word.py /path/to/audio-monitor-profile.json
python3 verify-audio-pll-byte-read.py /path/to/audio-monitor-profile.json
```

The missing implicit sibling-profile filenames are no longer used. Before
opening `/dev/mem`, each verifier validates record shape and pins, reconstructs
the shim from those records, checks its hash, and compares all 96 records with
the trusted generators. A supplied file cannot add arbitrary physical addresses
to the reader's allowlist. Wrong modes, changed words, addresses or metadata
fields are refused.

The shared aligned DRAM reader verifies all records, CPU_COMM magic and both
canaries; both t8 and k0 trace-base constants are compared after the loader's
AE34→AD98 relocation. It closes mappings and the descriptor on success or
failure. It reads neither PLL nor receiver MMIO and issues no firmware shell
commands. A matching profile confirms installed instruction identity, not
successful PLL initialization or PCM recovery.

The verifiers and generator imports require only Python's standard library;
ELF parsing/build dependencies load only during a build. Deploy the matching
verifiers, both access generators, init/retry/monitor generators, shared monitor
reader and `make-cap-irq-trace-uboot.py` together. The byte verifier also uses
`verify-audio-pll-word.py`. Hardware use presupposes the matching cold-start
experiment and source-3 startup; this document adds no installation workflow.

## Tests and preserved identities

```sh
python3 tools/mips/test-audio-pll-word.py /path/to/display.bin
python3 tools/mips/test-audio-pll-byte-read.py /path/to/display.bin
python3 tools/mips/test-audio-pll-access-host.py
python3 tools/mips/test-audio-trace-host.py
```

The first two require Unicorn (2.1.4 here), the build dependencies and explicit
private firmware. They check its identity, build the shim from source, and run
560 real stock-epilogue cases and 264 byte-load cases respectively. Importing
them performs no input reads or emulation. The host suite builds both shims but
uses synthetic FIT/firmware fixtures and mocked device mappings; it checks
second-table guards, immutable shim identity, fresh outputs, complete historical
profiles, wrong-mode/tampered-profile rejection before device access, both
relocations and verifier cleanup. Its nine tests also pass with optimized
Python. The shared host suite's 20 tests pass after the reader change.

Both complete historical profiles and candidates reproduce exactly:

| Mode | Shim bytes | Candidate SHA256 | Changed bytes |
| --- | ---: | --- | ---: |
| Word-write | 124 | `67d51b81b9e74d343a1b4c4e327dbc820c05a1cc14f5f0ff632c17ed764b5ddb` | 528 |
| Byte-read | 100 | `324543e16e3ef56e97011a5cdba563b08211ad4ba56fce05d4ce05f06568c37e` | 513 |

The full calculator model's baseline/fault/shim results also reproduce all
historical fields. Those dictionary-based fault/shim cases describe model
assumptions, not measured byte-lane hardware behavior.

## Evidence and limits

- [Word-write trial](../hdmi-evidence/2026-10-07-pll-word-access/README.md): the DSP completion timeout prevented a valid capture trial; two receiver-only windows and positive Init/PowerUp logs did not support the original byte-store fault hypothesis.
- [Byte-read trial](../hdmi-evidence/2026-10-07-pll-byte-read/README.md): packed scalar bytes showed configuration absent from aligned word replies, withdrawing the missing-upper-byte interpretation. Subsequent bridge/channel controls still returned unchanged DMA sentinels and zero IRQs.

Exact U-Boot/SPL restoration records are retained for both sessions. Positive
Init/PowerUp records establish execution; packed values do not prove physical
PLL lock. No successful PCM capture is established. Later DTV channel-selector
controls are archived as supporting session history, without promoting them
into new tooling or treating their model as a new validation result.

Original notes and trial/install/restore/helper scripts are exact non-executable
`.md.txt`/`.py.txt` snapshots, including superseded next steps. Curated
`README.md` files give the current interpretation. Normalized logs retain every
line and trailing prompt whitespace, escape controls/invalid UTF-8 and convert
CRLF to LF. [manifest.json](manifest.json) records original/export hashes and
local-only dispositions. Private/generated images, raw DRAM dumps and full
disassemblies remain local; exact source backups are under
`build/pll-access-review/originals/evidence/`. Historical approvals and restored
states refer to October 7 only. [validation.json](validation.json) records the
offline checks. Strict whitespace checks apply to active source and curated
Markdown; historical text checks preserve end-of-line/end-of-file whitespace.
