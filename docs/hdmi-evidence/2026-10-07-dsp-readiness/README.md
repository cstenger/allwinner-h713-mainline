# DSP fixed-init and route/interface comparison — October 7, 2026

Historical records, curated October 19. [result.log.txt](result.log.txt) records
zero version words on both devices and zero selectors. The fixed init in
[stock-init-result.log.txt](stock-init-result.log.txt) verifies three masked
settings and reports all724 patch pairs with versions1/1; fff7 remains zero.
This supports the particular init sequence, not a complete working DSP graph.

The video-only EDID control refused playback; the two later canonical EDID/720p
windows used routing+unmute, then added I2SIN1 word0012 bit15. The saved
[offline interface trace](interface-enable-offline.json) supports that modeled
enable write, not physical clock measurements or full format/gain setup.
It was not re-executed in this cleanup.

The first window's canonical logs are under
[without-interface/](without-interface/tone-run.log.txt). Top-level `tone-run.log`
and `bridge-tone-snapshots.log` are byte-identical copies of those first-window
files; they do not separately confirm the interface-enabled repeat. The latter
uses [audio-cache-trial.json](audio-cache-trial.json),
[cache-trial.log.txt](cache-trial.log.txt),
[interface-and-bridge-start.log.txt](interface-and-bridge-start.log.txt), and the
second DMA epoch in [final-capture-and-restore.log.txt](final-capture-and-restore.log.txt).

That aggregate log retains two11-snapshot DMA epochs: all changed counts and
bridge IRQ counts are zero, with sentinel FNV62519dc5 unchanged. Temporary
bridge resources and route/interface/mute settings were later restored with
readbacks. DSP versions remained1/1 and MIPS responded; the volatile patch
itself remained until cold boot. No PCM was recovered. These observations do
not establish the sole capture blocker or validate the complete stock graph.

**Later corrections:** these early probes predate the
[real DSP lock correction](../2026-10-08-audio-safety/README.md). Cached zeros
cannot prove SetAPLL non-execution, bit31 is not a PLL completion flag, and
[scalar byte reads](../2026-10-07-pll-byte-read/README.md) invalidated the missing
upper-byte/collapsed-store hypothesis. The original notes' proposed next steps
are historical rather than current instructions.

The copied source-3 log references the canonical
[DSP-cold export](../2026-10-07-dsp-cold/uboot-source3.log.txt), and PCM-selection
metadata references the [cold-resume export](../2026-10-07-cold-resume/source-audio-pcm.json).
[README.md.txt](README.md.txt) retains the full original narrative; the command
script is an exact non-executable `.py.txt` snapshot. See the
[history guide](../../audio-bringup-history/README.md) and
[hash/disposition manifest](../../audio-bringup-history/manifest.json).
No hardware was accessed during curation.
