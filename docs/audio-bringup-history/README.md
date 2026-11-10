# October 7 cold-resume and DSP bring-up history

Curated October 19, 2026. These early collections precede the later
[audio tracing](../audio-trace-diagnostics/README.md),
[PLL experiments](../audio-pll-experiments/README.md) and
[October 8 safety/rate records](../audio-oct8-history/README.md). They describe
historical boot and probe states, not current hardware instructions. Curation
used only file/hash/format and saved-observation checks: no hardware, network,
serial, playback, firmware execution or model rerun occurred.

| Collection | Supported observation | Boundary |
| --- | --- | --- |
| [Cold resume](../hdmi-evidence/2026-10-07-cold-resume/README.md) | Failed no-stock-IO control, later canonical EDID/720p lock and cached N/CTS during playback | Cached zeros do not establish SetAPLL non-execution; no capture trial here |
| [DSP cold-start](../hdmi-evidence/2026-10-07-dsp-cold/README.md) | Video-only EDID refusal, canonical playback, bounded raw DSP replies | Selector read timed out observing completion-clear; failed probe remained loaded |
| [DSP readiness](../hdmi-evidence/2026-10-07-dsp-readiness/README.md) | Zero-to-one version change after fixed 724-pair init, route/interface comparisons | Unchanged DMA sentinel/IRQs; versions and route readbacks do not establish a complete capture graph |

## Keep the early interpretations bounded

Cold-resume JSON retains its original labels: `pll_last_cts` is actually last N,
`pll_last_n` is last sample rate, and `channel_status_rate_code` was later named
`infoframe_rate_code`. The raw words and original labels are not rewritten.
Later collections use corrected labels. Six cold-resume and six DSP-cold tone
samples, plus four samples in each readiness window, record receiver state 5,
1280x720/repeat 0 and N/CTS 6144/74250. At a 74.25-MHz pixel clock those metadata
values imply 48000 Hz. That is not a measured PCM capture rate. ARM reads of
MIPS cache-backed structures can be stale; missing/zero history cannot prove
firmware non-execution. Later positive elog and uncached tracing supersede that
inference.

The DSP cold-start/readiness notes predate discovery of the real shared lock.
Their old ownership/address interpretation is historical and must not become
a live access recipe. The [October 8 preflight](../hdmi-evidence/2026-10-08-audio-safety/README.md)
identifies the shared lock at physical 0x05001530 and corrects earlier
codec/DAUDIO addresses misidentified as locks. Success of a bounded reply in
these earlier states does not validate those old ownership assumptions or
explain other timeouts.

In the cold-start probe, fff7=0 and selector0077=0 were accepted replies;
selector0130 did not produce an accepted completion-clear observation. The
failure latch blocked further requests. A fast clear/set transition could
escape observation, so this is not proof of an unserviced command or a failed
DSP. Its final-health record still lists the failed probe. Do not describe that
session as a successful DSP teardown.

In readiness, saved reads show both version words initially zero. Fixed init
readbacks and the `stock-patch pairs=724 version0=0001 version1=0001` record
support completion of that particular patch sequence. fff7 still being zero
shows why it alone was not a readiness test. The offline interface trace records
a modeled enable write to word0012 bit15; it was not re-executed here and does
not establish physical I2S clocks or a complete stock format/gain configuration.

The final aggregate capture/restore log contains two 11-snapshot DMA epochs,
separated by interface enable/reload. All 22 records report changed=0,
FNV62519dc5 and zero bridge IRQ count; status snapshots also retain zero IRQs.
The interface-enabled epoch ends with word0012 restored to zero, selector0130
to zero and mute8017 to one, followed by version1/1 and responsive MIPS. This
restored temporary routing/resources, not the volatile DSP patch. No PCM was
recovered in these sessions. Later captures succeeded under different setup;
these records do not establish a universal capture failure or its sole cause.

Old PLL claims about a missing setup bit are also superseded: bit31 selects an
Init path rather than proving completion, and later scalar-byte reads showed
aligned PLL words were not packed bank contents. See the
[PLL access correction](../pll-access-experiments/README.md).

## Duplicate and provenance decisions

[manifest.json](manifest.json) covers all 66 original files: the 61 review
candidates and five already-local disassemblies. It records source/export hashes
and dispositions. There are 54 unique committed exports. Six duplicate originals,
one empty command log and five disassemblies remain local. All original bytes
were backed up under `build/audio-bringup-review/originals/evidence/` locally.
All 66 match the October 18 inventory hashes.

Two top-level readiness files, `tone-run.log` and `bridge-tone-snapshots.log`,
are exact copies of their `without-interface/` counterparts. Their canonical
exports live under `without-interface/`; they are not separate confirmation of
the second window. The interface-enabled repeat is supported by its own cache
JSON, `cache-trial.log.txt`, `interface-and-bridge-start.log.txt`, and the later
epoch in `final-capture-and-restore.log.txt`.

Likewise, shared `uboot-init.log`, `uboot-source3.log` and host PCM-selection
JSON copies are mapped to single exports. Identical copies cannot independently
confirm multiple boot boundaries or playback windows. Original narrative session
attributions are retained, but their copied setup records are not counted as
new trials. The empty `dsp-read-command.log` has no independent content and does
not contradict the nonempty result log.

Each collection has a curated `README.md` and an exact original `README.md.txt`.
The three session-specific trial scripts are exact, non-executable `.py.txt`
snapshots; they depend on old checkout/module paths and issue hardware commands
if executed, so they are not promoted as current tools. JSON is preserved
byte-for-byte. Logs retain every line and trailing prompt whitespace, decode
invalid UTF-8 visibly, convert CRLF to LF, and escape remaining controls.
No source or ignore rules changed and no original was deleted or moved.

[validation.json](validation.json) records export/original hash checks,
JSON/script syntax checks without script execution, metadata/raw-word label
consistency, EDID/control outcomes, DSP transition/timeout witnesses, duplicate
mapping and DMA/route-restoration observations. These checks verify archive
consistency, not new hardware behavior. Strict whitespace checks apply to
curated Markdown; exact historical exports preserve their trailing whitespace.

This completes the last substantive evidence group identified in the
[untracked review](../untracked-review-2026-10-18.md). The separate October 19
audit report is being kept for its documentation follow-up.
