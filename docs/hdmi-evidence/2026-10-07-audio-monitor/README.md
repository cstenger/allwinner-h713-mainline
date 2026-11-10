# Audio cache baseline — October 7, 2026

Historical evidence, curated October 19. Positive firmware records in
[elog-hdmi.txt](elog-hdmi.txt) show SetAPLL's Update path executing before
source-loss handling; unchanged ARM reads of cached MIPS state cannot prove
that it never ran. Missing elog records are likewise inconclusive.

[cache-trial.log.txt](cache-trial.log.txt) and `audio-cache-trial.json` retain
the timing window. The correlated bridge trial reached canonical 720p lock
and played stereo 48-kHz audio but retained an unchanged DMA sentinel and
zero SPDI1/bridge IRQs; see [bridge-probe-dmesg.log.txt](bridge-probe-dmesg.log.txt)
and [bridge-cleanup.log.txt](bridge-cleanup.log.txt). This did not establish
physical PLL lock, PCM capture or an upstream cause.

The [original notes](README.md.txt) preserve the detailed observations and
then-proposed monitor experiment. That experiment subsequently ran in the
[next evidence group](../2026-10-07-audio-monitor-trace/README.md).

All original notes/scripts are retained as non-executable `.md.txt`/`.py.txt`
snapshots; normalized `.log.txt` exports retain every log line. Private images,
raw media and full disassemblies stay local. See the
[diagnostic guide](../../audio-trace-diagnostics/README.md) and its
[hash/disposition manifest](../../audio-trace-diagnostics/manifest.json).
No hardware operations were performed during this curation.
