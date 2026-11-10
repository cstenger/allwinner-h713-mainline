# Rate-test attempt 1 — aborted before playback, October 8, 2026

Historical records, curated October 19. This attempt never ran the rate sweep
and establishes no 32/44.1/48-kHz sample-rate failure. The subsequent
[attempt 2](attempt2/README.md) completed after a physical cold cycle and must
be interpreted separately.

The original listener attempts missed the expected console/boot boundary;
a later `reboot bootloader` reached U-Boot after normal panel initialization.
The saved MIPS/source-3/FIT and RAM-DT boot logs document that sequence, which
differs from attempt 2's direct cold-stop boundary. Matching module hashes alone
do not remove that boot-state difference or establish why setup later failed.

[dsp-patch.log.txt](dsp-patch.log.txt) records the volatile 724-pair patch and
versions 1/1. In [dsp-graph-failure.log.txt](dsp-graph-failure.log.txt), all 22
original graph words were read and nine writes verified. The next graph write
0012=8180 was issued, but its readback timed out on completion-clear after
50102 us. Its final value and remaining graph settings are unverified.
No further DSP traffic or software retry followed. The records do not resolve
whether the command was unserviced or a clear/set transition escaped observation.

[cleanup.log.txt](cleanup.log.txt) records probe unload and bridge/TVFE/clock
restoration, plus responsive MIPS. The failure latch prevented partial DSP
graph restoration; the volatile patch/partial graph required a physical cold
boot before another DSP trial. That is the recorded October 8 boundary,
not a request to change the board's state now.

[README.md.txt](README.md.txt) retains the original narrative and superseded
next steps. Normalized `.log.txt` exports retain all lines. See the
[history overview](../../audio-oct8-history/README.md) and
[hash/disposition manifest](../../audio-oct8-history/manifest.json).
No board, network, playback or device-memory access occurred during curation.
