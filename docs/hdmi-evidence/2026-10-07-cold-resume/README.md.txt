# Cold resume and receiver audio cache

The board was freshly powered at U-Boot. The volatile guarded MIPS startup,
HDMI1/source-3 transition, installed Linux boot, and postboot clock setup all
passed. Linux is 6.18.38, built October 6 at 17:19:05 PDT. No boot image,
bootloader, or persistent U-Boot environment was changed.

The latest HDMI checkout's audio work had already validated Audio Bridge/SPDI
setup without DMA samples. This session investigated the upstream firmware
audio path instead of repeating the bridge trial.

## Detection and audio timing

The first 30-second window, without stock DDC timing settings, never detected
the source. The tone was skipped. A ten-second `--stock-io` comparison read
the exact canonical 256-byte EDID and held receiver state 5 at 1280x720 with
zero pixel repeat in four samples. This establishes recovery using those
settings for this session; it does not isolate which setting is necessary.

The subsequent 30-second stock-IO window gated playback on that receiver lock
and the canonical EDID hash
`edab9bfc48547939fcb26f7775558c94569a11abb4beb1132e22f2ad4c173d34`.
The active ELD resolved PCM `hw:0,8`; `aplay` completed eight seconds of stereo
48-kHz S16_LE, left 1 kHz/right 2 kHz. Only MIPS DRAM was sampled, with no
ARM receiver MMIO reads, audio IRQ mappings, or Audio Bridge loads.

During playback, receiver firmware cached CTS=74250 and N=6144, status 0x10.
At the 720p 74.25-MHz pixel clock, `Fs = pixel_clock*N/(128*CTS) = 48000`.
One late post-tone sample also cached sample rate 48000 and rate code 0x30.
The PLL history fields remained zero throughout these samples. ARM may see
stale DRAM behind MIPS D-cache, so these zeros do not establish PLL execution
or failure. Later firmware elog records positively confirm SetAPLL update
execution; see ../2026-10-07-audio-monitor/README.md. No PCM samples have been
recovered.

## Firmware map and next boundary

Firmware SHA256:
`4380f1b3ed7b62aa50582e7cb16a87bdface1b4300578fe3631a416354da30ce`.

The audio worker state starts eight bytes into each port object. Its known
receiver-base field at worker+0x518 is 0x06840000, and the audio PLL base at
worker+0xb0 is 0x06880000. The sampler validates the receiver base before
interpreting fields. Relative to worker state:

| Offset | Field | Evidence |
|---|---|---|
| 0x78 | CTS | Get_N_CTS at 0x8b13c7f4 stores CTS first |
| 0x7c | N | Same routine stores N second |
| 0x80 | Sample rate in Hz | GetFs at 0x8b13c8f8 stores at audio+8 |
| 0x84 | Rate code | 0x8b13c6e0 stores at audio+0xc |
| 0x88 | Audio status byte | AudioMonitor compares audio+0x10 |
| 0xa8 | Last N for PLL setup | SetAPLL compares audio+4 with audio+0x30 |
| 0xac | Last sample rate for PLL setup | Compares audio+8 with audio+0x34 |

`ISREventHandle` 0x8b135ba4 handles event 0x3000 by calling Get_N_CTS/GetFs
with worker+0x78, then clears the PLL history fields. `AudioMonitor`
0x8b13a2a8 dispatches SetAPLL through table 0x8b22f0c4 when status changes.
SetAPLL 0x8b13c524 chooses full setup 0x8b13bcb8 or update 0x8b13c000.
Power-down/up helpers are 0x8b13b5e4/0x8b13b670. Listings are retained here.

Follow-up firmware elog confirms SetAPLL execution near source teardown in
one window. The next boundary is whether valid metadata triggers that path
during playback, and how recovered audio reaches SPDI1. The ARM cache zeros
are insufficient to resolve either question.

## Files and cleanup

`audio-cache-trial.json` retains all waiting/tone/post-tone samples. Its
original field names `pll_last_cts`/`pll_last_n` should be read as **last N /
last sample rate** respectively; further disassembly corrected the labels in
`tools/hdmi/read-mips-audio-cache.py`. `channel_status_rate_code` is now named
`infoframe_rate_code`. The original raw words are preserved.

`cache-trial-command.py` records the successful host command; it reads the
current HDMI checkout without modifying it. The canonical SCP probe was built
in /tmp against the running kernel build; SHA256
`0c41c7071c4606fc328fbc0d8ef2b52783af3dded199d1aad698ebedc5a3c0e0`.
Its source and generator came from commit aa8111f's HDMI checkout.

Both successful windows restored peripherals and SRAM with zero EDID
mismatches. Final source state is disconnected/disabled, DDC/SCP modules are
absent, and MIPS responds. TVFE/TVCAP, four capture clocks, and the EDID hold
remain active for the next session. The saved spirits Wi-Fi profile was
activated to reach the board. Syntax compilation and `git diff --check` pass.
