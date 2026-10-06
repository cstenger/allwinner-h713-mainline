# Read-only HDMI audio status probe

`h713-hdmi-audio-probe` is a deliberately small diagnostic module for the
first HDMI-input audio experiment. It does not register an ALSA card, request
an interrupt, allocate DMA, read FIFO/data ports, acknowledge IRQs, change a
clock rate, or write any audio register.

The module reads only recovered AudIf and AudBrg status/control words. It
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

This module is an investigation tool, not a production audio driver. Never
autoload it.
