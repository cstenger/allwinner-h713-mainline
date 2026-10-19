# Stock PLL init-on-zero experiment — October 7, 2026

Historical evidence, curated October 19. This functional experiment retains
the metadata retry, optimizes its stack restoration into jump delay slots,
and changes stock SetAPLL's Init selection from negative-only to nonpositive
at `0x8b13c628`. The
[profile](audio-monitor-profile.json) and
[candidate manifest](candidate-manifest.json) retain 42 patch records and
180 changed bytes confined to the original 672-byte table.

The [offline model record](emulation.json) includes direct Init completion,
Update reaching the instruction limit without a simulated handshake,
modified SetAPLL completing Init, and a hypothetical collapsed-byte-store
case. The latter reproduces early word readings but does not establish that
fault on hardware. Direct Init produces modeled +c=60180000, clearing bit31;
that bit selects a path rather than proving completion. Offline Init returning
success is not physical PLL-lock evidence.

Cold launch/source-3 and the live profile checks passed; see
[profile-verified.log.txt](profile-verified.log.txt).
[restored-and-profile.log.txt](restored-and-profile.log.txt) records exact
original U-Boot and unchanged SPL restoration before the live capture trials.
Three canonical lock-gated playback windows, including DSP/bridge capture
routing, produced no DMA changes or IRQs. The positive firmware log in
[logged/elog-hdmi.txt](logged/elog-hdmi.txt) records `Calling Init`, divider
calculation and `HdmiRxAudioPllPowerUp success!`; these establish execution,
not physical lock. Missing ring messages or stale mode-byte zeros are not
negative execution evidence. [cleanup.log.txt](cleanup.log.txt) retains the
unchanged DMA sentinel, probe/route teardown and responsive MIPS.

**Later correction:** scalar byte reads showed that aligned MIPS PLL word
reads do not return packed four-byte bank contents. The earlier +0=67/+c=0
observations therefore do not prove missing upper bytes or collapsed byte
stores. That hardware fault hypothesis is withdrawn. The word-write experiment
proposed in the original notes is a separate historical follow-up, not a
current recommendation. Physical PLL lock and successful capture remain
unproven, and these results do not establish a production need for init-on-zero.

[README.md.txt](README.md.txt) preserves the original notes and their later
correction. Trial/install/restore and fixed-ring reader copies are exact
non-executable `.py.txt` snapshots. Normalized logs retain every line. Private
images, raw DRAM dumps and full disassemblies stay local. See the
[experiment guide](../../audio-pll-experiments/README.md) and
[hash/disposition manifest](../../audio-pll-experiments/manifest.json).
No hardware operations were performed during curation.
