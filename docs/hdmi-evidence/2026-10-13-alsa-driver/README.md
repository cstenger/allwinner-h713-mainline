# First ALSA driver implementation, 2026-10-13

**Latest: real ALSA recording passed** for 48/32/44.1 kHz HDMI input,
with fixed 48 kHz stereo S16_LE capture. The three separate 16-second recordings
passed all acceptance checks with zero driver XRUNs. DSP graph restoration and
module cleanup also passed. See [attempt3](attempt3/README.md).

The original load/recording failures below are historical; both the early
AudIf access order and positive constraint-return handling are corrected.

The initial implementation session began with the board and computer freshly booted;
the board console showed Linux6.18.38 #1 (Oct7 18:57:16 PDT) and MIPS parked.
only read-only console checks were performed in that session. The later
user-stopped cold boot and first module staging/load are recorded separately
in the load-failure note. No listener was started or boot artifact changed.

The new [driver](../../../modules/hdmi-audio/README.md) registers capture-only
ALSA card H713HDMI at fixed48kHz stereoS16_LE, matching the successful rate
sweep. It derives clock/SPDI1/bridge setup from the proven bridge diagnostic,
adds actual DMA-position/period accounting and ALSA stream lifecycle, and
keeps receiver/DSP graph initialization as explicit guarded prerequisites.

`stock-pointer-start-stop.asm` preserves the exact stock pointer and flush
functions used for the implementation. Stock module SHA256:
65a8bdbbe9463aff2ae462a27fce3de1862a8039c52a22df2553fb6cd78794f5.
The literal pointer address is0x06148118; address-high register0x06142044.
The pointer register is an audio bridge status register, not receiver MMIO.

`build-manifest.json` identifies the compiled module, sources and dependencies.
The exact-kernel LLVM W=1 build completed without warnings. Native ring-math
checks passed. Synthetic recording-analysis checks passed valid stereo tones
and rejected silence, swapped channels, contaminated silence and wrong length.
The DSP helper rebuilt bit-identically to the successful graph-chain binary.

The original `build-manifest.json` describes the first build. The validated
module and source hashes are recorded in [attempt3/build-manifest.json](attempt3/build-manifest.json).
Automatic boot-time receiver/DSP setup and extended stability remain pending.
