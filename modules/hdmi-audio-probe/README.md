# Bounded HDMI audio status probe

`h713-hdmi-audio-probe` is a deliberately small diagnostic module for the
first HDMI-input audio experiments. It does not register an ALSA card, request
an interrupt, allocate DMA, read FIFO/data ports, acknowledge IRQs, or start a
stream. Its default mode does not write any register.

The module reads only recovered AudIf, AudBrg, and audio-top status/control
words. It
requires all three explicit acknowledgements because `0x0614xxxx` must not be
accessed on an ordinary boot:

```sh
insmod h713-hdmi-audio-probe.ko \
  armed=1 live_source3=1 receiver_powered=1 snapshot=1
```

Before loading, verify the guarded U-Boot source-3 trace, a live MIPS shell,
and active TVFE/TVCAP holds with `tools/hdmi/prepare-source3.py
--postboot-only`. The five audio clocks are obtained through the H713 CCU
provider. Gates already on are treated as inherited and are not refcounted,
which prevents module removal from switching off a gate left on by U-Boot.
Any gate found off is enabled through CCF and restored to off on removal.

Take later snapshots by writing a strictly increasing sequence number:

```sh
echo 2 > /sys/module/h713_hdmi_audio_probe/parameters/snapshot
```

Each snapshot is one parseable `dmesg` line beginning
`h713-hdmi-audio-probe: snapshot=`. The intended first test compares silence,
GPU LPCM playback, and post-playback snapshots. Use
`tools/hdmi/run-audio-status-trial.py`; it performs the source-3 preflight and
stages the canonical 256-byte EDID probe explicitly (so an older specialty
probe on the target cannot be selected accidentally). It leaves the audio
probe loaded. A cold power cycle is the normal teardown after a live receiver
experiment.

`activate_spdi1=1` applies the two control words produced by the stock capture
device 0 path for 48-kHz LPCM: `0x00003000` to `0x06146038`, followed by
`0x90000000` to `0x06146034`. The ordering and values come directly from the
stock `AudIf_spdi_Run`/`AudIf_spdi_activate` disassembly. Both original words
are saved and restored on removal. The experiment intentionally leaves the
AudIf IRQ status, mask, and route registers untouched, so no interrupt can be
delivered and no W1C status is acknowledged. It also leaves the audio bridge,
DMA, and FIFO/data registers untouched.

Any option that writes an audio register requires the separate
`h713-hdmi-tvfe-hold` module to be loaded first. The trial runner enforces this
with `--tvfe-hold-module`; it also checks MIPS liveness after the stock-order
TVFE setup and before loading this probe. A demod-bus-only experiment used the
wrong power order and hard-hung the board, so this prerequisite must not be
bypassed.

After an all-zero read-only baseline, `init_audio_top=1` opts into only the
three-write audio-top clock sequence confirmed directly in the stock
`snd_alsa_trid.ko` `audio_top_clk_init` disassembly. The original control and
configuration words are saved before the first write and restored during
module removal. This option still does not enable an IRQ, configure SPDI,
touch a stream/FIFO register, or start DMA.

`stock_audio_ihb=1` opts into one additional reversible CCU write. It saves
the audio-IHB clock word at `0x02001d50`, writes `0x81000002`, verifies the
readback, and restores the original word during removal. This exact word was
captured from the stock system in both idle and live-HDMI states. On the
current guarded boot the other two audio-core words already match stock, but
audio-IHB is `0x80000007`; therefore this option deliberately changes no
other CCU register. Use it with `init_audio_top=1` only as a bounded hardware
experiment.

This module is an investigation tool, not a production audio driver. Never
autoload it.
