# Scalar PLL byte-read diagnostic — October 7, 2026

Historical evidence, curated October 19. The
[profile](audio-monitor-profile.json) replaces the firmware `regr` LW at four
exact PLL addresses with four packed LBU reads, retaining stock PLL stores
and the init/retry layer. The word-write shim is absent from this candidate.
[profile-verified.log.txt](profile-verified.log.txt) records all 96 instructions,
magic and canaries; [restored.log.txt](restored.log.txt) records exact original
U-Boot and unchanged SPL restoration.

Complete playback replies in [pll-active-0.log.txt](pll-active-0.log.txt) and
[pll-active-1.log.txt](pll-active-1.log.txt) show:

| Address | Packed four-byte value |
| --- | --- |
| 06880000 | 0d320667 |
| 06880004 | 50000010 |
| 0688000c | 60180000 |
| 06880010 | 00000003 |

These reveal configuration bytes absent from the preceding aligned LW replies.
Thus +c=0/+0=67 did not establish missing upper-byte writes or collapsed byte
stores; that hypothesis is withdrawn. The positive Init/PowerUp log in
[elog-hdmi.txt](elog-hdmi.txt) establishes execution, not physical PLL lock.
The first receiver-only playback window isolated the read-width observation
from DSP initialization. Values also persisted in later capture windows.

The subsequent DSP/bridge window under `capture/` completed playback but
[bridge-after.log.txt](capture/bridge-after.log.txt) retains unchanged DMA
sentinels and zero IRQs. A later DTV channel-selector control under `channel1/`
also left DMA unchanged; [restored.log.txt](channel1/restored.log.txt) records
selector and route-owner restoration, not another bootloader restoration.
The `dtvout-channel-model.json` file is an archived two-channel model; this
cleanup checks its integrity rather than claiming a new model execution.
No successful PCM capture or complete capture-blocker diagnosis is established.

[README.md.txt](README.md.txt) preserves the original pre-trial summary; the
completed outcomes above come from the retained logs. Install/restore/trial
copies are exact non-executable `.py.txt` records, and normalized `.log.txt`
exports retain every line. Private images/shims, raw DRAM and full disassemblies
stay local. See the [access experiment guide](../../pll-access-experiments/README.md)
and [hash/disposition manifest](../../pll-access-experiments/manifest.json).
No hardware operations were performed during this cleanup.
