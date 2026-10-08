# HDMI-in audio: review findings and plan

Date: 2026-10-08. Written by Claude for the agent continuing the HDMI audio
capture work (`~/.codex/worktrees/hdmi-capture-current/h713`, plus the
uncommitted `docs/hdmi-evidence/2026-10-07-*` and `modules/hdmi-dsp-probe/` in
the main checkout). Everything below marked **verified** was checked against
stock binaries, stock device trees, live Android captures or a hardware run;
everything marked **hypothesis** was not.

## 1. Where things stand

The receiver side works on Linux: canonical EDID, 1280x720 lock, N 6144 /
CTS 74250, and with the live SetAPLL retry the PLL history reads 6144/48000.
The DSP patch loads (versions 1/1) and selectors write and read back.
Nothing has ever arrived in ARM memory: no SPDI1 status, no AudIf or bridge
interrupt, the 64-KiB sentinel unchanged.

**The reason no bridge trial could succeed: SPDI1 status never moves.** Its
stock interrupt handler (`AudIf_spdi_Interrupt`) runs a lock state machine
off status bits that set when a stream arrives. All of them stayed zero in
every trial, so no stream ever reached SPDI1. Every check in those trials
(DMA sentinel, bridge IRQ, AudIf IRQ) is downstream of that point and could
not have shown anything. Stop running bridge/DMA trials until something
upstream of SPDI1 is shown to carry audio.

## 2. Findings that change the approach

### 2.1 The Android baseline never exercised capture (verified)

The audible Android trial used the **speaker** path, which never touches ARM
memory:

HDMI RX -> MSP DSP I2SIN1 (route 0x89, `HDMI2PCM_MIXED_TO_S`) -> DSP I2S out
(edge 8d00 -> 9a00) -> codec internal I2S at 0x02031000 -> codec DAC with
`DAC Src Select = I2S` -> speaker.

Evidence: HAL log `output_route: media-speaker-i2s`; vendor
`audio_mixer_paths.xml` path `media-speaker-i2s` sets `DAC Src Select = I2S`;
the Android register snapshot (`2026-10-07-android-audio/tone-steady/`) shows
SPDI1 controls and bridge output stream 0 all zero and every ALSA capture
stream closed.

So the chain being rebuilt (route 0xbd -> DTVOUT1 -> SPDI1 -> bridge ostream 0)
**has never been observed working**, and DTVOUT1 -> SPDI1 is an inference
from names. SPDI also handles IEC 61937 burst preambles
(`AudIf_spdi_ExtractFormatFromPc`), so its input may be the HDMI receiver
directly rather than the DSP. Unknown until a stock capture is observed.

### 2.2 Bridge and AudIf interrupts are swapped in our DT (verified)

| Block | Stock | Our patch 0024 / probe |
|---|---|---|
| Audio Bridge | SPI 115 (0x73), DT index 0 | SPI 113 |
| AudIf ("abp dtv") | SPI 113 (0x71), DT index 1 | SPI 115 |

Evidence: three stock DTBs (`local/stock-boot/sunxi.dts:1069` and two
others) list `<0 0x73 4 0 0x71 4>`; stock `AudBrg_Init` calls
`platform_get_irq(pdev, 0)` and `ABP_DTV_Init` index 1; live Android
`/proc/interrupts` names 115 "audio bridge irq" and 113 "abp dtv irq".
`patches/kernel/0024-...board.patch:763` has the comment and order reversed.

This is not why there was no data (status registers read directly were also
zero). It likely explains the early hard hang on mapping "bridge interrupt 0"
(really AudIf, with status pending, while the handler cleared bridge status).
Once data flows, each handler would acknowledge the wrong block and the level
interrupt would storm. **Fix before any further bridge trial.**

### 2.3 The DSP probe's ownership handshake uses the wrong addresses (verified addresses; effect is a hypothesis)

