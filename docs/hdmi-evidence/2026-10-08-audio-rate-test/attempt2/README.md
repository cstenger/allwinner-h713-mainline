# Rate-test attempt 2 — completed sweep, October 8, 2026

Historical records, curated October 19. After a physical cold cycle stopped
at U-Boot, the graph setup and four bounded trials completed without the prior
DSP timeout. The [summary](sweep/summary.json) equals the four detailed result
files. This is one historical sweep, not four newly repeated hardware tests.

| Trial | Host input | Inferred diagnostic DMA rate | Minimum expected-tone fraction |
| --- | --- | --- | ---: |
| Initial control | 48000 Hz | approximately 48000 Hz | 0.958219 |
| Input-rate control | 32000 Hz | approximately 48000 Hz | 0.972379 |
| Input-rate control | 44100 Hz | approximately 48000 Hz | 0.991305 |
| Final control | 48000 Hz | approximately 48000 Hz | 0.957441 |

Each trial retains ELD, hardware parameters, direct `hw:` playback logs, source
helper evidence, timing/IRQ observations and detailed analysis. Twelve 64-KiB
stereo S16_LE tone rings support left-1-kHz/right-2-kHz tone/channel/level checks;
four active-stream silence rings are entirely zero. Re-analysis of those local
rings reproduces the saved metrics, levels and advancing approximately
184–185-Hz bridge IRQ rates; see
[rate-validation.json](../../../audio-oct8-history/rate-validation.json).
Raw rings, tone WAVs and EDID copies stay local with hashes in the manifest.
Empty companion outputs stay local too; they are not treated as failed commands.

Host parameters and verbose playback confirm the requested input rates.
DMA rate is inferred from tone cycles per sample, not assumed from WAV headers.
Approximately 48-kHz output from 32/44.1-kHz input supports rate conversion
somewhere in the path; it does not locate the converter, measure timing/drift,
prove seamless switching during one open capture, or extend the result to
24-bit/multichannel/compressed audio. Ring-read seams can affect spectra.
The original fixed-48-kHz stereo S16_LE driver implication is limited to these
diagnostic observations; no driver capability changes are made here.

[dsp-graph.log.txt](dsp-graph.log.txt) records all 22 applied/verified settings;
[dsp-graph-restored.log.txt](dsp-graph-restored.log.txt) records all 22 originals
reverse-restored with matching readbacks. [cleanup.log.txt](cleanup.log.txt)
records teardown and responsive MIPS. The volatile stock patch remained until
cold boot, while persistent boot artifacts were unchanged in that session.
These are historical states, not assertions about the board now.

[README.md.txt](README.md.txt) preserves the original full report. See the
[history overview](../../../audio-oct8-history/README.md) and
[hash/disposition manifest](../../../audio-oct8-history/manifest.json).
No hardware was accessed during curation or sample re-analysis.
