# H713 handoff — audio finished, HDMI input opened

Session of 2026-09-02. Two threads: **audio playback, which is done**, and
**HDMI input, which is not** but went from unmapped to a well-characterised
subsystem with one clearly identified blocker.

Deeper detail: [audio.md](audio.md), [hdmi-in.md](hdmi-in.md).

**Board state on handoff: HUNG.** The last experiment (patch 0090) hard-locked
it. It needs a **power cycle**, then it boots the 0090 FIT; the previous kernel
is backed up on the board under `/root/fits/replaced-*.fit`.

---

## 1. DONE — audio playback is correct and verified

Patches **0082–0086, all in series**. Card 0 `h713-audio-codec` via an H713
variant of mainline `sun4i-codec`.

| | |
| --- | --- |
| pitch | 440.01 Hz at nominal 44.1 kHz, 440.00 Hz at 48 kHz (was 418.97 / 384.93) |
| volume law | −3.50 / −7.81 / −12.27 dB for DAC 59/55/51 vs 63, spec 4.64 dB/4 steps |
| amp | `0x324` bit 15 and `gpio-2` follow playback, release after `pmdown_time` |

Three things that were wrong and are now right:

1. **The speaker is on the HEADPHONE amp**, not LINEOUT. `Line Out Playback
   Volume` provably does nothing (+0.21 dB across its range).
2. **Bit 15 alone is correct** — the full vendor word measured −0.10 dB against
   it, inside the run's 0.25 dB repeatability. The earlier claim that the extra
   bits "raised gain" was wrong.
3. **The audio PLL never left its 172 MHz boot value**, so everything played
   4.8 % slow. `audio_codec_dac_clk` was a bare gate with no
   `CLK_SET_RATE_PARENT`, so `clk_set_rate` rounded to the current rate and
   **returned 0**. Patch 0086 needs BOTH the flag AND `mod_freq_mult = 2` —
   this codec divides by 1024, not the shared table's 512. The flag alone is
   *worse* than the bug (half speed).

**Open on audio:** capture only. `dmas` is tx-only; ADC, HDMI-in audio and the
`daudio` I2S blocks are untouched.

---

## 2. HDMI input — mapped, blocked on HPD

Full detail in [hdmi-in.md](hdmi-in.md). The short version.

### Solved

- **The power gate.** Every HDMI-RX window is behind TVFE/TVCAP, both off at
  boot; access to them hard-locks the SoC. Patch **0087** attaches PPU domains
  1 (TVFE) and 2 (TVCAP) and enables the TV clocks — narrowly, with no
  interrupt and no GPIOs. After it the whole HDMI-RX space is reachable.
- **The register map**, confirmed by scanning: `rx` at `0x05000000`, `phy` at
  `0x05040000`, `thdmirx` at `0x050c0000`, plus wrapper windows at
  `0x06800800` and `0x06840000` (which aliases every `0x800`).
- **A writable EDID interface** at `rx+0x50/0x54` (`EDID_CTRL`/`EDID_DATA`),
  unlike the thdmirx DMA bank which is dead.

### The blocker: HPD

`SCDC_CONFIG.HPDLOW` only *forces HPD low*; clearing it does not drive the pin
high. The only known HPD drive is `0x07091014`, and **reading it hard-locks the
board** — twice now.

Eliminated: `bus-r-cpucfg` (patch 0090, tested, refuted — the read still hung
with the clock held).

**The hypothesis that now fits everything:** that register is not
ARM-addressable at all. Stock drives it from ARISC firmware, the peer notes
ARISC writes it without raising a GIC IRQ, no device tree describes the block,
and the only ARM-side lever the R_CCU exposes is now eliminated.

### Dead ends — do not re-run these

- **ARISC EDID sub-commands.** A full protocol exists (`UpdateEDID 0x0111`,
  `RequestEDID 0x0315`, ...) and the handlers behind dispatcher `0x12490` all
  return `status=-3`, **hollow by design**. Stock uses the direct path.
