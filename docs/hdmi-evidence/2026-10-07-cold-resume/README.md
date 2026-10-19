# Cold resume and receiver audio cache — October 7, 2026

Historical records, curated October 19. The first no-stock-IO window failed
to detect a source and skipped tone playback; see
[cache-trial-no-stock-io.log.txt](cache-trial-no-stock-io.log.txt). A later stock-IO
comparison and canonical-EDID playback window reached 1280x720/repeat0 lock.
This session does not isolate which IO setting was necessary.

[audio-cache-trial.json](audio-cache-trial.json) contains six tone-phase samples
with N=6144 and CTS=74250. At a 74.25-MHz pixel clock that implies 48-kHz incoming
metadata; no Audio Bridge/SPDI capture trial was run here. ARM snapshots may be
stale behind MIPS D-cache. Zero PLL history does not establish non-execution;
[later positive firmware evidence](../2026-10-07-audio-monitor/README.md) corrected
that inference.

The JSON retains old names: `pll_last_cts` means last N, `pll_last_n` means last
sample rate, and `channel_status_rate_code` later became `infoframe_rate_code`.
Raw words are unchanged. [cleanup.log.txt](cleanup.log.txt) and
[audio-cache-final.json](audio-cache-final.json) preserve the recorded end state,
with responsive MIPS and receiver/clock holds retained for that session.

[uboot-init.log.txt](uboot-init.log.txt) and
[uboot-source3.log.txt](uboot-source3.log.txt) are saved boot/source-3 records.
The former is also copied in DSP-cold; it cannot independently confirm two
boots. The shared [host PCM selection](source-audio-pcm.json) likewise has exact
copies in the other collections. See the manifest for canonical mappings.

[README.md.txt](README.md.txt) preserves the detailed original narrative and
superseded next steps. The command script is archived as
[non-executable text](cache-trial-command.py.txt); full disassemblies stay local.
See the [history guide](../../audio-bringup-history/README.md) and
[provenance manifest](../../audio-bringup-history/manifest.json).
No hardware was accessed during curation.
