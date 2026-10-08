# Audible HDMI split test: silent, and the DSP I2S link never clocked

Date: 2026-10-08. Same boot as `../2026-10-07-pll-byte-read` (live MIPS still
carries that profile's SetAPLL retry; stock DSP patch loaded, versions 1/1;
route 0xbd, HDMI unmute and I2SIN1 enable already applied by the DSP probe).
No U-Boot, kernel or firmware change.

## What was applied

`modules/hdmi-speaker-split` (SHA256
`7325a88f5b6c79592046864c49f24b84b7d6a448b341756e458316bae7f0e845`):

- DSP route 0x89 as stock's audible HDMI speaker path: 0077=1617, 0118=7c7d,
  0020=2e2f; 8017 bit0 clear (unmuted); 0012 bit15 set (I2SIN1). All read back.
- Codec internal I2S at 0x02031000: the stock init recovered from the vendor
  kernel (0xc08320a0, 21 writes) plus the I2S half of the stock
  `DAC Src Select = I2S` put (0xc0831e2c: CTL bits 17/18 clear, bit 1 set).
  Result CTL=00000013, FMT0=00081f55, CLKD=00000184, CHCFG=11, TX0CHSEL=10003,
  RXCHSEL=10000, RXCHMAP3=100. Linux had never configured this block
  (CTL was 00060010, GEN off; formats at reset).
- At lock, DAC_DPC bits 30 and 29 set (DAC half of the same put): e0000000.

The module does not use the 0x02031078 "owner" word the older DSP probe
writes: that address is in this internal-I2S block.

## Result

`run-split-test.py` timeline in `run.log`. The 500 Hz control beep through the
normal Linux path was heard. Receiver locked 1280x720 state 5 at 6.2 s; the
host played 16 s of 48-kHz stereo tone with aplay rc 0; receiver cached
N 6144 / CTS 74250 and PLL history 6144/48000 throughout.

**The operator heard silence after the beep, with one click or pop** (most
likely the DAC source switch). Internal-I2S RXCNT stayed 0, ISTA 0 and FSTA
0x100 in every sample before and during the tone: the codec's I2S receiver
got no samples at all, not even silence, so the DSP side never drove the link
in this configuration.

## Interpretation

This does not show where HDMI audio stops. It shows the DSP's I2S output to
the codec is not running under our init, so the speaker test cannot see the
receiver-to-DSP leg yet. Candidates, cheapest first:

1. The DSP output interface (module 0x9a00, edge 8d00 -> 9a00) needs its own
   MAPI_AUD_EnableInterface bit, as I2SIN1 needed 0012 bit15. Recover it
   offline with the existing Unicorn tooling.
2. Stock graph setup beyond selectors (Sound_Path_Connect, Init_Modules,
   volumes / prescale) is required before the DSP produces output.
3. Clock mastership: stock's put leaves the codec I2S as slave; if the MSP
   output also expects to be slave, nobody drives BCLK/LRCK.

Cleanup restored every DSP word and codec register (`cleanup.log`); MIPS
answered `help win`.
