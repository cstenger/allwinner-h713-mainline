# Metadata retry experiment — October 7, 2026

Historical evidence, curated October 19. The
[profile](audio-monitor-profile.json) adds stock SetAPLL dispatch for stable
nonzero audio status with valid N/Fs differing from stock PLL history. It
preserves every original status-change dispatch, RTT read output and the
fixed patch-table census. It publishes no monitor telemetry. This functional
experiment is not a production firmware fix.

The candidate changed 177 bytes within the 672-byte table; see
[candidate-manifest.json](candidate-manifest.json).
[restored-and-profile.log.txt](restored-and-profile.log.txt) records the exact
original U-Boot hash, unchanged SPL and matching live retry profile. Restoration
preceded the live trials; the experiment remained in MIPS RAM for that session.

Two canonical 720p/stereo-48k windows completed playback. The first retained
positive cached PLL history N=6144/Fs=48000 and complete PLL word replies,
supporting stock SetAPLL execution with valid metadata. Cached zero fields
and missing log messages cannot prove non-execution. The second window added
the previously tested DSP initialization/capture route and bridge module:
[capture/trial-summary.log.txt](capture/trial-summary.log.txt) and
[capture/dmesg-active.log.txt](capture/dmesg-active.log.txt) retain unchanged
64-KiB DMA sentinel data and zero SPDI/bridge IRQs. No PCM was recovered.
[cleanup.log.txt](cleanup.log.txt) records resource/route restoration and
responsive MIPS.

**Later correction:** aligned PLL word replies +4=10/+c=0 do not describe all
four bytes of each bank word. Subsequent scalar byte reads invalidated claims
that +c=0 proved missing upper-byte programming or collapsed byte stores.
Bit 31 is also an Init-selection condition, not a completion flag. These
trials do not establish physical PLL lock or the complete cause of absent
DMA. The following [init-on-zero experiment](../2026-10-07-pll-initialization/README.md)
is historical investigation of that earlier hypothesis.

[README.md.txt](README.md.txt) preserves the original evolving notes, including
superseded pre-trial instructions and the early PLL interpretation. Script
copies are exact non-executable `.py.txt` records; logs are normalized
`.log.txt` exports without line filtering. Private/generated images and
full disassemblies stay local. See the
[experiment guide](../../audio-pll-experiments/README.md) and
[hash/disposition manifest](../../audio-pll-experiments/manifest.json).
No hardware operations were performed during curation.
