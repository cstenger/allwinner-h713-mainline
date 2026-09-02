# H713 audio bring-up

Started 2026-09-01. Read out of the **stock DTB**
(`local/stock-boot/sunxi.fex`, decompiled) and the mainline tree — no hardware
has been touched yet, and nothing has made a sound.

**Most of the DT groundwork already existed** and was rediscovered rather than
found: `sun50i-h713.dtsi` already carries `codec@2030000` with the stock
register layout, the vendor tuning properties, and the speaker GPIO correctly
resolved to PL2 on r_pio, with a comment warning it is not PB2 on the main pio.
Check the dtsi before repeating that work. The genuinely new finding is the
mainline driver fit below, which contradicts the dtsi's own comment that
"mainline does not have this driver yet".

## What is actually populated — answered

The roadmap recorded this as an assumption: "it is a projector with speakers, so
a codec and amp should be there, but that is an assumption until someone looks
at the board or gets a sound out of it."

The stock DTB settles the first half. Stock **enables** the internal codec:

| node | status |
| --- | --- |
| `codec@2030000` `allwinner,sunxi-internal-codec` | **okay** |
| `sound@2030330` `allwinner,sunxi-codec-machine` | **okay** |
| `dummy_cpudai@203032c` | **okay** |
| `daudio@2032000`, `daudio@2033000` | okay |
| `daudio@2034000` | disabled |
| `owa@2036000` (S/PDIF) | disabled |

So the speaker path is **internal codec → power amp → speakers**. No external
I2S codec, and S/PDIF is off. That is a much smaller job than "bring up audio".

## The speaker amp, from the stock codec node

```text
gpio-spk       = <0x18 0x00 0x02 0x00>;   phandle 0x18 = r_pio (pinctrl@7022000)
spk_used       = <0x01>;
pa_level       = <0x01>;                  amp enable is ACTIVE HIGH
pa_msleep_time = <0xa0>;                  160 ms settle after enabling
speaker_vol    = <0x1a>;                  26
headphone_vol  = <0x00>;                  headphone unused
digital_vol    = <0x00>;
```

**The GPIO is on `r_pio`, not the main `pio`** — bank 0 of r_pio is PL, so this
is **PL2**, active high. The dtsi already encodes this correctly as
`gpio-spk = <&r_pio 0 2 GPIO_ACTIVE_HIGH>`; the decode above merely confirms it
independently from the stock blob. The 160 ms settle is the vendor's own value
and is worth honouring; amp enable pins usually pop if driven without one.

Related caution from elsewhere in this project: **PB5 is the backlight/fan
enable and must never be held low for long** (see `backlight-investigation.md`).
Confirm PL2 has no such shared duty before driving it in a loop.

## Mainline fit — the new finding

The dtsi comment says "Mainline does not have this driver yet, but keep the real
register layout documented here instead of fake H6/A23 assumptions." Keeping the
layout was right. The premise is now out of date.

`sun4i-codec.c` already handles `allwinner,sun50i-h616-codec`, and H616
(sun50iw9) is the near relative of H713 (sun50iw12). The register blocks look
like the same block relocated:

| | H616 mainline | H713 stock |
| --- | --- | --- |
| base | `0x05096000` | `0x02030000` |
| length | `0x31c` | `0x32c` |
| extra range | — | `0x02031000` len `0x7c` |

16 bytes apart on a ~800-byte block. The second H713 range is probably the
analog part; mainline has `sun50i-codec-analog.c` if a separate node is needed,
but H616 gets by with one range, so try one first.

**The clocks and reset already exist in our CCU** — this was the expected
blocker and it is not one:

```text
CLK_PLL_AUDIO        139     stock "pll_audio"
CLK_AUDIO_CODEC_DAC   88     stock "codec_dac"
CLK_AUDIO_CODEC_ADC   89     stock "codec_adc"
CLK_BUS_AUDIO_CODEC   90     stock "codec_bus"
CLK_BUS_AUDIO_HUB     87
RST_BUS_AUDIO_CODEC   42
```

H616's node names them `apb` (CLK_BUS_AUDIO_CODEC) and `codec`
(CLK_AUDIO_CODEC_1X); H713 has no `_1X`, so `codec` most likely maps to
`CLK_AUDIO_CODEC_DAC`. Stock also lists a `pll_tvfe` clock on the codec, which
is unusual and unexplained — note it, do not copy it blindly.

Stock's IRQ for the codec is SPI 25 (`interrupts = <0 0x19 4>`, on the
`sndcodec` machine node rather than the codec node). DMA is channel 7 on the
`#dma-cells = <1>` controller.

## Architecture note: do not port the vendor shape

Stock uses a three-node vendor architecture — `sunxi-internal-codec` plus a
`sunxi-dummy-cpudai` that owns the DMA plus a `sunxi-codec-machine` that ties
them together. Mainline's `sun4i-codec` is self-contained: it registers its own
DAI and sound card. So the `dummy_cpudai` and `sndcodec` nodes have no mainline
equivalent and should not be recreated. Take the register base, clocks, reset,
DMA channel, IRQ and the speaker GPIO from stock; take the structure from
mainline.

## First experiment

Enable the codec with the H616 compatible and see whether it probes and
registers a card. That is a DT-only change and it fails cheaply — a probe error
in `dmesg` costs nothing and tells us whether the register layout is compatible
before any driver work is contemplated.

Success looks like: the driver probes, `/dev/snd/*` and an ALSA card appear,
`aplay -l` lists a device. Sound is a separate question and needs the PL2 amp
enable, which is deliberately not part of the first step.

If it probes but is silent, the likely candidates in order are the amp GPIO,
the analog block at `0x02031000`, and the `codec` clock mapping.

