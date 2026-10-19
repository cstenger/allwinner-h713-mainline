# Scalar PLL word-write experiment — October 7, 2026

Historical evidence, curated October 19. The
[profile](audio-monitor-profile.json) retains init/retry and replaces two byte
helper stores with a bounded aligned word RMW shim. It was motivated by a
collapsed-byte-store hypothesis that later scalar byte reads invalidated.
This is an experiment record, not a recommended production change.

The [candidate manifest](candidate-manifest.json) identifies the exact
96-record candidate. [profile-verified.log.txt](profile-verified.log.txt) and
[restored.log.txt](restored.log.txt) retain matching live code and complete
original U-Boot/unchanged SPL restoration. The diagnostic remained only in live
MIPS RAM during the historical trials.

[dsp-timeout.log.txt](dsp-timeout.log.txt) records a final device-1 version
completion timeout at pair 724. No DSP retry or bridge route followed, so this
boot has **no valid DMA capture result**. Two receiver-only windows reached
canonical 720p/audio metadata and completed their bounded playback gates.
[logged/elog-hdmi.txt](logged/elog-hdmi.txt) positively records stock Init and
PowerUp. Aligned word replies did not change; this did not confirm collapsed
stores. [cleanup.log.txt](cleanup.log.txt) records teardown and responsive
MIPS; partial volatile DSP state required a physical cold boot afterward.

The [model](model.json) preserves baseline, hypothetical collapse, and shim
semantics. All three are reproducible offline, but a model explaining an
observation is not proof of that hardware fault. The following
[byte-read diagnostic](../2026-10-07-pll-byte-read/README.md) demonstrated that
aligned PLL word reads were not packed four-byte bank values. Missing upper
bytes/collapsed stores are therefore withdrawn interpretations; PLL lock
remains unproven.

[README.md.txt](README.md.txt) preserves the original evolving notes, including
superseded pending-trial instructions. Helper/install/restore/trial copies are
non-executable `.py.txt` snapshots. Logs are normalized without line filtering.
Private/generated binaries and full disassemblies stay local. See the
[access experiment guide](../../pll-access-experiments/README.md) and
[hash/disposition manifest](../../pll-access-experiments/manifest.json).
No hardware operations were performed during this cleanup.
