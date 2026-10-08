# Verified stock Android HDMI audio capture, 2026-10-08

Stock Android captured 17.96 seconds (862,080 stereo frames) of the known HDMI
signal through Trident card 4, device 0. The left channel is 1 kHz, right 2 kHz;
more than 99.99998% of each channel's spectral energy is in its expected tone
band, with negligible opposite-channel energy. See `a2dp-tone-analysis.json`,
`a2dp-tone.pcm`, `a2dp-app-result.txt`, and `a2dp-app-state-{0..3}.txt`.
The operator also confirmed hearing the HDMI tone during the separate 30-second
stock speaker playback: "Yes, HDMI tone heard". See `completion.json`.

## Successful capture route

The foreground diagnostic app explicitly selected Android's HDMI input device
(id 7, type 9), verified the actual routed device, and recorded stereo S16_LE
at 48 kHz. Normal HAL parameter `audio_devices_out_active=AUDIO_A2DP` caused
stock HAL to use Trident capture. No Bluetooth pairing was required for this
routing diagnostic. The app had RECORD_AUDIO, MODIFY_AUDIO_SETTINGS and
FOREGROUND_SERVICE permissions; no rooting, DAC permission changes, direct DSP
writes or Android system-partition changes were needed.

Trident card 4/device 0 was RUNNING, period 480 frames, buffer 1,920 frames.
All other observed capture streams were closed. Hardware and application
pointers advanced. Bridge SPI 115 increased from 617 to 3,327 between samples
(delta 2,710); AudIf SPI 113 remained zero. HAL logs report input prescale
0.334966, consistent with the captured tone amplitude near 2,100 counts.

During proven capture (`audio/a2dp-app-0/audio-registers.txt`):

| Register | Value |
| --- | --- |
| AudIf status 06146000 | 00000000 |
| AudIf mask 06146004 | 003007d2 |
| AudIf W1C event 06146008 | 00000000 |
| AudIf SPDS status 06146010 | 00000000 |
| SPDI1 control 06146034 / 06146038 | 90000000 / 00003000 |
| SPDI1 status 0614603c | 00000000 |
| Ostream0 start / end | 00004000 / 00004fff |
| Ostream0 block / config | 00000040 / 00002207 |
| Bridge global IRQ / mask | 00000001 / 00000010 |
| Bridge IRQ status / stream sync | 000003cf / 00000000 |
| AudioTop 0614a000 / 0614a00c | 00000700 / 011a5e00 |
| Bridge address-high 06142044 | 00000000 |

DSP words 0130 and 801a were not sampled live. This does not establish a
particular live DSP selector or DTVOUT-to-SPDI wiring. Offline stock HAL
execution (`hal-route-selection.json`) selects Sound_Connect(0x8f) for HDMI
source 1/A2DP sink 3, and 0x89 for speaker sink 1. The exact HAL binary hash
is recorded there. Calls to Sound_Connect are intercepted at entry; this
recovers branch intent without pretending a dummy context fully initializes
the hardware.

`routes-8f-bd.json` decodes the hashed preset: 0x8f uses the processing graph;
0xbd is the alternate direct I2SIN1-to-DTVOUT1 route.
`capture-init-code.json` executes Sound_Path_Init and Sound_Path_Connect(0x8f)
with explicit hardware/timing stubs. Initial DTVOUT1 sources are processing
outputs 0x9009/0x900a, selector 0130=696a, DTV channel 0. Input interface
9600 is enabled, format 01800000 is configured, and input prescale is set to
32. `capture-graph-selected-words.json` folds selected writes with explicit known
bit masks for comparison against cold Linux defaults. These are code-derived
settings, not live measurements or permission
to replay every emulated initialization write.

## Controls and failed access methods

With the same app's preferred HDMI input but `AUDIO_SPEAKER`, the HAL captured
codec card 0 instead. This produced DC/noise without the test tones despite
Android reporting an HDMI routed device. See `tone-analysis.json`,
`tone-capture.pcm`, `app-tone-hal-log.txt`, and `app-tone-state-{0..3}.txt`.
Nonzero data alone is therefore insufficient to establish capture success.

Direct shell TinyALSA access was denied, and shell AudioRecord was rejected by
AudioPolicy even after attribution fixes. Shell AudioSystem parameter writes
returned 1 and did not reach the HAL; those attempts left speaker mode unchanged.
The app with the ordinary audio permissions solved both access problems.
These failed attempts are retained as evidence, not recommended recipes.

