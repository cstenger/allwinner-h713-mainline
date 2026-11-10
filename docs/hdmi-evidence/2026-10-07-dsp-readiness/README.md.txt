# DSP readiness and fixed stock initialization

User physically power-cycled and stopped at U-Boot. Guarded first MIPS launch,
source3 transition and installed Oct7 18:57:16 kernel boot passed. No Linux
kernel, SPL or rootfs product change. Exact kernel tree is the2a2ced73e505...
6.18.38 build recorded by build-dsp-probe.py.

Immediate bounded completion sampling removed the previous scheduling gap.
Both DSP version words80ff (devices0/1), capture selector0130 and speaker
selector0077 returnedzero with a fresh completion transition. DSP0 uses
06144010, busy/done bits4/5; DSP1 uses06144018,bits7/8. Both protocols are
recovered from the exact saved libmspdriver. Tested reader module SHA256
41dab4e3f48df98785225c3b81f9de4d3ee7d22e5bececa0f8bae36f4031c2fb.

The fixed stock init/patch probe was built only from the pinned2896-byte blob,
SHA2568e31db199e0078d142f622436ff0b7249b333dbb6df8ec3fbabc0d8fea6ea0c5.
It required both versionszero before any init write. Masked readbacks passed:
00ee:0200->0180 (DSP clock speed3),8034:00->10 (HDMI RX enabled),
8017:00->01 (HDMI I2SIN mute). All724 big-endian patch pairs completed with
bounded busy waits and stock1ms pacing. Both version80ff words became0001,
matching stock's nonzero readiness condition; fff7 remainedzero. Exact tested
module6cdb07585fa03ef3d6dca16d3cb44de3b49beb2b44a8c25cfe846782d9d404d9.
Linux/MIPS stayed responsive and owner50/kernel-owner0 were preserved.

Preset routebd was applied and read back as0130=1617, sourcing I2SIN1/9600
into DTVOUT1/9500. HDMI mute8017 bit0 was cleared. A separately named bridge
probe cloned the previously validated staged SPDI1/Audio Bridge source; no
changes to its power/IRQ/DMA protocol, and the original audio clock hold
remained loaded throughout. Module69e1571c594d30bc85f4dde22a0eb2a707f22d2555ec87f57f214f1b4913a639.
Its source is retained at/tmp/h713-dsp-bridge-trial/h713-hdmi-bridge-trial.c.

The first playback precondition failed because the board's staged default
probe was again the128-byte video-only build. No audio was sent then.
The trial runner now explicitly stages/hash-verifies the canonical probe
0c41c7071c4606fc328fbc0d8ef2b52783af3dded199d1aad698ebedc5a3c0e0 before
each window; no reliance on the board's default staging directory.

Two canonical256-byte EDID/720p-lock-gated8-second stereo48kHz tone windows
completed. One used routing+unmute; the second added I2SIN1 enable0012 bit15.
The latter bit is independently recovered by executing MAPI_AUD_EnableInterface
on module9600 in Unicorn after Init_Modules. API's second argument is an error
output pointer, not an enable boolean; output trace is saved. No guessed I2S
format or gain configuration was applied.

All64KiB stayed at a5 sentinel, FNV62519dc5, zero SPDI and Audio Bridge IRQs
in both windows. N/CTS6144/74250 confirms incoming48kHz metadata. Evidence
without-interface/ retains the first complete trial. Current top-level trial
files are the interface-enabled repeat. The interface route module tested was
fa8482d89ee0959ab5319c7ba45b5bbed21985fe93d7cfdc9fced00fff18bde7.
This rules out missing fixed stock DSP initialization as the sole capture
blocker; it does not validate a complete DSP graph or DTVOUT-to-memory wiring.

Teardown released both capture IRQs/private DMA and restored selector0130=0,
mute8017=1, I2SIN word0012=0, with readback. Both DSP versions remained1 and
MIPS help win passed. Receiver/audio power holds remain active. DSP firmware
is volatile until power cycle. Python syntax, both module builds and git diff
--check pass. No PCM captured.

Next: earlier firmware-side PLL reads showed power bit still set and setup
bit absent during valid audio timing. New dispatch-latched trace is prepared
under ../2026-10-07-audio-dispatch to freeze N/Fs at the actual status-change
SetAPLL branch. Do not infer receiver PLL readiness from DSP versions.
