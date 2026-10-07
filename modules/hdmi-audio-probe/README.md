# Bounded HDMI audio status probe

`h713-hdmi-audio-probe` is a deliberately bounded diagnostic module for the
first HDMI-input audio experiments. It does not register an ALSA card and its
default mode does not write any register. Explicit options can reproduce the
stock audio-top, SPDI1, and Audio Bridge setup in reversible phases.

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

Each status snapshot begins with one parseable `dmesg` line containing
`h713-hdmi-audio-probe: snapshot=`. A DMA-enabled probe adds
`bridge_snapshot=` and `dma_snapshot=` lines. The intended test compares
silence, GPU LPCM playback, and post-playback snapshots. Use
`tools/hdmi/run-audio-status-trial.py`; it performs the source-3 preflight and
stages the canonical 256-byte EDID probe explicitly (so an older specialty
probe on the target cannot be selected accidentally). It leaves the audio
probe loaded. A cold power cycle is the normal teardown after a live receiver
experiment.

`activate_spdi1=1` applies the two control words produced by the stock capture
device 0 path for 48-kHz LPCM: `0x00003000` to `0x06146038`, followed by
`0x90000000` to `0x06146034`. The ordering and values come directly from the
stock `AudIf_spdi_Run`/`AudIf_spdi_activate` disassembly. Both original words
are saved and restored on removal.

`open_spdi1=1` additionally reproduces the stock `AudIf_spdi_Open` sequence.
It requires `activate_spdi1=1`, owns DT interrupt index 1, clears only the
SPDI1 W1C bits (`0x00300052`), writes route value `0x400`, and enables those
mask bits. Its handler acknowledges only owned SPDI1 events. The saved mask,
route, and controls are restored before the IRQ is released.

`configure_audbrg=1` requires `open_spdi1=1`. It allocates a private coherent
64-KiB DMA buffer, owns Audio Bridge DT interrupt index 0, and reproduces stock
output stream 0: 1024-byte blocks and config word `0x00003207`. The exact word
comes from `Thal_Alsa_Audio_Capture_Start(0)` passing `(0, 0, 2, 2)` through
`Trid_Audio_Output_SPDIF_Input` into `audbrg_ostream_config`; it must not be
shortened to `0x2207` by dropping the live `r2` argument.

Audio Bridge setup is deliberately split by `audbrg_stage=`:

1. resolve (but do not request) the IRQ and allocate/fill DMA, with no
   bridge-register writes;
2. program the upper address nibble and inert stream start/end/block/config;
3. log and clear pending status, request the stock-style `IRQF_ONESHOT`
   threaded handler, then enable output-stream-0 and global bridge IRQ bits;
4. toggle the stock stream flush/start bit.

The fail-safe default is stage 1; hardware investigation must advance one cold
boot at a time and request later stages explicitly. Every stage prints a
boundary message before its first write. A
combined stage-4 load hard-hung the initial test boot before its log could be
retrieved. A serial-instrumented stage-1 retry then stopped immediately after
clock discovery and before audio-IHB setup, isolating the fault to the eager
hard-IRQ request that used to precede DMA setup. The stock driver instead uses
a threaded one-shot handler and acknowledges all 14 bridge status bits. The
probe now defers that exact interrupt shape to stage 3, so it must not be
advanced without serial capture. Removal disables
the source first, masks owned interrupts, synchronizes both handlers, restores
every touched register, and frees coherent DMA.

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
