# PLL readback diagnostic: trial complete, exact U-Boot restored

The prior AudioMonitor trial proved valid MIPS N/Fs but yielded no DMA audio.
The live `regr 06880004` shell command returned only its echo/prompt. Firmware
disassembly shows why: handler 0x8b180128 tail-calls UART4 printf 0x8b15b304;
its callback writes directly to UART4, not the RTT ring. The missing value is
not evidence for a zero register or successful PLL setup. `help win` still
responded afterward.

The new profile changes that one successful-read tail call to the identical
printf ABI at 0x8b15b348, whose callback writes RTT up[0]. Register parsing,
address conversion, LW, format string, stack and return remain unchanged.
The input address must be the firmware physical address: `06880004` converts
to MIPS 0xbb880004. Do not substitute 01880004 or ARM-read receiver MMIO.

The AudioMonitor hook retains status/count/N/Fs witnesses, dropping only the
redundant audio-object pointer store to free one patch record. Its shortened
branches were retargeted. The table remains 42 records with seven relocation
bases and seven stores. Both original and shortened trampolines passed 500
simulated paths each, checking registers, stack, delay slots and DRAM accesses.
The generator checks exact firmware/installed U-Boot hashes and every original
patched word. Python compilation and git diff --check passed.

Under the user's existing authorization to temporarily install a diagnostic
and restore U-Boot, the candidate was installed and fully read back:

- U-Boot proper LBA 4828160 / 0x49ac00, 1798 sectors / 920576 bytes.
- Installed candidate SHA256
  `5bb6ad2b22840d658b7846d8b0678d4aa2f6b33b6d787a2d3e9e24ef3cc189cd`.
- Exact original/rollback SHA256
  `c882461d5ee69128c79d99b784fde668ee4d57ab09ae308738e3f9ea91fd1ce7`.
- SPL LBA16/64 sectors verified unchanged, SHA256
  `cb9da87448a57aa1cafbc7ebf66200b5183304cef1eafe23d0818b99696a49ec`.
- 181 changed bytes, entirely within the same 672-byte diagnostic table.

Candidate and rollback are saved here and on the board as
`/tmp/uboot-audio-regr.bin` and `/tmp/uboot-audio-regr-rollback.bin`.
`candidate-install.log` records the readback. The current running MIPS still
has the previous trace; do not use the new decoder until the cold-start launch.
Only HDMI power/EDID-clock probes remain loaded; the audio/TVFE probes are out.

The user has been asked to physically power-cycle and stop at U-Boot before
the first MIPS launch. Then use the established
`h713_disp mips-comm-trace 0x34`, source-3 commcall
`commcall eaf13de5 chan=0 pid=8b8f275c 3`, and `run bootcmd`.
Do not warm-relaunch MIPS from Linux. The new aligned DRAM-only decoder
`/root/hdmi-safe-trace/read-audio-regr-trace.py` and generator are staged.
After launch, verify the profile/canaries, confirm RTT `regr` output, and read
only documented PLL addresses during canonical lock-gated playback. Any
additional MMIO reads require firmware evidence that they are safe. Restore
the exact original U-Boot after the trial and verify the complete region/SPL.

## Hardware result

The user confirmed a physical cold start. MIPS firmware and source-3 transition
passed, then Linux held receiver power/clocks. The decoder verified every
profile instruction and both canaries. RTT regr output now works.

The first 15-second canonical 720p/stereo-48k trial completed with zero DMA
bytes changed and zero SPDI/bridge IRQs. The short 0.3-second read windows
produced delayed/interleaved shell replies, so they are retained as exploratory
evidence only. The first confirmation attempt refused snapshot 2 because the
loaded probe requires strictly increasing snapshot sequence numbers. No tone
was played in that refused attempt; the detector restored its state.

The confirmation retry used snapshots 12–15, reused the verified modules,
read only PLL +4/+c with two-second reply windows, and omitted the slow elog
dump. Playback, canonical EDID, 1280x720 receiver lock and cleanup passed.
Active snapshots 13 and 14 both saw uncached MIPS N=6144, Fs=48000,
current/previous status=16, dispatch count=2. Monitor count rose 7085->7945.
Each corresponding regr reply was complete, with no stale output:

| Firmware address | During playback | Meaning from stock code |
|---|---|---|
| 06880004 | 00000003 | bit 0 still set; PowerUp clears bit 0 |
| 0688000c | 00000000 | setup bit 31 absent; setup routine sets it |

The private 64-KiB DMA sentinel remains unchanged (FNV 62519dc5); SPDI and
bridge interrupts remain zero. This establishes PLL state incompatible with
the stock power-up/setup sequence while audio metadata is valid. It does not
prove which SetAPLL gate skipped programming, measure lock, or prove this is
the only capture blocker. Investigate status-change dispatch versus N/Fs
history next; do not force unknown PLL words from ARM.

`uboot-restored.log` verifies the exact original full U-Boot region and
unchanged SPL after the trial. `cleanup.log` verifies clean audio/TVFE probe
unload and responsive MIPS. The new diagnostic remains only in live MIPS RAM
until power cycle; installed U-Boot is original. No further cold start is
requested at this boundary.

The safe post-trial DRAM snapshot confirms each port's PLL base is 06880000.
The saved firmware's table at 8b22f0bc has slot +8 = 8b13c524 (SetAPLL),
confirming the monitor's status-change dispatch calls SetAPLL directly.
Thus the next question is whether that call occurs with N/Fs still zero,
or returns through its cached-history equality gate without programming.

## Later correction: PLL control bit interpretation

Offline execution on Oct 7 (../2026-10-07-pll-initialization) establishes that
full stock init finishes PLL +c with high byte 0x60, not bit31 set. SetAPLL
uses a negative word to select Init and a nonnegative word to select Update.
Thus the earlier phrase "setup bit31 absent" must not be read as a direct
completion or lock test. The actual observation +c=0 remains valid; the
recovered full-init sequence ends at a nonzero configuration. No hardware
PLL lock has been established by this correction.

## Correction from scalar byte reads

The later cold PLL byte-read experiment (../2026-10-07-pll-byte-read) shows
aligned MIPS LW/regr does not provide a packed four-byte value for this bank.
With stock PLL byte stores, explicit four-byte LBU reads during playback yield
+0=0d320667,+4=50000010,+c=60180000,+10=3. Thus earlier +c=0/+0=67
word observations do not prove missing upper-byte configuration or collapsed
byte writes. That hypothesis is withdrawn. Stock full Init and PowerUp are
positively logged; physical PLL lock and capture success are still unproven.
