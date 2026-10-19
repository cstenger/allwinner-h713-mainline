# AudioMonitor dispatch-time N/Fs trace

Using the earlier explicit user authorization for temporary U-Boot tracing
followed by exact restoration. This profile retains monitor/status counters
and RTT regr output, but updates N/Fs only on a status-change PLL dispatch.
This distinguishes late valid metadata from the values seen by SetAPLL.
No receiver MMIO writes or functional firmware changes are introduced.

make-audio-dispatch-trace.py wraps the exact-image generator. It preserves42
records,672 table bytes, seven-base/seven-store relocation census and all
normal branch targets/registers/stack. test-audio-dispatch-trace.py passed500
randomized paths, including latched values unchanged when status is equal.
Reader verifies all42 instructions, trace magic and both canaries before
allowlisted aligned DRAM loads. It retains the exact RTT printf tail-call fix.

Original U-Boot padded920576 bytes/1798 sectors at LBA4828160:
c882461d5ee69128c79d99b784fde668ee4d57ab09ae308738e3f9ea91fd1ce7.
Candidateea5828f159fc6be1f40473804dea8f37430810d0629eb21b54ebea3bbb00f9cb.
183 bytes differ, all inside the original672-byte table. Exact rollback file
uboot-before.bin is retained here. install.log records complete pre-write
original/SPL hash checks, complete candidate readback and unchanged32-KiB SPL.
Host installer source is retained at/tmp/h713-install-dispatch.py.

## Completed cold-start result

The user physically power-cycled and stopped at U-Boot. The first MIPS launch
accepted the exact firmware identity, reached application readiness, and the
source-3 callback/worker completed with both event witnesses. The installed
Linux 6.18.38 #1 (Oct 7 18:57:16 PDT) booted unchanged. Exact-kernel receiver
modules and the canonical 256-byte audio EDID were explicitly staged.
Every trace instruction, mailbox magic and both canaries passed verification.

Two bounded 30-second HPD windows played an eight-second stereo 48-kHz tone
only after canonical EDID identity, dynamic HDMI PCM selection and 1280x720
receiver lock passed. Both detector trials exited 0 and restored peripheral
state with EDID mismatch 0. There was no DSP patch or DMA capture in these
windows: this experiment isolates firmware PLL dispatch timing.

| Window/event | Monitor calls | Dispatch count | Latched N / Fs |
|---|---:|---:|---:|
| First signal, stable audio status 16 | 116 onward | 1 | 0 / 0 |
| Second signal, tested audio-clock holds active | 3213 onward | 2 | 0 / 0 |
| Second signal removed, status 16 -> 0 | 6258 | 3 | 6144 / 48000 |

The second window used the previously validated stock-order TVFE hold and
AudioTop/IHB initialization. Across both windows 362 guarded DRAM snapshots
show the monitor running while the dispatch latch remains zero during active
playback. The only dispatch publishing valid N/Fs occurred on signal removal.
This is direct MIPS evidence that dispatch precedes valid metadata; it is no
longer inferred from potentially stale ARM reads of cached MIPS objects.
Those ARM cache snapshots still report Fs 0 and are not used to assert the
MIPS live Fs during playback.

Complete two-second RTT replies during both windows read PLL 06880004 as
00000003 and 0688000c as 00000000. After the valid-metadata teardown dispatch,
+4 changed to 00000010 while +c remained 00000000. Thus teardown did execute
a different PLL path, but this does not establish successful setup or lock.

Stock code dispatches SetAPLL only when audio status differs; its separate
N/Fs-history equality gate returns for initial 0/0. The evidence supports a
missed setup when metadata becomes valid after stable status. A future fix
should evaluate valid N/Fs versus PLL history while audio is present and call
the stock routine, with bounded timing and explicit provenance. Do not bypass
all status checks, force guessed PLL values, or live-patch MIPS. PCM recovery
and any additional capture blockers remain unverified.

## Restored board state

`restore.log` verifies the complete original 1798-sector U-Boot region SHA256
c882461d5ee69128c79d99b784fde668ee4d57ab09ae308738e3f9ea91fd1ce7 and byte-identical
SPL SHA256 cb9da87448a57aa1cafbc7ebf66200b5183304cef1eafe23d0818b99696a49ec.
The restoration happened after the first window; the trace remained in live
MIPS RAM for the confirming window without a relaunch or live code change.
`restore-script.py` records guarded preimage and full readback verification.

`cleanup.log` records temporary audio/TVFE probe unload and responsive MIPS.
Receiver power/EDID clock holds remain as before. Linux is running; the next
ordinary cold boot uses the original U-Boot. The installed kernel/FIT, SPL,
IR remote, suspend and poweroff work were not modified.

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
