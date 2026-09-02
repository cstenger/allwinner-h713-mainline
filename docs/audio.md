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

## LOUD — the speaker is on the headphone amplifier

The quietness was not the external amp and not the codec's gain. **The speaker
is driven from the HEADPHONE amplifier, and HP_AMP_EN was never set.**

What made that visible was a deliberately large A/B rather than more reading.
Line Out Playback Volume 6/31 against 31/31 is indistinguishable by ear; DAC
Playback Volume 20 against 63 likewise; stereo against mono differential,
switched mid-tone over two passes, likewise. The registers were provably
changing throughout -- `0x310` reads `0x0015E80F` at line-out volume 15 and
`0x0015E87F` at 31.

**Controls that verifiably move the right register bits while having no audible
effect mean the speaker is not on that output.** That is the whole inference.

```text
0x324 = 0x80800C44   HP_EN_L and HP_EN_R set, bit 15 HP_AMP_EN CLEAR
0x324 = 0x80808F8C   vendor's word: HP_AMP_EN + bits 3, 7, 8, 9  -> LOUD
```

Written mid-tone, the change was immediate and obvious.

### Two earlier conclusions this corrects

- **"The codec is not the limit, the quietness is downstream -- the amplifier or
  the speaker."** Wrong. It was the codec, in a stage nobody was driving.
- **The headphone-path lead, which was then retracted.** The retraction was
  wrong in an interesting way: `speaker_vol` really does live at `0x310[4:0]`,
  so the reasoning that killed the lead was sound -- but the *speaker* is on the
  HP amp regardless, so the original hunch was right for a reason I had not
  found yet. Correct reasoning, wrong conclusion.

Both null results above were **correct data pointing at a wrong assumption**,
not failures. They are only confusing if you assume the output is LINEOUT.

### Patch 0085 — VERIFIED on hardware 2026-09-02

0085 adds an `HP Amp` DAPM supply widget toggling `HP_AMP_EN`, with `LINEOUT`
depending on it. All three open checks are now answered, on a board running the
exact kernel built from the series (`/proc/version` timestamp matched the build,
and the series digest matched the cached tree).

**1. The amp follows playback.** Idle `0x324 = 0x80800C44` and `gpio-2 out lo`;
during a tone `0x324 = 0x80808C44` (bit 15 set) and `gpio-2 out hi`; afterwards
both return low.

Read this one carefully, because the first sample said the opposite. Sampling
3 s after the stream stopped showed the amp still up, which looks exactly like
"the widget never powers down". It is not: the component sets `use_pmdown_time`,
and ASoC's default `pmdown_time` is 5000 ms. **Sample later than the power-down
delay, not just "after the event".** A second read well past it showed a clean
idle. Writes to `0x324` made directly by hand are also cleared by the widget's
`POST_PMD` path, so DAPM wins over manual pokes.

**2. Volume controls work, and the volume law is roughly as specified.**
Measured with a microphone recording, per-segment level by complex demodulation
at the tone's own measured frequency:

```text
DAC Playback Volume   63      0.00 dB   (reference)
                      59     -3.50 dB   (4 steps, 4.64 dB predicted)
                      55     -7.81 dB
                      51    -12.27 dB
```

Steps of 3.50, 4.31 and 4.46 dB against a specified 4.64 dB: the law converges
to spec as level drops and compresses about 1 dB at the very top, which is what
a small speaker driven hard does. An earlier run measured 18.4 dB against a
predicted 18.56 dB between raw 16 and 32 -- consistent, and taken lower down the
range where there is no compression.

**3. `HP_AMP_EN` alone is right, but not for the recorded reason.** A synchronised
A/B at fixed DAC volume measured the full vendor word `0x8F8C` at **-0.10 dB**
against bit 15 alone, with the run's own repeatability (an identical segment
repeated 30 s later) at **0.25 dB**. So the extra undocumented bits deliver **no
measurable gain**. Keeping bit 15 alone is still correct -- fewer undocumented
bits touched -- but the claim that the vendor bits "only raised gain" is wrong
and has been corrected in the patch header.

The same recording settled `Line Out Playback Volume`: 31 against 0 measured
**+0.21 dB**, inside the drift. It genuinely does nothing on this speaker, which
is consistent with the speaker being on the HP amp rather than on LINEOUT.

### 0086 — a control-list rewrite, built and correctly abandoned

A build exists (`h713-kernel-audio-0086.fit`) giving H713 its own control list,
identical to H616's except that `DAC Playback Volume` is declared with
`invert = 0` instead of `1`. It was dropped without a record; the final build
went back to the previous source. Dropping it was right, and the reason is
measurable in one step:

```text
control 63  ->  DAC_DPC (0x02030000) DVOL field = 0x00
control  0  ->  DAC_DPC              DVOL field = 0x3F
```

DVOL is an *attenuation* field and the TLV declares 64 steps of 1.16 dB from
-73.08 dB, so the inherited `invert = 1` is correct: ALSA 63 is 0 dB. With
`invert = 0` the control would put maximum attenuation at maximum volume. No
listening required -- two register reads rank it.

## The audio clock is wrong: everything plays 4.8 % slow