- **thdmirx EDID port at `+0x4424`.** Outside the backed register file — the
  window is only ~`0x0d00` bytes. Ruled out at both access widths, and against
  global enable, reset, port-select and wrapper init.
- **`0x050c0400/0500/0600` as per-port EDID RAMs.** They are register banks; no
  EDID header, repeating `00 C1 D1 04`.

---

## 3. Where the next session should focus

**Decide the HDMI question before spending boots on it.** There are two routes
and they diverge sharply in cost:

1. **Close the ARM-side question** — one more experiment: deassert
   `RST_BUS_R_CPUCFG` (the ARISC held in *reset* rather than unclocked; the
   R_CCU exposes it and nothing has touched it) and read `0x07091014` again
   from inside the driver with the flushed marker. One boot, possibly one power
   cycle. If it hangs, ARM-side is closed definitively and route 2 is the only
   option.
2. **Go where stock goes** — running ARISC firmware, reached over
   msgbox/rpmsg. Much larger, but it is what the hardware actually does, and
   `PullHotPlug 0x0211` in the documented protocol is exactly the HPD lever.

**Recommendation: do 1 first.** It is bounded, it is the last cheap thing, and
its outcome determines whether route 2 is optional or mandatory.

**If HDMI stalls, the highest-value work elsewhere is audio capture** — the
codec is up and proven, so the ADC is a much shorter path than anything in
HDMI, and it closes the audio subsystem entirely.

Also still open from the previous session, unrelated and untouched here:
**mpv cannot use the video plane** (needs an ffmpeg/mpv with the `v4l2request`
hwaccel emitting `AV_PIX_FMT_DRM_PRIME`; userspace only, no kernel work).

---

## 4. Method notes that cost real time

- **Check `pm_genpd_summary` and `clk_summary` before the first access to any
  new window.** Both are free and would have predicted the first hard-lock. A
  read is only safe when the target block is known to be powered.
- **Some blocks here are byte-wide and word access lies about them.** Word
  reads of `0x0680xxxx` return zeros where byte reads return data; word writes
  vanish where byte writes stick. The clue was that the vendor driver uses
  `writeb()` and never `writel()`. `mmio-rw` now has `rb`/`wb`/`db`.
- **Scan before theorising.** Five separate causes were tested one at a time
  for the dead EDID port; one scan showed the address was outside the backed
  register file and retired all of them at once.
- **Name and flush before a risky access.** Every probe prints "about to READ
  <addr> — if this is the last line, ..." before touching a new window. That is
  the difference between a refuted hypothesis and a silent board.
- **Check what your instrument can actually show.** Every "EDID does not work"
  result was measured through a host GPU that could not have reported success,
  because HPD was never asserted. The measurement was incapable of a positive
  before the experiment began.
- **A register accepting a write proves it is backed, not that it is wired to
  anything.** `SWENABLE` sticking meant nothing; it was in the wrong register
  file entirely.
- **A tone is a measurement instrument.** The audio PLL bug was invisible to
  every register check and fell out of the *pitch* of a recording taken to
  measure loudness.

## 5. Standing hazards added this session

- **`0x07091014` hard-locks the board.** Twice. Do not read it again without a
  new, specific reason — and never from `mmio-rw`, only from inside a driver
  with a flushed marker so a hang is attributable.
- Be precise about the range: `0x07090000` is the **RTC** (`reg` length
  `0x400`), driven by our kernel and fine. It is `0x07091000` specifically.
- **Do not enable the vendor `sunxi-tvtop` driver.** Its node claims
  `GIC_SPI 110` — the interrupt the KMS display driver owns for AFBD — and
  carries `panel_bl_en = <&pio 1 5 ...>`, which is **PB5, the backlight and fan
  enable**.
- **Do not give the MIPS the AFBD block.** It would remove the NV12 KMS plane
  the drmprime mpv path targets and force a bespoke client. Treat the MIPS as a
  frame producer writing into a buffer we scan out.
