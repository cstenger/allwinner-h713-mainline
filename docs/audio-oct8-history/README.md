# October 8 audio safety and rate-test history

Curated October 19, 2026. This archive connects the corrected DSP safety
preflight with an aborted rate-test setup and its later successful cold-start
retry. These are historical observations, not a current deployment procedure.
No hardware, serial, SSH, playback or device-memory access occurred during
curation. No source or ignore rules changed.

| Session | Evidence | Supported outcome |
| --- | --- | --- |
| Safety preflight | [audio-safety](../hdmi-evidence/2026-10-08-audio-safety/README.md) | Corrected shared DSP lock and bounded version reads worked in the observed boot state; speaker init trace used simulated hardware |
| Rate attempt 1 | [audio-rate-test](../hdmi-evidence/2026-10-08-audio-rate-test/README.md) | DSP graph setup timed out before playback; no sample-rate conclusion |
| Rate attempt 2 | [attempt2](../hdmi-evidence/2026-10-08-audio-rate-test/attempt2/README.md) | Four bounded trials accepted 48/32/44.1/48-kHz HDMI input and produced approximately 48-kHz stereo S16_LE diagnostic DMA data |

## Safety interpretation

The preflight record identifies the stock shared lock at physical 0x05001530
(two words), correcting earlier codec/DAUDIO addresses misidentified as locks.
Before the observed commands both words were zero; afterward the peer remained
zero and the ARM word was aa. Device-0/device-1 version reads returned 1. The
saved fake-MMIO test log reports contention, timeout/readback cases and 1000
cycles writing only the ARM word. These establish limited command behavior in
that boot and historical test results, not the cause of earlier timeouts or
universal readiness. The lock test was not rerun in this evidence-only cleanup.

The bridge IRQ correction and W1C handling are historical source observations.
The installed DT still had the old ordering during preflight, so no bridge
module was loaded in that preflight. Subsequent rate sessions used the known
RAM-only IRQ correction and separately logged setup; do not combine their
states into one run. Current implementations live in the
[DSP probe](../../modules/hdmi-dsp-probe/README.md) and
[speaker bench](../../modules/hdmi-speaker-split/README.md), which have evolved
since these logs.

The archived speaker-init decoder trace has return codes 0/0 and explicit
library/preset hashes. Its hardware operations, time and firmware-version
responses were stubbed. It records stock interface/selector operations but
establishes neither physical BCLK/LRCK frequencies nor working speaker output.
The complete trace is retained for provenance, without rerunning that private
library model or promoting its writes into a new live recipe.

## Rate outcome and limits

The first attempt issued a graph write to 0012=8180, then timed out on its
completion-clear readback after 50102 us. Its final value and later graph
settings were unverified. The probe latched failure and stopped DSP commands;
cleanup restored bridge/clock state but could not restore the partial DSP
graph. No playback ran. The logs cannot distinguish an unserviced command
from a missed clear/set transition, and cannot establish a sample-rate failure.

After a physical cold cycle, attempt 2 applied and verified all 22 graph words,
then ran four independent bounded source windows. Host `hw-params.txt`, direct
`hw:` playback logs and ELD records support the requested input formats. Known
left-1-kHz/right-2-kHz tone cycles per sample support the DMA-rate inference:

| HDMI input | Inferred DMA rate | Minimum expected-tone energy fraction | RMS ratio L / R to first control |
| --- | --- | ---: | --- |
| 48 kHz control | approximately 48 kHz | 0.958219 | 1.000000 / 1.000000 |
| 32 kHz | approximately 48 kHz | 0.972379 | 1.000001 / 1.001031 |
| 44.1 kHz | approximately 48 kHz | 0.991305 | 0.999833 / 1.000183 |
| 48 kHz control | approximately 48 kHz | 0.957441 | 0.999830 / 1.000009 |

Each trial has three 64-KiB tone snapshots and one all-zero active-stream
silence snapshot. Saved board uptime/IRQ counters reproduce advancing bridge
IRQs at about 184–185 Hz, including silence. The largest opposite-channel tone
energy fraction at the inferred 48-kHz rate is 6.02831e-5. Playback/helper
return codes are zero, and the saved summary equals the four detailed results.
The graph was reverse-restored with 22 verified saved values; cleanup logs
record module/route/clock teardown and responsive MIPS. The volatile DSP patch
remained until cold boot; that is a historical state, not the board's state now.

Approximately 48-kHz output from 32/44.1-kHz input supports an inference of rate
conversion somewhere in the receiver/DSP path. It does not locate the block,
measure continuous frame timing or drift, prove uninterrupted rate switching
with one open capture, or establish 24-bit/multichannel/compressed support.
These are finite live-ring snapshots, whose read seams can affect spectra.
The historical fixed-48-kHz stereo S16_LE driver implication is limited to this
tested path; this archive does not change driver capabilities.

## Provenance and offline validation

[manifest.json](manifest.json) records all 149 original files, their hashes,
exports and explicit local dispositions. The 82 useful exports include logs,
structured traces/results and exact original `README.md.txt` snapshots. Three
curated READMEs distinguish outcomes and superseded instructions. Normalized
logs preserve every line and trailing prompt whitespace while escaping
controls/invalid UTF-8 and converting CRLF to LF. Original selected bytes remain
under `build/audio-oct8-review/originals/evidence/` locally.

The 16 raw DMA rings, four generated EDID copies and four tone WAVs remain
local with hashes, along with 43 empty companion stdout/stderr/log files. Empty
output is not treated as a failure or missing trial; result files and helper
logs carry the successful command outcomes. No new ignore rule hides them.

[rate-validation.json](rate-validation.json) records re-analysis of all 16 local
rings with the unchanged, hash-recorded
[analyzer](../../tools/hdmi/audio-rate-analysis.py). The archived metrics match
within relative 1e-10 / absolute 1e-8 tolerance; all pass classifications,
channel levels, zero-silence observations and IRQ-rate calculations reproduce.
The analyzer checks each ring independently and does not establish continuity.
Raw rings are intentionally not embedded in Git, so that re-analysis requires
the retained local inputs. It is a repeat analysis of old samples, not another
hardware success. [validation.json](validation.json) records archive/hash,
format, preflight, timeout, graph-restore and source-rate consistency checks.
No historical binaries or firmware were rebuilt or installed.
