# HDMI AudioMonitor trace: hardware trial complete, U-Boot restored

Both the uncached monitor trial and the correlated guarded DMA trial passed
their canonical EDID/720p lock and playback gates. The monitor runs at about
100 Hz and sees N=6144 / Fs=48000, proving that ARM's Fs=0 snapshot is stale.
Status-change dispatches occurred, but this trace does not capture N/Fs at the
exact dispatch or SetAPLL's result. Missing PLL log records remain inconclusive.
SPDI1 and Audio Bridge still produced zero interrupts and zero DMA samples.
The exact original U-Boot was restored and verified; the separate SPL hash
remains cb9da87448a57aa1cafbc7ebf66200b5183304cef1eafe23d0818b99696a49ec.
Audio/TVFE probes unloaded cleanly and MIPS remains responsive. Only the live
RAM firmware instrumentation remains until the next power cycle.

## RAM deployment failure and approved alternative

The user power-cycled the board and left it at the first U-Boot prompt. Exact
version, reset-zero, relocation address, and all 168 patch-table words passed.
The **first** `mw.l` then raised a synchronous permission abort: ESR 0x9600004f,
FAR 0x7ffa4bf0. U-Boot maps this data read-only. No RAM table write completed,
no MIPS launch occurred, and no storage was changed. The board automatically
reset and recovered to Linux. `uboot-overlay-install.log` records the failure;
`after-overlay-abort.log` confirms the Linux serial prompt.

The RAM installer is withdrawn and its command-line entry now refuses before
opening serial or making writes. The safe alternative is a temporary U-Boot
proper candidate, **approved by the user and installed with full readback verification**.
The exact rollback image is saved alongside it. The installed candidate readback matches
`ec277392463beced5b369baae973952397f2d4975c882f81f6923cb0485a5e6b`.
The board was rebooted to U-Boot, whose normal preboot logo initialization
launched and quiesced MIPS. After a further user-confirmed physical cold start,
`h713_disp mips-comm-trace 0x34` and the verified source-3 commcall passed.
Installed Linux then booted with the trace live. Exact rollback has completed;
`uboot-restored.log` and the later `bridge-cleanup.log` both verify the original
1798-sector U-Boot region as c882461d5ee69128c79d99b784fde668ee4d57ab09ae308738e3f9ea91fd1ce7.
MIPS must still be started only from U-Boot, never live from Linux.

## What is ready

The installed U-Boot proper was read from eMMC without writes. Its first
920576 bytes match SHA256
`c882461d5ee69128c79d99b784fde668ee4d57ab09ae308738e3f9ea91fd1ce7`.
The full readback remains `/tmp/h713-audio-trace-installed-uboot.bin`.
Board-B firmware SHA256 is
`4380f1b3ed7b62aa50582e7cb16a87bdface1b4300578fe3631a416354da30ce`.

`tools/mips/make-audio-monitor-trace.py` validates both hashes, the unique
42-record capture overlay, every pristine firmware word, cave ownership in
the selected patch table, equal table sizes, and the installed relocation
census. It produces the accompanying profile and 672-byte table. The table
is **data for a RAM overlay**, not a bootable image or an eMMC payload.

The FIT's U-Boot data starts at file offset 0x134. The replaced table starts
at offset 0x92d24, giving RAM offset **0x92bf0 from bdinfo's relocaddr**.
`tools/mips/install-audio-monitor-trace.py` derives the live RAM address from
bdinfo, checks the exact U-Boot version, requires MIPS reset register
0x0200160c to be zero, and compares all 168 original table words before its
first write. It writes only changed words in relocated U-Boot RAM and verifies
the whole replacement. It never launches MIPS, resets the core, changes the
environment, flashes storage, or modifies running firmware. The hardware
permission failure invalidates the RAM deployment method despite successful
mocked tests. Do not retry it or weaken MMU protection.

## Execution witness

Hook 0x8b13a2f4 replaces the monitor's status equality branch with a jump into
a verified zero-filled cave at 0x8b1004c0. The original `addiu a1,s0,0x78`
remains the hook's delay slot. The trampoline saves/restores t8/t9 and the
stack, logs only firmware audio-object fields and uncached mailbox words, then
reproduces the original equal/unequal return paths. No receiver MMIO is added.

The mailbox is physical 0x4d980000 / MIPS kseg1 0xad980000:

| Offset | Meaning |
|---|---|
| +0x100 | Monitor comparison count |
| +0x104 | Unequal-status dispatch count |
| +0x108 | Current receiver audio status seen by MIPS |
| +0x10c | Previous cached status seen by MIPS |
| +0x110 | N from the MIPS audio structure |
| +0x114 | Sample rate in Hz from that structure |
| +0x118 | Audio structure pointer |

An increasing monitor count with valid N/Fs and no new dispatch count would
confirm that the status-change condition is skipping the normal SetAPLL path.
A new dispatch establishes that control took that path, not PLL lock or
successful SetAPLL completion. A stopped count means the monitor comparison
is not being reached and needs further tracing. These counters are uncached;
last-observed fields are best-effort, not an atomic coherent struct snapshot.

The overlay temporarily removes VIncap IRQ-mask counters. CPU_COMM, source-3
handoff markers, canaries, and panel traces remain. No branch behavior or audio
register programming is intentionally changed. Additional tracing has timing
cost; this is a diagnostic experiment, not a production fix.

