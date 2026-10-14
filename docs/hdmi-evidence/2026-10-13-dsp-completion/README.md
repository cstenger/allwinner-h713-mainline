# DSP completion investigation, 2026-10-13

**Latest: [attempt3](attempt3/README.md) passed24 full graph cycles and three
real ALSA captures with stock completion handling. The helper now defaults to
stock busy-clear/request/done-set. Graph restoration and module cleanup passed;
MIPS responds. No recovery is pending.**

Historical first experiment: **Live continuous-poll test failed; a revised command-boundary test is built
but has not run. Physical cold boot is required before further DSP commands.**

The user cold-cycled the board and manually stopped at U-Boot. The guarded
single MIPS launch, current channel PID, source3 worker/canaries, preserved FIT
and RAM-only IRQ correction all verified. Linux6.18.38 and MIPS responsiveness
verified. No persistent boot artifacts changed and no listener was started.

## Tested diagnostic

The optional `dense_clear_poll=1` removes deliberate delays while observing
the completion clear edge. It retains clear-then-set, the failure latch, stock
ownership and bounded waits; IRQs remain disabled only for the initial100-us
window. Default behavior remains unchanged. Counters distinguish fast clear,
slow clear and clear timeout. The native test exercises the actual helper
against short clear pulses, sticky completion, delayed device1 completion and
slow MMIO with an elapsed-time bound.

[Build manifest](build-manifest.json) identifies tested module SHA256
5d60fff8858e0ebf8fd925420c7b1b689691c9c3986d5d2336feb3c88f716e66.
`tested-probe.c`, `tested-completion.h` and `tested-dsp-read.asm` preserve its
source and compiled command sequence. The exact-kernel LLVM W=1 build passed.

Both cold DSP versions read0/0. The guarded patch entry re-read versions, then
read clock word00ee and issued the stock masked clock-setting write. Its
readback failed at completion-clear after50,100us, status00000120. Five prior
reads observed clear in the fast window; the next read required the slow
window and timed out. **No724-pair patch data was sent and no graph was applied.**
See [failure](failure.log). No additional DSP request was issued afterward.

[Cleanup](cleanup.log) confirms DSP/ALSA/TVFE diagnostics removed, peripheral
state restored and MIPS responding. Receiver power/EDID holds remain. The
partially applied stock clock setting requires physical cold boot before a
new diagnostic. No failure latch was bypassed.

This failure does not establish whether the DSP failed to complete or the
observer missed a short clear edge. It also does not prove that continuous
polling is ineffective: compiled inspection found a `ktime_get` call between
the command write and first status read in this first experiment.

## Next prepared test

The revised dense path calculates its deadline **before** publishing the
command. [Next disassembly](next-dsp-read.asm) confirms no function call between
the command write at050c and first status read at0514. The actual helper's
native control also checks that its precomputed-deadline path reads MMIO before
calling the clock. On failure, the revised probe records the raw command/response
port as evidence only; it never accepts that value without completion or
issues a recovery command.

[Next build](next-build-manifest.json) is retained at host
`build/hdmi-dsp-completion-boundary`. It passed LLVM W=1 and
[next offline checks](next-offline-test.log), but **has no hardware validation**.
A new physical cold boot is required. Do not deploy it as an automatic driver
or infer that it resolves the restore timeout.

The exact [stock read routine](stock-dsp-read.asm) waits busy-clear, writes the
request, then waits done-set up to49999us. It does not require seeing done-clear.
The stock binary hash remains65a8bdbbe9463aff2ae462a27fce3de1862a8039c52a22df2553fb6cd78794f5.
The diagnostic's extra freshness check is still preserved pending evidence
about command-boundary behavior.
