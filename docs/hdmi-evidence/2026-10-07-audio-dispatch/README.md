# Dispatch-time N/Fs latch — October 7, 2026

Historical evidence, curated October 19. The [profile](audio-monitor-profile.json)
retains the RTT redirect and updates N/Fs only on a status-change dispatch.
The [candidate manifest](candidate-manifest.json) records 183 byte changes
inside the same 672-byte table. All three candidates are independently
reproducible from their pinned private inputs.

The two watches contain 362 samples total:

| Event | Monitor count | Dispatch count | Latched N / Fs |
| --- | ---: | ---: | ---: |
| First playback status 16 | 116 onward | 1 | 0 / 0 |
| Second playback, audio-clock holds | 3213 onward | 2 | 0 / 0 |
| Second signal removal | 6258 | 3 | 6144 / 48000 |

See [dispatch-watch.jsonl](dispatch-watch.jsonl) and
[audio-holds/dispatch-watch.jsonl](audio-holds/dispatch-watch.jsonl).
Each watch has one count-change flag. A clear flag is not an atomic snapshot
guarantee; the second watch even observes a status update before the dispatch
counter changes. The stable playback latch provides the useful timing witness:
valid metadata reached a dispatch only at source removal in these trials.
This supports a metadata/status timing gap without proving PLL completion,
lock, capture recovery or a complete diagnosis of absent DMA.

Aligned `regr` word replies remain in the logs, but the later scalar-byte
experiment invalidated the inference that +c=0 proves missing upper bytes.
The [original notes](README.md.txt) preserve both the early hypothesis and
its correction. Metadata retry/init and PLL access-width changes are deferred.

[restore.log.txt](restore.log.txt) records exact original U-Boot and unchanged
SPL hashes. Restoration occurred after the first window; the trace remained
in MIPS RAM for the second window without relaunch.
[cleanup.log.txt](cleanup.log.txt) records probe teardown and responsive MIPS.
Installation/restore/trial scripts are archived as text, not active tooling.

All original notes/scripts are retained as non-executable `.md.txt`/`.py.txt`
snapshots; normalized `.log.txt` exports retain every log line. Private images,
raw media and full disassemblies stay local. See the
[diagnostic guide](../../audio-trace-diagnostics/README.md) and its
[hash/disposition manifest](../../audio-trace-diagnostics/manifest.json).
No hardware operations were performed during this curation.
