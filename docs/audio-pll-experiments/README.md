# MIPS audio metadata retry and PLL initialization experiments

Reviewed October 19, 2026. These functional bench experiments build on the
[monitor/readback/dispatch tools](../audio-trace-diagnostics/README.md). They
change firmware control flow and allow stock PLL register programming. They
are historical experiments, not validated production fixes. This cleanup ran
only offline checks; it did not access the board, install firmware or repeat
a hardware trial.

| Layer | Generator and verifier in `tools/mips/` | Behavior |
| --- | --- | --- |
| Metadata retry | `make-audio-pll-retry.py`, `verify-audio-pll-retry.py` | Preserve status-change dispatches; additionally dispatch for stable nonzero status when N/Fs are nonzero and differ from PLL history |
| Init-on-zero | `make-audio-pll-init.py`, `verify-audio-pll-init.py` | Retain retry; change stock SetAPLL's `bltz s0` to `blez s0`, selecting existing Init for zero as well as negative control words |

The retry trampoline reads the audio object's metadata/history and writes
only its saved scratch registers to the stack. The original hook delay slot
runs once, and registers/stack are restored before either original return
path. Stock SetAPLL owns PLL programming, history updates and hardware waits.
There is no added retry limit: if history never matches, future monitor calls
can retry. Unchanged zero status or zero metadata skips the added dispatch;
changed status retains its original behavior even with zero metadata.

Init-on-zero moves stack restoration into jump delay slots to free a patch
record. At `0x8b13c628` it changes `06000017` to `1a000017` and preserves the
original delay-slot store. Positive and negative nonzero words retain their
stock branch selection. These are statements about the word returned by the
firmware read, not proof of the physical PLL bank's complete state.

Both modes keep the RTT `regr` printf redirect, 42 records / 672 bytes and the
seven-base/seven-store relocation census. Neither publishes monitor fields:
`fields` is empty in their profiles. Use their verifiers, rather than earlier
monitor snapshot readers. Verification establishes code/magic/canary identity,
not PLL success or PCM capture.

## Offline generation and tests

From the repository root, with separately retained private inputs:

```sh
python3 tools/mips/make-audio-pll-retry.py /path/to/uboot-readback.bin /path/to/display.bin build/pll-retry-new --candidate
python3 tools/mips/make-audio-pll-init.py /path/to/uboot-readback.bin /path/to/display.bin build/pll-init-new --candidate
python3 tools/mips/test-audio-pll-retry.py
python3 tools/mips/test-audio-pll-init.py
python3 tools/mips/test-audio-trace-host.py
```

Generators use the preceding group's exact firmware/U-Boot pins, bounded FIT
parser, pristine-word/cave-ownership guards and fresh-output requirement.
They write host artifacts only. Outputs retain the shared names
`audio-monitor-profile.json`, `audio-monitor-table.bin` and, with `--candidate`,
a complete candidate, exact rollback image and change manifest. Table data is
not a bootable image. No installation entry point is added.

The retry test runs 4050 status/metadata/history/register cases. The init test
runs those same 4050 cases with its optimized returns, plus 212 stock/generated
branch executions checking all registers and the delay-slot store. Its branch
opcode comes from the generated record. The host suite covers both historical
profiles and synthetic candidate generation, verifier cleanup/help behavior,
and rejection of an unpinned model input. Init branch/model tests and the host
suite require Unicorn (tested here with 2.1.4); generators/verifiers and the
retry instruction simulator otherwise use the Python standard library.

The verifiers have `--help` and reject unknown arguments before opening
`/dev/mem`. After the corresponding cold-start diagnostic and source-3 launch,
run the matching verifier on the board with its generator chain, the monitor
reader and `make-cap-irq-trace-uboot.py` alongside it. It checks every relocated
instruction, CPU_COMM magic and both canaries using the preceding group's
aligned, allowlisted DRAM reader. Mappings close on success or failure. The
verifier performs no firmware shell commands or receiver MMIO reads.

## Stock PLL model

The supporting tracked model now takes an explicit private input:

```sh
python3 tools/stock/decode-mips-audio-pll.py /path/to/display.bin
```

It checks the board-B SHA256 with an explicit exception before emulation,
including under optimized Python. Importing it no longer reads private files
or runs emulation. The branch preimage is also checked explicitly. It executes
pinned firmware code in Unicorn, simulating byte helpers only inside the PLL
bank and replacing the logging helper. Reads default to zero and there is no
hardware handshake. The instruction limit remains 200000.

All four results reproduce the historical [emulation record](../hdmi-evidence/2026-10-07-pll-initialization/emulation.json):
direct Init returns after 5279 instructions; Update remains incomplete at the
instruction bound; modified SetAPLL completes Init after 5569 instructions;
the modeled collapsed-byte-store fault reproduces the earlier word readings.
The current output additionally includes `word_write_shim: false`, a field
already present in the tracked model before this cleanup. The collapsed-byte
case is a hypothetical fault model whose hardware interpretation was later
withdrawn. Model agreement is not evidence for that fault or for physical lock.

## Historical results and corrections

- [Metadata retry](../hdmi-evidence/2026-10-07-audio-pll-retry/README.md): positive history changes and changed register replies support stock SetAPLL running with valid metadata during playback. The DSP/bridge trial still recovered no DMA samples or IRQs.
- [Init-on-zero](../hdmi-evidence/2026-10-07-pll-initialization/README.md): positive firmware logs record full Init and PowerUp, but three playback windows still produced no DMA or IRQs. Exact original U-Boot/SPL restoration is recorded for both experiments.

Two later corrections limit the early interpretation. Bit 31 selects the
Init path; it is not a completion flag, and stock Init clears it. Scalar-byte
reads subsequently showed that aligned PLL word reads do not return packed
four-byte bank contents. Consequently +c=0/+0=67 did not prove collapsed byte
stores or missing upper-byte programming. Those hypotheses are withdrawn;
physical lock and successful capture remain unproven. The zero-word branch
experiment remains useful history without establishing a production need for
that change. PLL word-write/byte-read tooling and its evidence remain separate
follow-ups.

Each evidence directory has a curated `README.md` and an exact original
`README.md.txt`, including its superseded plans and interpretations. Trial,
install, restore and fixed-ring reader copies are non-executable `.py.txt`
snapshots, not reusable deployment tools. Historical approvals and restored
states refer to October 7 only. Private/generated binaries, raw DRAM dumps and
full disassemblies stay local. [manifest.json](manifest.json) records source
and exported hashes/dispositions; raw source backups remain under
`build/audio-pll-review/originals/evidence/` locally. Normalized logs preserve
all lines and trailing prompt whitespace while escaping control bytes.

[validation.json](validation.json) records offline checks and unchanged
candidate identities: retry changes 177 bytes, init-on-zero changes 180,
all within the original diagnostic table. Generated instructions and full
profiles remain identical to the historical ones. Source/curated Markdown
passes strict whitespace checks; exact historical text is checked with
end-of-line/end-of-file whitespace diagnostics disabled.