Audible stock speaker playback left internal codec I2S RXCNT zero, FSTA 100,
and ISTA zero, matching the silent Linux split trial. See `tone-state-{0..3}.txt`
and their audio snapshots. RXCNT incrementing is not a valid prerequisite, and
zero does not prove missing I2S clocks. Likewise zero SPDI status or zero AudIf
interrupts does not prove that HDMI-to-memory capture is impossible.

## Stock bridge code comparison

`stock-ostream-config.asm` is the exact stock snd_alsa_trid.ko disassembly.
Function audbrg_ostream_config (text 3ba8) constructs CONFIG from the stored
mode shifted by 12, channel argument shifted by 8, another argument shifted
by 11, and stored field +14 shifted right by 4. The mode argument is bounded
to 0..2 before storage. Stock observed CONFIG is 2207; our previous Linux
probe used 3207, which differs in this mode field. The mode's semantic name
has not yet been recovered; the mismatch is real. Start/end and block registers
encode byte addresses and sizes shifted right by 4 (instructions 3c48, 3c64,
3c74). Thus 4000..4fff represents a 64-KiB region at physical 40000; use
Linux's allocated private DMA address, never this stock literal address.
The existing Linux block setting 1 KiB produces register 40, matching stock.

## Cleanup and boot restoration

The app released AudioRecord and restored `AUDIO_SPEAKER` with return code 0,
then verified the speaker query. Both codec and Trident captures were confirmed
closed and the temporary app `com.h713.hdmicapture` uninstalled successfully.
See `completion.json` and `sink-after-a2dp.txt`. Temporary tools remain under
/data/local/tmp/cap; no system files were replaced.

The exact saved Linux SPL has now been restored at LBA16 and verified after
a physical cold boot. Full Linux U-Boot and vendor boot0 hashes also match
the saved backups (`fel-return-verified.json`). The installed kernel FIT was
copied read-only and matches the host FIT, SHA256
`a298eeb8c131aa045c94279c2e89de73dcec3091173fff8d4fa0d25e948d399b`.
At the earlier Android switch, vendor boot0 was installed at LBA16. Before the switch, all 64 sectors read back exactly, vendor copy at
LBA256 and complete Linux U-Boot at LBA4828160 checked unchanged, and exact
current Linux SPL/U-Boot backups were saved here. See `boot-preflight.json`
and `vendor-switch.log`. No kernel/rootfs/Android partition or boot environment
was modified.

Return requires physical FEL entry, then:

```
external/sunxi-tools/sunxi-fel -p spl build/out/h713-restore-spl.bin
```

This is a 64-KiB restoration program, not the 32-KiB SPL. Its payload at offset
28,732 matches the current saved SPL and its eGON checksum passes
(`fel-return-validation.json`). Do not regenerate it from another build.
Verify installed SPL and full U-Boot against these backups after returning.

## Next Linux work

1. Preserve the exact current boot artifacts and Claude's IR/suspend changes.
2. Correct the loaded DT IRQ order (bridge 115, AudIf 113) before bridge trials;
   source patch is fixed, the installed Linux DT is still old. Keep the probe's
   guard against a wrong DT. Use the corrected stock DSP ownership handshake.
3. Recover stock A2DP HDMI route calls offline; compare initialization and
   observed bridge config against Linux. Require tone-correlated PCM, not
   counters or nonzero samples alone, for success.
4. Run one bounded, reversible Linux capture trial with restoration evidence.

PLL reflash experiments and undocumented-window reads remain excluded.

## Linux resumed after verification

Linux is now running the exact preserved 6.18.38 kernel with IRQ cells
`<0 115 4 0 113 4>` changed only in a copied RAM DT. The installed FIT and
persistent environment remain unchanged. Guarded cold MIPS startup and source-3
transition passed, and Linux preparation verified source/canaries, MIPS response,
TVFE/TVCAP and four held clocks, and EDID clock. See `linux-return.json` and
`linux-return-*.log`.

The prior on-board worker reader expected a temporary audio-dispatch patch and
correctly rejected the restored normal trace. The matching host reader was
staged separately under /tmp/h713-linux-return and verified all patch words.
`prepare-source3.py --trace-reader` now permits selecting the matching verifier
without replacing older tools or weakening their guard. A bounded direct-route trial was subsequently run and restored; see
[Linux trial](../2026-10-08-linux-direct-capture/README.md).
The IRQ correction is lost on the next normal boot;
reapply it in RAM or correct the installed DT before a bridge IRQ trial.

The autoboot monitor sent spaces while waiting for physical cold boot. It was
stopped when the operator reached U-Boot, pending spaces cleared, and no
keypress monitor remains running.
