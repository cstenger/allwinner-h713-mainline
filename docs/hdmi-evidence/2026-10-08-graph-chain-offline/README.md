# Route 0x8f data path: what the 13-word trial left unwired (offline, 2026-10-08)

Host-only analysis. No board access. Everything here is stock code intent from
emulation with hardware and timing stubs, not live DSP readback.

## Why the stock-graph trial produced frames of zeros

The 13-word `stock_graph` trial made the bridge run (IRQs 3029 -> 4684, whole
DMA buffer written) but every PCM byte was zero. Listing every
`MAPI_AUD_SetSourceSelectPort` call made by `Sound_Path_Init` and
`Sound_Path_Connect(0x8f)` (`route8f-connections.json`) gives the full stock
data path:

```
9600 (I2SIN1) -> 8400 -> 8500 -> 8f01 in2/in3 (mixer) -> 9009/900a (volume) -> 9500 (DTVOUT1)
   connect        init     init                          connect                init
```

The 13 words covered 9600 -> 8400 (0077) and 8f01 -> 9009/900a -> DTVOUT1
(8059/805a, 0130). They never wired **8400 -> 8500** or **8500 -> 8f01**, and
never set the 8f01 mixer gains for inputs 2/3. With those selectors at their
cold values the mixer gets no input. It still produces output frames at the
DSP rate, so they are zeros. That matches the trial exactly.

There is also a mute. Stock `Sound_Path_Init` ends by user-muting 9009/900a
(bit 15 of words 0059/005a). The HAL removes that mute only at runtime:
`Check_Sound_Unmute` -> `Sound_Set_Mute(path, false)` -> `Thal_Sound_Set`
-> `Sound_Path_SetAttr` -> `MAPI_AUD_DisableUserMuteByType(0xe)`
(`path-unmute.json`, `tools/stock/decode-path-unmute.py`). Linux's cold values
for 0059/005a have never been read.

## Exact words (`graph-edges.json`, `tools/stock/decode-graph-edges.py`)

Each call is run in isolation after `Init_Modules` in the exact stock
libmspdriver (SHA256 a03e6344...).

| Stock call | Word | Mask | Value |
| --- | --- | --- | --- |
| 8500.0/1 <- 8400.0/1 | 007c | ffff | 8081 |
| 8500.2/3 <- 8400.2/3 | 007d | ffff | 8283 |
| 8500.4/5 <- 8400.4/5 | 007e | ffff | 8485 |
| 8f01.2 <- 8500.0 | 8102 | 00ff | 0086 |
| 8f01.3 <- 8500.1 | 8103 | 00ff | 0087 |
| SetMixer(8f01, out0, in2, 0x20) | 0102 | ff00 | 2000 |
| SetMixer(8f01, out1, in3, 0x20) | 0103 | 00ff | 0020 |
| DisableUserMuteByType(0xe), path 8f | 0059, 005a | ffc0 | 0000 (mute = 8000) |

The same isolated runs reproduce all the already-known words: 0077=1617,
8059=7c, 805a=7d and 0130=696a. Mixer inputs 0/1 of 8f01 come from 9402, not
HDMI, and are deliberately left alone.

The full folded stock state after init + connect + unmute touches 137 device-0
words. The 22 words here are only the HDMI data path. If the 22-word run still
gives zeros, the next places to look are module enables and coefficients on
8400/8500, and the global words 0002/0004/0008.

## Prepared probe change (built, not yet run)

`modules/hdmi-dsp-probe`: the new load-time parameter `graph_chain=1` makes
`stock_graph` apply 22 words: the original 13 plus the 9 above, with the
unmute last as in stock. Without it, behaviour is exactly the recorded
13-word trial. The same save/verify/reverse-restore and failure latch apply.
Saved values are logged before any write, so the run also records Linux's cold
values for all nine new words. Build against the exact running kernel with
`tools/hdmi/build-dsp-probe.py` (verified: 22-entry table in the compiled .ko).

Success is still only tone-correlated PCM in the private DMA buffer (L 1 kHz,
R 2 kHz). Bridge IRQs and non-sentinel bytes alone do not count.