## Validation and next run

`tools/mips/test-audio-monitor-trace.py` executes the generated MIPS words with
real branch-delay-slot semantics across 500 equal/unequal status cases. It
checks branch destinations, every register, stack restoration, counters,
field values, DRAM-only accesses, canary avoidance, and unreachable relocation
padding. A mocked serial U-Boot test verifies full RAM overlay/readback and
refusal before writes for version/reset/table/truncated-read failures.
The decoded instructions are in `monitor-trampoline.asm`. Python syntax and
git diff --check pass. This has **not** been validated on hardware yet.

The candidate was generated with `--candidate`. It changes only 176 bytes in
the same 672-byte diagnostic table, at file offsets 601380–602037. FIT image
properties have no hash/signature nodes that require updating; code, BL31,
DTB, metadata, sector-tail bytes, and the separate SPL are byte-identical.
The full candidate and rollback files are each 920576 bytes / 1798 sectors:

- `uboot-audio-monitor.bin`: SHA256
  ec277392463beced5b369baae973952397f2d4975c882f81f6923cb0485a5e6b
- `uboot-before.bin`: SHA256
  c882461d5ee69128c79d99b784fde668ee4d57ab09ae308738e3f9ea91fd1ce7

`candidate-manifest.json` records the byte comparison. The exact installed
U-Boot region is mmcblk0 LBA 0x49ac00, 1798 sectors, matching the existing
validated capture-trace deployment. The user explicitly approved this temporary installation and exact rollback.
`candidate-install.log` records full matching readback.
After installation, verify the entire region against the candidate hash,
then physically power-cycle and enter U-Boot before the diagnostic launch. Use the
established `h713_disp mips-comm-trace 0x34`, source-3 commcall, and installed
Linux boot sequence. Once the trace test is complete, restore the exact
rollback image and verify the whole region again.

Linux tracing can use the staged
`/root/hdmi-safe-trace/read-audio-monitor-trace.py` with `--watch 30 --interval
0.25` during a lock-gated canonical EDID/stock-IO tone trial. The ordinary
firmware loader authenticates the firmware before applying the table and
flushes its firmware window before release. The reader verifies every new
instruction, trace magic, and both canaries before interpreting the mailbox;
it performs aligned allowlisted DRAM loads only. The generator and capture
helper are staged beside it.

The decoder refused the previous uninstrumented live firmware, and MIPS
answered `help win` before the user's subsequent power cycle. That refusal
is expected. After the U-Boot abort, the board is in Linux without a new MIPS
launch; no audio capture has been attempted in this state.

## Captured results and next boundary

An initial detection-only window used the old 128-byte fallback EDID that the
postboot preparer had staged. The native-720p playback guard correctly refused
the tone; the window restored cleanly. Its evidence is preserved under
`fallback-edid-no-tone/`. The complete SCP module was restaged and hashed
before the canonical retry.

The canonical monitor trial played two 8-second 48-kHz stereo tones. The
45-second uncached watch produced 181 samples. Monitor count rose from 3187
to 6361. Dispatch count rose from 0 to 5 during acquisition, then stayed 5
while MIPS saw N 6144/Fs 48000 and current/previous status 0x10/0x10. The first
samples at dispatch counts 2 and 4 still had N/Fs zero. Count 5 and valid N/Fs
first appear together in a 250-ms sample interval. Their exact order is
unresolved. Two reads observed a counter change during the read and are
explicitly flagged. `monitor-summary.json` retains all field transitions.

During the stage-4 Audio Bridge/SPDI1 trial, snapshot 2 saw monitor count 6865,
dispatch count 5, status/N/Fs zero. Snapshots 3–5 saw counts 7367, 7990, 8487,
dispatch count 6, status 0x10, N 6144, Fs 48000. The source completed the
12-second stereo tone with receiver state 5 at 1280x720/repeat 0. The DMA
sentinel remained unchanged (FNV-1a 62519dc5), and both owned IRQ counts stayed
zero through snapshot 6. The exact guarded module hashes match the preceding
validated builds. Evidence is in `bridge-monitor-*.json`, `bridge-probe-dmesg.log`,
`bridge-cleanup.log`, and the per-snapshot firmware logs.

This rules out a stopped AudioMonitor or permanently inactive port gate and
positively establishes firmware-side audio timing metadata during absent DMA
activity. It does **not** prove SetAPLL ran with valid metadata, completed
successfully, locked the PLL, or enabled receiver audio output. Next tracing
should freeze N/Fs at the actual dispatch or expose SetAPLL history/result
from MIPS, before changing the status condition or audio route. No functional
firmware fix or speculative receiver-register write has been applied.

Raw firmware dumps remain in /tmp with saved SHA256 manifests. The correlated
bridge dumps use the aligned-load-only fixed-window reader saved as
`aligned-elog-reader.py`, avoiding device-memory memcpy assumptions. Final
source output is disconnected/disabled. Only h713_hdmi_power and
h713_edid_clock remain loaded. Python syntax, 500 generated-instruction paths,
prototype guard tests, and git diff --check pass; mocked installer tests never
established permission to write the protected hardware mapping.
