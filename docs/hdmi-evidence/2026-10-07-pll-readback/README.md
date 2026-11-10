# RTT register-read output — October 7, 2026

Historical evidence, curated October 19. The [profile](audio-monitor-profile.json)
redirects the successful firmware `regr` printf tail call from UART4 to RTT.
A missing reply before the redirect was not a zero register reading. The
monitor witness drops its pointer field to make room for the redirect while
keeping 42 records and the original register/stack/branch behavior.

`first-h713-pll-readback-*.log.txt` retain the short, delayed/interleaved
replies; treat them as exploratory. `confirmation-refused/` retains the failed
snapshot-sequence gate (no tone). The retry used increasing snapshots 12–15
and complete two-second replies, e.g.
[confirmed-h713-pll-readback-3.log.txt](confirmed-h713-pll-readback-3.log.txt).
Canonical lock/playback passed while the DMA sentinel and SPDI/bridge IRQ
counts remained unchanged. The monitor saw valid N/Fs during playback.

**Interpretation correction:** the original notes inferred missing PLL setup
from aligned word reads +4=3 and +c=0. Later scalar byte reads showed that these
word loads do not return packed four-byte bank contents. Those observations
do not prove missing upper-byte programming; the hypothesis is withdrawn.
Neither word readings nor the printf redirect establish physical lock or PCM
capture. See the correction sections of the [original notes](README.md.txt).
The later PLL byte-read experiments remain a separate follow-up.

[candidate-install.log.txt](candidate-install.log.txt),
[uboot-restored.log.txt](uboot-restored.log.txt) and
[cleanup.log.txt](cleanup.log.txt) preserve full candidate/readback, exact
original U-Boot/SPL restoration and responsive MIPS. Original cold-start and
staging instructions are historical session records, not current next steps.

All original notes/scripts are retained as non-executable `.md.txt`/`.py.txt`
snapshots; normalized `.log.txt` exports retain every log line. Private images,
raw media and full disassemblies stay local. See the
[diagnostic guide](../../audio-trace-diagnostics/README.md) and its
[hash/disposition manifest](../../audio-trace-diagnostics/manifest.json).
No hardware operations were performed during this curation.
