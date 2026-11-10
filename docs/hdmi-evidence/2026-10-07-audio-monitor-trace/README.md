# AudioMonitor trace — October 7, 2026

Historical evidence, curated October 19. The [profile](audio-monitor-profile.json)
and [candidate manifest](candidate-manifest.json) describe the exact monitor
instrumentation. The first RAM-table write faulted before completion on a
read-only mapping; [uboot-overlay-install.log.txt](uboot-overlay-install.log.txt)
retains the abort. That installation path is withdrawn.

A later temporarily installed storage candidate passed full readback.
[uboot-restored.log.txt](uboot-restored.log.txt) and
[bridge-cleanup.log.txt](bridge-cleanup.log.txt) retain exact original U-Boot
and unchanged SPL hashes. Trace code remained only in live MIPS RAM until a
power cycle; this describes that session, not the board's present state.

The [watch](monitor-watch.jsonl) contains 181 samples: monitor calls rose
3187→6361, with two reads flagged for a count change. The
[summary](monitor-summary.json) records dispatch counts 0→5 and eventual
N/Fs 6144/48000. These fields were sampled on every comparison, so the trace
did not establish their values at the dispatch itself. The correlated bridge
trial still produced no DMA/IRQs. The fallback EDID/no-tone control remains
under `fallback-edid-no-tone/`; it was a refused playback gate, not a tone run.

[Original notes](README.md.txt) contain evolving plans, including a stale
"not validated on hardware yet" paragraph superseded by their later results.
The archived prototype tests established only mocked guard behavior, not
permission to write the hardware mapping. Continue with the
[RTT readback](../2026-10-07-pll-readback/README.md) and
[dispatch latch](../2026-10-07-audio-dispatch/README.md) results.

All original notes/scripts are retained as non-executable `.md.txt`/`.py.txt`
snapshots; normalized `.log.txt` exports retain every log line. Private images,
raw media and full disassemblies stay local. See the
[diagnostic guide](../../audio-trace-diagnostics/README.md) and its
[hash/disposition manifest](../../audio-trace-diagnostics/manifest.json).
No hardware operations were performed during this curation.