Found 2026-09-02 while measuring the volume sweep, from a detail that had
nothing to do with volume: **the 440 Hz test tone came back at 418.97 Hz**,
stable to 0.01 Hz across every segment. That is -84.8 cents, nearly a semitone
flat, and it means all audio plays about 4.8 % slow.

The chain, all measured:

```text
hw_params                      rate: 44100 (44100/1)
audio-codec-dac  (playing)     43,000,000 Hz
audio-codec-dac  (48 kHz!)     43,000,000 Hz   <- unchanged
pll-audio-base                172,000,000 Hz
0x02001078                     0x280B5501  -> N=86, M=12, 24 MHz*86/12 = 172 MHz
```

**The module clock does not respond to the requested sample rate at all.**
`sun4i_codec_hw_params` calls `clk_set_rate(clk_module, ...)` -- 22 579 200 for
the 44.1 kHz family, 24 576 000 for the 48 kHz family -- and both leave the
clock at 43 MHz. The call returns 0, so nothing reports an error.

The cause is one missing flag in the CCU:

```c
/* drivers/clk/sunxi-ng/ccu-sun50i-h713.c */
static SUNXI_CCU_GATE(audio_codec_dac_clk, "audio-codec-dac", "pll-audio-2x",
                      0xa60, BIT(31), 0);
                                       ^ no CLK_SET_RATE_PARENT
```

It is a bare gate. With no `CLK_SET_RATE_PARENT`, `clk_set_rate` cannot
propagate to `pll-audio-2x` (which *does* carry the flag) or to the PLL, so it
rounds to the current rate and returns success. `pll-audio-base` therefore keeps
whatever value it booted with -- 172 MHz, which is not an audio rate and is
almost certainly a leftover.

### The divisor, and why the CCU table already knows the answer

Two nominal rates, one stuck clock, gives two independent points and pins the
divisor exactly:

```text
nominal 44100  ->  418.97 Hz measured   (440 * 41992/44100 = 418.97)
nominal 48000  ->  384.93 Hz measured   (440 * 41992/48000 = 384.93)
```

Both fit `actual_rate = audio-codec-dac / 1024 = 43e6/1024 = 41 992 Hz` to
0.01 Hz. So this codec divides its module clock by **1024**, and needs

```text
44100 * 1024 = 45 158 400        48000 * 1024 = 49 152 000
```

`audio-codec-dac` is `pll-audio-2x`, which is `pll-audio-base / 4`. The required
PLL rates are therefore 180 633 600 and 196 608 000 -- **and both are already in
`pll_audio_sdm_table`**, as its two largest entries. The CCU port is right about
the divisor chain; nothing can currently reach those entries.

### Proven on hardware, without a rebuild

Poking the PLL by hand to the table's own 180 633 600 entry (N=22, M=3, SDM on,
pattern `0xC001288D` -- `0x02001078 = 0x29021501`, `0x02001178 = 0xC001288D`)
and restoring `0x280B5501` afterwards:

```text
44.1 kHz, PLL as found     418.97 Hz    -84.8 cents
48   kHz, PLL as found     384.93 Hz   -231.5 cents
44.1 kHz, PLL poked        440.00 Hz      0.0 cents
```

**Exactly on pitch.** The diagnosis is complete and the fix is confirmed before
any driver change was written.

### What the fix has to do

Two things, not one -- adding the flag alone would make it *worse*:

1. `audio_codec_dac_clk` (and `audio_codec_adc_clk`) need `CLK_SET_RATE_PARENT`.
2. The H713 codec variant must request **rate x 1024**, not the shared
   `sun4i_codec_get_mod_freq`'s rate x 512. With the flag added but the request
   left at 22 579 200, the PLL would be driven to 90 316 800 (also in the table),
   `audio-codec-dac` would land on 22 579 200, and playback would run at
   22 050 Hz -- half speed.

## Not yet established

- **Nobody has looked at the board.** The codec being enabled in the stock DTB
  and a speaker that audibly works make this academic for playback, but the
  physical amp and speaker fit is still inferred rather than seen.
- Capture is untouched: only `pcmC0D0p` exists and `dmas` is tx only. ADC,
  HDMI-in audio and the `daudio` I2S blocks have had no work.
- Whether the second reg range at `0x02031000` is required.
- What `pll_tvfe` is doing on an audio codec.
- Whether PL2 has any shared duty, as PB5 does.
- Whether the ~1 dB of compression at the top of the volume range is the
  speaker, the amp, or a codec stage. It does not matter for correctness.

## Method notes from this round

- **A tone is a measurement instrument, not just a stimulus.** The clock bug was
  invisible to every register check and fell out of the *pitch* of a recording
  taken to measure loudness. Record the frequency even when you only care about
  the level.
- **Two operating points beat one.** Testing 48 kHz as well as 44.1 kHz turned
  "the clock looks wrong" into an exact divisor, because one stuck clock across
  two nominal rates over-determines the arithmetic.
- **Check the power-down delay before concluding a widget is stuck on.**
- **A silent `clk_set_rate` return of 0 is not evidence it worked.** For a clock
  with no rate ops and no `CLK_SET_RATE_PARENT`, the framework rounds to the
  current rate and reports success.
- **Pick measurement steps against the noise floor you will actually have.** The
  first sweep used 18.5 dB steps into a room with 18 dB of headroom, so two of
  six segments were unmeasurable. The second used 4 dB steps and all six landed.