## RESULT: card works, one register diverges from H616

Patches 0082 (H616 compatible) and 0083 (`allwinner,audio-routing = "Speaker",
"LINEOUT"`) get most of the way:

- `sun4i-codec` binds to `2030000.codec`; card 0 "H616 Audio Codec" with
  `pcmC0D0p`; mpv opens the PCM (`AO: [alsa] 44100Hz mono 1ch s16`);
- DAPM powers the output and **the speaker amp asserts** —
  `gpio-2 (allwinner,pa) out hi` once `Line Out Playback Switch` is on. The DT,
  the GPIO, the driver's event handler and the DAPM graph all work.

**Blocker: `DAC Playback Switch` cannot be set, and the reason is hardware.**
It accepts a write with no error and reads back 0. So does a direct
`devmem` write. The control that makes that meaningful:

```text
0x02030310 (DAC analog control)   0x0015000F
  ALSA sets Line Out ON           0x0015280F   bits 13+11, exactly LINEOUTx_EN
  ALSA sets Line Out OFF          0x0015000F
0x02030314 (H616 DAC_AC_MIXER)    0x00000000, and will not take 0x00220000
```

The block is live and writable at 0x310; 0x314 is dead. The vendor driver's own
register map says why — **H713 has no register at 0x314**:

```text
0x300 ADCL   0x304 ADCR   0x310 DAC   0x318 MICBIAS   0x320 BIAS   0x324 HP
```

H616 places `DAC_AC_MIXER_REG` at 0x314; H713 jumps 0x310 to 0x318. Writes to a
register that does not exist are dropped silently, which is exactly what was
observed. This is the project's writability-triage method again: a register that
will not take a write cannot be the cause.

**So the H616 compatible is close but not correct.** The next step is an H713
variant in `sun4i-codec` that drops the DAC_AC_MIXER controls and the Left/Right
Mixer widgets, routing DAC to LINEOUT directly. Verify against the vendor driver
whether H713 has a mixer stage at all before assuming it is merely relocated.

Do not just hunt for the mixer at another offset without checking that: the
vendor map has no obvious candidate, which suggests the stage is absent rather
than moved.

## SOUND — 2026-09-01

Patch 0084 adds an H713 variant to `sun4i-codec` that drops the mixer stage and
the ramp controller, routing the DACs straight at the line-out mux. Card 0
becomes `h713-audio-codec`, and the falsifiable prediction held: **`DAC Playback
Switch` disappeared from the control list**, having no register left to live in.

A 440 Hz tone is **audible**. The register confirms the whole chain:

```text
0x02030310 = 0x0015E87F   DAC_LEN + DAC_REN + LINEOUTL/R_EN
                          + differential select + volume 31/31
0x02030310 = 0x0015000F   idle, for comparison
gpio-2 (allwinner,pa) out hi   amp asserts on playback
```

**Operating notes worth keeping:**

- **`Speaker Switch 0` releases the amp immediately.** Turning off `Line Out
  Playback Switch` and waiting does not — `use_pmdown_time` holds it up. Use the
  pin switch to power the amp down.
- The controls needed for sound are `Speaker Switch 1`, `Line Out Playback
  Switch 1 1`, and a non-zero `Line Out Playback Volume`. All default to
  off/zero, so a fresh boot is silent by design.

## Open: it is quiet, and the route is not the reason

Loudness barely changed between `Line Out Playback Volume` 15/31 and 31/31, and
an A/B of Stereo against Mono Differential — switched mid-tone, two passes —
produced no audible difference. The operator's reading is that this board has a
**single speaker**, so differential drive gains nothing if it is wired
single-ended, and that is more convincing than any register explanation.

`DAC Playback Volume` is already at maximum: its control is declared with
`invert = 1`, so 63 means zero attenuation.

**Corrected: the codec is NOT the limit, and the headphone-path lead was wrong.**
`speaker_vol` does not live at 0x324. The vendor driver writes all three volumes
into registers we already drive:

```text
speaker_vol    -> SUNXI_DAC_REG (0x310) bits [4:0]   == mainline's
                  SUN50I_H616_LINEOUT_VOL, i.e. "Line Out Playback Volume"
headphone_vol  -> SUNXI_DAC_REG (0x310) bits [30:28]
digital_vol    -> SUNXI_DAC_DPC                      == "DAC Playback Volume"
```

So "Line Out Playback Volume" *is* the vendor's speaker volume. Comparing what
each stack actually programs:

| | stock | ours |
| --- | --- | --- |
| digital | 0x00 | ALSA 63, invert=1 -> reg 0, same |
| speaker | 0x1a (26) | 31, louder than stock |
| headphone | 0x00 | 0 (read back in 0x0015E87F) |

We drive the codec harder than the vendor does. The vendor driver also has no
GPIO or regulator beyond gpio-spk, so there is no second amp enable being
missed.

**Therefore the quietness is downstream of the SoC** -- the external amplifier
or the speaker itself. Register work will not fix it. The cheap next checks, in
order:

1. **Was stock Android loud on this board?** If it was not, there is nothing to
   fix and this is simply how the unit sounds. Nobody has compared.
2. Someone looking at the board: what the speaker is wired to, whether the amp
   has a gain-select pin, and whether its supply rail is up.

## Not yet established

- **Nothing has been heard yet.** The amp asserts, but with the DAC path open
  the mixer switch is unsettable, so no audio has reached it.
- **Nobody has looked at the board.** The codec being enabled in the stock DTB
  is strong evidence but not proof that the amp and speakers are fitted.
- Whether the second reg range at `0x02031000` is required.
- What `pll_tvfe` is doing on an audio codec.
- Whether PL2 has any shared duty, as PB5 does.