`modules/hdmi-dsp-probe/h713-hdmi-dsp-probe.c:480` maps 0x02031078 ("user
owner") and 0x02032078 ("kernel owner"), and writes 0x55 to the first around
every command. Per the stock DT, 0x02031000/0x7c is the codec's second
register window, the **internal I2S** (`INTER_I2S_*` register names in the
vendor kernel), and 0x02032000/0x7c is `daudio0`. The 0x50 being "restored"
is just that I2S register's contents.

Stock `snd_alsa_trid.ko` uses `WaitDSPFree`/`ReleaseDSP`: wait while
0x05001530 == 0x55, write 0x55 to 0x05001534 to claim, 0xAA to release. Both
addresses also appear in the MIPS firmware's data. The probe never takes this
lock, which may explain the flaky DSP command timeouts (0x0130 completion,
the device-1 version timeout that voided the word-access trial). Before
touching 0x05001530 from ARM, confirm it is powered (`pm_genpd_summary`,
CCU), per the 0x07091000 rule.

### 2.4 Linux never configured the codec's internal I2S (verified, run on hardware)

On Linux, INTER_I2S CTL reads 0x00060010 (global enable off) and the format
registers sit at reset. The stock init is vendor kernel function
`0xc08320a0` (21 writes); the `DAC Src Select` put is `0xc0831e2c`. Both are
transcribed in `modules/hdmi-speaker-split/h713-hdmi-speaker-split.c`.

### 2.5 Smaller corrections (verified)

- `0x06146008` is not a route register. In `AudIf_spdi_Interrupt` it is a
  W1C event register (bit 0x400 = SPDI1 event, cleared by writing 0x400).
  Reading 0 is correct.
- PLL byte reads match the stock Init model except byte lane 1: +1 reads
  0x06 where 0x66 is written, +5 reads 0x00 where 0x10 is written. Neither the
  README nor its corrections mention this. These bytes have never been read
  on stock. Possibly self-clearing bits; unverified.
- `audio-cpu`/`audio-umac`/`audio-ihb` are modelled as plain AHB gates, so the
  100 MHz Linux reports is meaningless. Stock words: d48=0x80000002,
  d4c=0x80000002, d50=0x81000002. IHB matches on Linux; read
  0x02001d48/0x02001d4c once to close the other two.

## 3. Hardware result from 2026-10-08: the split test

Evidence: `docs/hdmi-evidence/2026-10-08-speaker-split/`.

Applied route 0x89 (0077=1617, 0118=7c7d, 0020=2e2f), HDMI unmute, I2SIN1
enable, the stock internal-I2S init, and at lock `DAC_DPC` bits 30+29. All
DSP words read back. Control beep through the normal path was heard. During
16 s of locked 48-kHz HDMI tone the operator heard **silence (one click)**,
and internal-I2S RXCNT stayed **0** before and during the tone.

Meaning: the DSP never drove the I2S link to the codec, not even with
silence. This does **not** yet say whether HDMI audio reaches the DSP. It says
the DSP output side is not running under our setup. Everything was restored;
MIPS stayed responsive.

## 4. Plan

Ordered so each step has an observable that can fail. Do not proceed past a
step whose exit check has not been met.

### Step 1: make the DSP drive its I2S output (offline first, then one run)

Goal: internal-I2S RXCNT increments after the speaker route is applied, with
or without HDMI input.

1. **Offline.** With the existing Unicorn harness (`decode-sound-route.py`,
   the `MAPI_AUD_EnableInterface` emulation used for 0012 bit 15), recover
   the interface enable for the output module **0x9a00** and for every other
   module on route 0x89 (8400, 8700/8701, 8d00, 8f01). Then trace what stock
   `Sound_Path_Connect(0x89)` does beyond the six selector writes: interface
   enables, `Init_Modules`, `Set_Path_In_Prescale`, volume, mute. The HAL log
   shows it runs path connect, then volume, DRC, surround, balance, gains,
   PEQ and prescale before unmuting.
2. **Offline.** Determine I2S clock mastership: which side drives BCLK/LRCK
   between DSP output 9a00 and the codec internal I2S. Stock's put clears CTL
   bits 17/18 (codec slave). Check whether a DSP word makes the MSP side
   master.
3. **Hardware, one run.** Re-run `modules/hdmi-speaker-split/run-split-test.py`
   with the recovered writes added. Exit check: RXCNT climbs. Then the
   operator's ear answers whether HDMI audio reaches the DSP:
   - **Tone heard:** receiver, PLL, I2S into the DSP and the DSP are proven.
     The capture problem is purely DSP -> memory. Go to Step 2.
   - **RXCNT climbs but silence:** the DSP outputs but receives nothing.
     The break is receiver -> I2SIN1 (receiver audio output, I2S clocks from
     the PLL, I2SIN1 format). Investigate there; the PLL lane-1 bytes
     (2.5) become relevant.

Operator steps need their own turn: announce, wait for "ready", then run.

### Step 2: take a stock capture baseline on Android

Goal: observe stock moving HDMI audio into memory, and record exactly how.

- With HDMI1 selected and audible, run a capture on card `TridentALSA`
  (card 4) devices 0 and 1. Stock has no `tinycap`/`tinymix`, so push a
  static arm32 build. Do it twice: with the HAL's route as is (0x89), and with
  capture route 0xbd applied.
- Better still, make the HAL capture on its own: route Android's output to a
  sink the DSP cannot reach (A2DP headset or a USB audio device), so
  AudioFlinger must pull HDMI audio through memory.
- Snapshot during capture: SPDI1/SPDI2 registers, bridge output streams 0
  and 1, AudIf mask/status, AudioTop, DSP selector 0x0130 and 0x801a, codec
  INTER_I2S, `/proc/interrupts` lines 113 and 115, and whether capture data
  is non-zero.
- Exit check: stock capture data is non-zero and the register set that
  carried it is recorded. If stock capture through the Trident card is silent
  too, that device is not the HDMI capture path, and the search moves to the
  `daudio`/codec capture paths (codec `ADC Dest Select`, internal I2S RX).

Only then rebuild the Linux capture path, diffing against that baseline.

### Step 3: fix before any further bridge or SPDI trial

- Swap the Audio Bridge / AudIf interrupt order in patch 0024 and the probe
  (bridge = SPI 115, AudIf = SPI 113).
- Replace the 0x02031078/0x02032078 handshake with stock's 0x05001530/34
  lock (after a power-domain check), or drop it; never write 0x55 into the
  internal I2S again.
- Read 0x02001d48/0x02001d4c on Linux once (expect 0x80000002).

### Step 4: cheap cross-checks against stock

- Read PLL bytes 0x06880000..0x06880010 on stock during audible playback
  with the same byte-read method, and compare lanes +1 and +5 with Linux.
- Record stock INTER_I2S register values during audible playback, to confirm
  the init transcription in `h713-hdmi-speaker-split.c`.

## 5. Stop doing

- No more Audio Bridge / SPDI1 / DMA trials until Step 1 or 2 shows audio
  upstream of SPDI1.
- No more U-Boot-reflash PLL experiments until Step 1 shows the break is
  between the receiver and the DSP. Each costs a power cycle and has not
  produced an observation point.
- Do not treat the speaker baseline as a capture baseline.

## 6. Safety rules still in force

- Never read 0x07091000, 0x0694xxxx or other undescribed windows; check
  `pm_genpd_summary` and the CCU before the first access to any new window.
- MIPS is launched only from U-Boot after a physical cold start; never live
  from Linux.
- Restore the exact original U-Boot after any temporary candidate and verify
  the full region plus SPL.
- Never write Speaker Switch 0 (mute via DAC volume); never hold PB5 low.
