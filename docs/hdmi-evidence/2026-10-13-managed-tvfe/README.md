# Driver-managed TVFE sequence, 2026-10-13

**PASS: combined automatic TVFE + DSP initialization, all three input-rate
captures, and automatic restoration on unload.** Standalone TVFE and DSP
helpers were absent. Base receiver power/EDID holds remain for live MIPS.
[Summary](summary.json), [build hashes](build-manifest.json).

The driver includes the proven stock-order TVFE clock/reset sequence by default
with `manage_tvfe=1`, alongside managed DSP setup. The module SHA256 is
`7b0ddff871239da730e41e28b91e6b0db6cc68b9d9101f6e246a5d9ffbd9f5de`.

The component is adapted from the exact previously validated TVFE hold source,
retained in host `build/hdmi-alsa-tvfe`. It releases demod reset first, waits,
holds the two parent clocks, saves/applies15 functional clock words, then enables
the demod bus. It preserves the live MIPS-owned TVFE control word and refuses
uninitialized source state or an inherited active demod bus.

Initialization precedes audio IHB/AudioTop setup. Teardown follows DSP graph,
PCM/audio peripheral and audio clock restoration, while base receiver power
holds remain. It restores functional words, parent references, reset and bus,
with readback verification of all15 saved words and the bus. Partial mapping
failure cannot write an unsaved bus word.

[TVFE-only hardware cycle](tvfe-only-cycle.log) used `manage_dsp=0` to avoid
altering the existing DSP patch. No standalone TVFE module was loaded. The
integrated sequence loaded, MIPS responded, automatic teardown verified all
15 clock words/bus, and MIPS responded again. WirePlumber was restored after
briefly releasing its ALSA control handle.

[Native lifecycle controls](native-lifecycle.log) compile the actual component
against fake MMIO/clock/reset providers. They cover exact setup/restoration,
second-map allocation failure without unsaved register writes, inherited demod
owner rejection, and full rollback of uninitialized source3 control. These
controls do not establish hardware timings or power readiness.

Base `h713_hdmi_power` and `h713_edid_clock` holds deliberately remain. The
[power helper's live-MIPS notes](../../../modules/hdmi-bringup/README.md#live-mips-isolation)
record loss of firmware IPC when power/clock lifetime was mishandled and prohibit
removing the final hold under live MIPS. This change does not remove those holds,
power domains off, relaunch MIPS, manipulate HPD/EDID, or add receiver MMIO.
Independent receiver power lifetime needs further work before those helpers can
be removed safely. `manage_tvfe=0` retains the external TVFE-hold workflow.

## Combined fresh-boot result

The user's physical cold boot/manual U-Boot stop was followed by the same
single guarded MIPS launch, current PID/source3 worker verification, preserved
FIT and RAM-only IRQ correction. The base receiver holds were prepared; no
standalone TVFE or DSP helper was staged or loaded.

The new `tools/hdmi/load-managed-audio.py` bench loader staged the driver and
pinned firmware in board RAM, loaded the module and verified both managed modes,
readiness and no DSP failure. Its finally block writes a newline when restoring
an originally empty firmware search path and verifies the result. See
[load and path evidence](combined/driver-load/load.log).

The combined driver preserved live TVFE control, applied stock-order clocks,
initialized the pinned724-pair DSP patch from versions0/0 to1/1 and verified
all22 graph words before ALSA registration. The three-rate acceptance test then
recorded separate16-second WAVs for HDMI inputs48/32/44.1kHz. All768,000-frame
48kHz stereoS16_LE recordings passed tones, zero silence tails, process exits
and closed/reopened capture. Driver XRUN count remained zero.
[Capture summary](combined/capture-test/summary.json).

Removal verified all22 DSP graph readbacks first, restored audio resources,
then verified15 TVFE clock words and the bus/reset baseline. MIPS responded;
TVFE/TVCAP base holds remained active. WirePlumber was briefly stopped to
release its control handle and restored active after removal. The firmware
search path remained at its original empty value. See
[teardown](combined/unload-cleanup.log) and
[service verification](combined/service-restored.log).

No recovery is pending. Another managed load needs fresh DSP versions0/0;
the volatile patch remains until physical cold boot. No serial listener ran,
no boot artifact was flashed and no U-Boot environment was saved. Source3 boot,
base receiver power lifetime, long-term recording, physical hotplug endurance,
open-stream format changes and suspend remain outside this validation.
