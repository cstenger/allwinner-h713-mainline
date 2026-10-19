# DSP cold-start and bounded reads — October 7, 2026

Historical records, curated October 19. A video-only 128-byte EDID passed video
lock but failed the canonical audio playback guard; it was not a tone trial.
[video-only-128-byte-edid.log.txt](video-only-128-byte-edid.log.txt) preserves that
control. The subsequent canonical 256-byte EDID window completed playback;
[audio-cache-trial.json](audio-cache-trial.json) has six tone samples at 720p
with N/CTS6144/74250. Those are cached metadata, not recovered PCM samples.

[dsp-read-result.log.txt](dsp-read-result.log.txt) records fff7=0 and responsive
MIPS. [dsp-fresh-result.log.txt](dsp-fresh-result.log.txt) records an accepted
selector0077=0 reply followed by a selector0130 timeout observing completion
clear. No0130 response was accepted; further requests were blocked. Fast
completion can escape such observation, so this is inconclusive about command
service or DSP health. fff7 alone does not establish patch readiness.

**Later correction:** the old ownership/address discussion in the original
notes predates the [real shared-lock preflight](../2026-10-08-audio-safety/README.md).
Earlier codec/DAUDIO addresses were misidentified as locks; this archive does
not validate them as safe handshake addresses. Historical successful replies
are limited to their observed probe/boot state.

[final-health.log.txt](final-health.log.txt) records responsive Linux/MIPS with
the failed DSP probe still loaded. This was not a successful DSP teardown;
its next DSP trial required a physical cold start. That is a historical state,
not an instruction to change the board now. No PCM was captured.

The duplicate U-Boot init log references the canonical
[cold-resume export](../2026-10-07-cold-resume/uboot-init.log.txt).
[uboot-source3.log.txt](uboot-source3.log.txt) is also copied into readiness.
The host PCM-selection JSON references its
[cold-resume copy](../2026-10-07-cold-resume/source-audio-pcm.json).
None is counted as an independent trial witness merely because it was copied.
The empty command log stays local; the nonempty result record is retained.

[README.md.txt](README.md.txt) preserves the original detail. The trial script
is a non-executable `.py.txt` snapshot. See the
[history guide](../../audio-bringup-history/README.md) and
[hash/disposition manifest](../../audio-bringup-history/manifest.json).
No hardware operations were performed during curation.
