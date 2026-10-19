# Stock audio PLL init-on-zero experiment

The previous metadata retry made stock SetAPLL run during playback, with
positive N/Fs history 6144/48000 and PLL +4 changing 3 -> 10. No capture DMA
bytes or interrupts occurred even with the verified DSP init and capture route.
PLL +c remained zero. Stock SetAPLL selects Init only for a negative +c word;
a nonnegative word selects Update. This motivates testing full stock init
when that word is completely zero, without guessing register contents.

## Offline execution and corrected interpretation

`tools/stock/decode-mips-audio-pll.py` executes the exact identity-pinned raw
MIPS firmware in Unicorn. It stubs only logger and byte read/write/masked-write
helpers; device accesses update a Python dictionary, never the board. Only
PLL 06880000..0688001b is allowed. All calculation/soft-float code runs from
firmware with inputs CTS=74250, N=6144, Fs=48000. All reads default to zero.
This is a zero-state model, not a hardware initialization or lock guarantee.

Direct stock Init (8b13bcb8) returns success in 5279 instructions, making 26
byte-helper writes. Final modeled words are +0=0d326667, +4=50001010,
+c=60180000, +10=3. Other mapped words remain zero. Full SetAPLL with the
one zero-selection change returns success and produces the same words.
Direct Update under this zero-state model reaches the 200000-instruction
limit in a hardware-handshake poll. Since the model has no device handshake,
this does not establish a live timeout or failure. Live +4=10 from the prior
trial shows a different behavior than that frozen model. emulation.json
preserves both successful and incomplete outcomes, without treating them as
hardware results.

**Correction:** bit31 is an Init-selection condition, not a setup-completion
flag. Stock full Init writes high control byte 0x40 then 0x60, clearing bit31.
The earlier interpretation of its absence as absent "setup bit" was wrong.
Zero +c remains observed, but lock and complete configuration are unproven.

The separate stock HDMI configuration routine 8b13ca0c calls full Init
unconditionally at 8b13ca8c after calculating a receiver rate-derived input.
This establishes an existing stock unconditional init path, but that broader
receiver routine is not invoked in this experiment. No wrapper/receiver ARM
MMIO or guessed PLL values are written.

## Candidate and validation

`make-audio-pll-init.py` retains the validated metadata retry, optimizes its
stack restoration into jump delay slots, and changes only SetAPLL's branch
at 8b13c628: bltz s0 (06000017) -> blez s0 (1a000017). Negative/nonzero control
words follow the original selection; zero additionally selects the existing
Init path. The original delay-slot store and all stock arguments, arithmetic,
register programming, hardware polls and return paths remain unchanged.
There is no live MIPS patch. Firmware and U-Boot identities, expected words,
cave ownership and the fixed 42-record/7-base/7-store census are checked.

4050 retry-path cases passed for zero/status/history guards, registers, stack,
delay slots, explicit DRAM reads and stack-only writes. Unicorn branch cases
verify zero is the only changed selection; positive 1/60180000/7fffffff and
negative 80000000/ffffffff retain original paths and delay stores. Full
SetAPLL offline execution also reaches and completes stock Init. Python
compilation and git diff --check pass. Hardware trial results are recorded below.

Original U-Boot at LBA4828160,1798 sectors/920576 bytes SHA256:
c882461d5ee69128c79d99b784fde668ee4d57ab09ae308738e3f9ea91fd1ce7.
Candidate SHA256:
3c2dd5d5208a23f1c4511c37b704a3d17e8a9bce29f16293dc8e768a7582660a.
180 bytes differ entirely within the same 672-byte table. Exact rollback is
uboot-before.bin. SPL LBA16/64 sectors is guarded by SHA256
cb9da87448a57aa1cafbc7ebf66200b5183304cef1eafe23d0818b99696a49ec.
Install/restore scripts verify complete preimages, fsync, full readback and
byte-identical SPL. Restore original U-Boot after the cold trial.

After verified temporary installation, physically power-cycle and stop at
U-Boot before first MIPS launch. Use guarded mips-comm-trace/source3 and
installed Linux, then verify-audio-pll-init.py. Earlier monitor readers do
not decode this functional profile. Stage exact-kernel modules/canonical
EDID explicitly and use lock-gated bounded playback. Read only the two
previously validated PLL registers via MIPS. Recovering DMA samples remains
the goal; a changed PLL word alone is insufficient. Preserve kernel/FIT,
SPL and user IR/suspend/poweroff changes.

## Completed hardware trial

Cold launch and source3 passed. All 42 profile records, magic and canaries
were verified. The original U-Boot was restored with full readback and
unchanged SPL before the capture trials (restored-and-profile.log).
Three lock-gated 720p/48k playback windows, including verified DSP initialization
and bridge routing, produced no DMA bytes or interrupts. PLL +4 stayed 10,
+c stayed zero; bridge buffer retained its a5 sentinel.

The stock informational log in logged/elog-hdmi.txt positively records full
Init with N=6144, Fs=48000, successful divider calculation and PowerUp.
A cached log-mode read can appear zero; absence of ring output alone was not
proof of disabled logging. Direct positive records establish Init execution.

MIPS scalar reads after cleanup showed +0=67,+10=3 as well as +4=10,+c=0.
Stock Init writes the fixed +0 bytes 0d,32,66,67. A simulated fault where every
byte store clears the aligned word and writes the low byte reproduces all
four observed values exactly. This is a byte-lane handling hypothesis, not
yet a verified hardware mechanism. The next experiment replaces only writes
to scalar PLL configuration words with aligned read-modify-word-write.
Capture remains unresolved. Diagnostic modules were unloaded and routes restored.

## Correction from scalar byte reads

The later cold PLL byte-read experiment (../2026-10-07-pll-byte-read) shows
aligned MIPS LW/regr does not provide a packed four-byte value for this bank.
With stock PLL byte stores, explicit four-byte LBU reads during playback yield
+0=0d320667,+4=50000010,+c=60180000,+10=3. Thus earlier +c=0/+0=67
word observations do not prove missing upper-byte configuration or collapsed
byte writes. That hypothesis is withdrawn. Stock full Init and PowerUp are
positively logged; physical PLL lock and capture success are still unproven.
