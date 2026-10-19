# Cold-start stock PLL metadata retry experiment

The preceding dispatch-time trace found initial N/Fs 0/0 on audio appearance
and valid 6144/48000 only on teardown dispatch. During playback PLL +4=3,
+c=0. The next experiment makes the existing monitor retry its stock SetAPLL
call when valid metadata differs from stock PLL history while status is stable.

`tools/mips/make-audio-pll-retry.py` replaces only the same 672-byte diagnostic
table in exact original U-Boot. The firmware and complete U-Boot preimages,
all patched firmware words and cave ownership are checked. There remain 42
records with the same seven-base/seven-store relocation census. The seven
relocation bases/stores are unreachable padding, matching prior profiles.
The actual code stores only the two preserved scratch registers on the stack.
No ARM or trampoline writes to receiver MMIO, metadata or PLL history occur.

At the original branch 8b13a2f4:

- Changed status follows the original dispatch path at 8b13a2fc.
- Equal zero status follows the original skip path at 8b13a31c.
- Equal nonzero status also skips if either N or Fs is zero.
- Equal nonzero status with valid N/Fs compares audio +4/+8 against +30/+34.
  Both matching skips; either differing returns to the original dispatch path.
- The original dispatch passes PLL base and audio object to stock SetAPLL,
  which owns register programming and updates its normal history. The retry
  then stops once history matches. Its stock setup/update waits are unchanged.

Both temporary scratch registers, stack and all original registers are
preserved, including status v0 used by the stock status-byte store. Original
hook delay-slot addiu a1,s0,0x78 executes exactly once. RTT regr printf redirection
is retained for only the two previously validated PLL-register reads. This
profile publishes no monitor fields; use verify-audio-pll-retry.py, not a prior
trace snapshot decoder.

The instruction emulator passed 4,050 combinations of status, zero/valid N/Fs,
matching/differing history and randomized register contents, including branch
delay slots, exact return path, stack-only stores and explicit DRAM-load
allowlist. Python compilation and git diff --check passed. Hardware behavior
is still unverified. Do not treat this as a production firmware fix.

Original 1798-sector U-Boot at LBA4828160 SHA256:
c882461d5ee69128c79d99b784fde668ee4d57ab09ae308738e3f9ea91fd1ce7.
Candidate SHA256:
a253ac5e08d4b9fed8bbbd4fd38d679dc949fee714da3b809746f3c2364b6a5b.
177 changed bytes all within the existing table; FIT size and padding unchanged.
Exact rollback is uboot-before.bin. SPL LBA16/64 sectors must remain SHA256
cb9da87448a57aa1cafbc7ebf66200b5183304cef1eafe23d0818b99696a49ec.
Installation/restoration scripts guard the full preimage, then fsync and verify
all 1798 sectors plus byte-identical SPL. Restore exact original after trial.

The user power-cycled and stopped at original U-Boot. Linux was booted without
launching MIPS solely to stage this next temporary candidate. After verified
installation, physical power-cycle and stop at U-Boot again before first MIPS
launch. Never warm-relaunch or live-patch MIPS. Use the guarded source-3
procedure, then current installed Linux, exact-kernel modules, canonical audio
EDID, lock-gated bounded tone, and MIPS reads of PLL +4/+c. If PLL setup is
established, continue with separately verified DSP patch/route and bridge DMA
capture; do not infer PCM success from PLL register values alone.

The installed kernel/FIT, SPL, and user IR/suspend/poweroff work are preserved.

## Completed hardware result

The user physically cold-started at U-Boot. Exact firmware identity, MIPS
application readiness and source-3 callback/worker completion passed. The
unchanged installed Oct 7 18:57:16 Linux 6.18.38 booted. Original U-Boot was
restored before the live trial, with complete 1798-sector readback and
byte-identical SPL; see restored-and-profile.log. The candidate remained only
in live MIPS RAM. Its 42 instructions, mailbox magic and both canaries verified.

Exact-kernel receiver and stock-order audio holds were staged. Two canonical
256-byte EDID, 1280x720-lock-gated 30-second HPD windows played an eight-second
stereo 48-kHz tone. Both completed with exit 0 and restored EDID/peripheral
state. In the first window, complete RTT PLL replies during playback show:

| Address | Before retry (prior experiment) | With retry |
|---|---:|---:|
| 06880004 | 00000003 | 00000010 |
| 0688000c | 00000000 | 00000000 |

Positive ARM DRAM snapshots now show PLL history N=6144/Fs=48000 during the
active window. Other cached fields remain stale; do not infer live Fs=0 from
them. Together with the changed PLL register this supports stock SetAPLL
running with valid metadata during playback. This does not establish PLL lock.

The second window combined the retry with the exact previously tested DSP
module (fa8482d89ee0959ab5319c7ba45b5bbed21985fe93d7cfdc9fced00fff18bde7),
rebuilt from current source and the identity-pinned 724-pair stock patch.
Both DSP versions became 1. The capture selector, HDMI unmute and I2SIN1
interface enable were applied and read back using the verified helper.
The unchanged tested bridge module was then armed with private 64-KiB DMA.
Snapshots 2 and 3 during playback had zero changed DMA bytes (FNV 62519dc5),
zero SPDI IRQs and zero bridge IRQs. PLL reads remained +4=10, +c=0. No PCM
was recovered. Thus the metadata retry alone is insufficient even with the
previously verified DSP initialization and capture routing.

Further offline control-flow inspection sharpens the next boundary:
SetAPLL at 8b13c628 tests the sign of its PLL +c word. Nonnegative chooses
Update at 8b13c000; negative chooses Setup at 8b13bcb8. The measured zero
therefore chooses Update. The live retry does not change that choice. Find
the stock prerequisite that establishes the correct initial PLL configuration
before considering any setup-path change. Do not force guessed +c values or
infer a fully configured PLL from +4 alone. Relevant disassembly is retained
in pll-setup-update.asm and pll-powerup.asm, plus the earlier complete
SetAPLL disassembly in the audio-monitor evidence directory.

cleanup.log records final DMA/status snapshots, bridge IRQ/DMA release,
DSP route/interface/mute restoration with readback, probe unload and MIPS
liveness. The stock DSP patch remains volatile until power cycle; its route
was restored. Receiver power/EDID clock holds remain. Original U-Boot is on
storage, and the next cold boot clears this retry. Kernel/FIT, SPL and user
IR/suspend/poweroff changes remain unchanged. No further cold start is needed
at this boundary.
