# MIPS audio monitor, readback and dispatch diagnostics

Reviewed October 19, 2026. These are historical October 7 diagnostics for the
board-B firmware and the exact capture-instrumented U-Boot image pinned below.
They are bench tools, with host-only image generation and guarded on-board
DRAM readers. No new hardware trial, installation or restoration was performed
in this cleanup. Metadata retry/init and PLL access-width experiments remain
separate follow-ups.

| Layer | Generator / matching reader in `tools/mips/` | Witness |
| --- | --- | --- |
| Monitor | `make-audio-monitor-trace.py` / `read-audio-monitor-trace.py` | Comparison count, status-change dispatch count, last observed status/N/Fs/audio pointer |
| RTT readback | `make-audio-regr-trace.py` / `read-audio-regr-trace.py` | Monitor without pointer witness; successful firmware `regr` printf redirected from UART4 to RTT |
| Dispatch latch | `make-audio-dispatch-trace.py` / `read-audio-dispatch-trace.py` | RTT readback plus N/Fs updated only on status-change dispatch |

The wrappers load private module instances and retain the monitor generator's
image guards. Each profile replaces the same 42 records / 672 bytes and keeps
the seven-base/seven-store relocation census. It removes the VIncap interrupt
mask counters while preserving CPU_COMM, source-3, canaries and panel traces.
The trampoline preserves the original comparison's delay slot, return paths,
registers and stack. It adds DRAM accesses; it does not program receiver MMIO.
The RTT redirect leaves the firmware register read itself unchanged.

## Offline generation

From the repository root, using separately retained private inputs:

```sh
python3 tools/mips/make-audio-monitor-trace.py /path/to/uboot-readback.bin /path/to/display.bin build/audio-monitor-new --candidate
```

Substitute the regr or dispatch generator for the other layers. Output must be
a new directory. All modes emit `audio-monitor-profile.json` and
`audio-monitor-table.bin`; the latter is table data, not a bootable image.
`--candidate` additionally emits a padded candidate, exact rollback image and
byte-change manifest. It does not access hardware or storage devices.

The firmware SHA256 is
`4380f1b3ed7b62aa50582e7cb16a87bdface1b4300578fe3631a416354da30ce`.
The first 920576 bytes of the U-Boot readback must hash to
`c882461d5ee69128c79d99b784fde668ee4d57ab09ae308738e3f9ea91fd1ce7`.
A full readback may contain a suffix; it is excluded from parsing and output.
The generator checks the bounded version-17 FIT, unique original table,
pristine firmware words, cave ownership, fixed table size and relocation
census before creating output. Candidate changes must stay within the table.

Private firmware, generated tables, boot images, rollback files, raw media and
full disassemblies stay local. Profiles retain every replacement record, so
candidate identity can be reproduced without committing binary inputs.

## On-board reader contract

Use the matching reader only after the corresponding diagnostic was loaded
at cold start and the source-3 startup completed. Deploy its generator chain
and `make-cap-irq-trace-uboot.py` beside it; these imports use only the Python
standard library and do not open devices. On the board, a single snapshot uses
`python3 read-audio-dispatch-trace.py`; `--watch 30 --interval 0.25` provides a
bounded watch (maximum 60 seconds).

The reader checks every relocated instruction, CPU_COMM magic and both
canaries before reporting fields. `/dev/mem` mappings use a writable protection
because ctypes requires a writable buffer, but the reader exposes only aligned
32-bit loads from explicit firmware/mailbox addresses. Receiver MMIO is not in
that allowlist. Mappings and the descriptor close on success or exceptions.
The reader does not issue firmware `regr` commands.

Snapshots are best-effort. The count-change flag can detect an update during
some reads; a clear flag does not establish atomicity. Dispatch count/N/Fs
witness entry into the status-change path, not SetAPLL completion, successful
PLL programming, physical lock or recovered PCM. The first monitor modes
sample N/Fs every call; only the dispatch reader names them `dispatch_n` and
`dispatch_sample_rate_hz`.

`install-audio-monitor-trace.py` always exits before any device access. The
first historical RAM-table write faulted on a read-only U-Boot mapping; mocked
guards did not establish hardware writability. The exact withdrawn prototype
is preserved as [text](withdrawn-ram-installer.py.txt). Historical flash/restore
scripts below are text records of already completed trials, not deployment
entry points or authorization for another installation.

## Historical evidence and interpretation

- [Cache/monitor baseline](../hdmi-evidence/2026-10-07-audio-monitor/README.md): positive firmware logs correct the inference that unchanged ARM snapshots meant SetAPLL never ran.
- [Monitor trace](../hdmi-evidence/2026-10-07-audio-monitor-trace/README.md): the monitor ran with valid N/Fs during absent DMA; the RAM write aborted, and the later temporary storage candidate was restored exactly.
- [RTT readback](../hdmi-evidence/2026-10-07-pll-readback/README.md): the printf redirect exposed complete register replies; the first short replies and a refused confirmation are retained with the successful retry.
- [Dispatch latch](../hdmi-evidence/2026-10-07-audio-dispatch/README.md): playback dispatches latched 0/0; a teardown dispatch latched 6144/48000. This supports a metadata/dispatch timing gap in those trials.

Later scalar-byte diagnostics corrected the interpretation of aligned PLL word
reads: they do not provide a packed four-byte value for that bank. Earlier
claims that +c=0 proved missing upper-byte programming are withdrawn. The raw
observations remain useful, with this correction. Neither these traces nor
the later correction proves PLL lock or PCM capture success. Full later PLL
experiment sources and evidence will be reviewed independently.

Each directory's `README.md` is the curated summary; `README.md.txt` preserves
the original evolving notes, including superseded next steps and claims.
Trial/installation scripts are non-executable `.py.txt` snapshots. Logs are
text-normalized without filtering lines: CRLF becomes LF, invalid UTF-8 and
remaining controls are escaped. [manifest.json](manifest.json) records original
and exported hashes plus explicit local-only dispositions. Exact source
backups remain under `build/audio-trace-review/originals/evidence/` locally.
Historical authorizations and restored states describe October 7 only.

## Validation

```sh
python3 tools/mips/test-audio-monitor-trace.py
python3 tools/mips/test-audio-dispatch-trace.py
python3 tools/mips/test-audio-trace-host.py
```

The first two run 1500 simulated MIPS paths including branch delay slots,
register/stack preservation, counters, latches and DRAM-only accesses. The host
suite uses synthetic FIT/firmware fixtures and anonymous memory with mocked
device calls: malformed input/pin/table guards, output overwrite refusal,
historical record identity, reader allowlists, verification failures and
resource cleanup. No `/dev/mem`, serial or board access occurs in these tests.

The cleanup also regenerated all three candidates with the locally retained
pinned inputs: full profiles and candidate hashes match the original records,
with 176/181/183 changed bytes respectively. [validation.json](validation.json)
records those results and recomputed watch counts. This is offline regression
validation, not another hardware pass.

Source and curated Markdown pass strict `git diff --check`. Historical text
exports retain 86 original whitespace diagnostics (serial prompts, boot logs
and two exact script snapshots); these are not silently rewritten. The full
evidence diff is checked with end-of-line/end-of-file whitespace warnings
disabled, while hashes verify the documented exports.
