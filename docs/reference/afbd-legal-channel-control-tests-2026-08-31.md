# Legal AFBD channel-control probes on Linux, 2026-08-31

## Setup

The board was running our U-Boot-initialised 1280x720 display and the Debian
DECD test FIT.  The monochrome boot logo was visibly scanning out through AFBD
OSD channel 1 (`0x05600140`), DECD source 0 was repeating at approximately
60 Hz, and the stock chroma gain `0x05140508 = 0x144c0000` was still applied.

These probes followed the six-window cross-stack writability triage.  That
triage had written the deliberately illegal-looking value `0xdeadbeef` and
labelled several masked AFBD controls "readonly" when the value did not read
back.  The tests below use legal values captured from stock instead.

## Phase A: stock channel-0 control only

The stock control word was written to the otherwise idle channel and committed:

```
0x05600100 <- 0x83001901    read back exactly
0x05600104 <- 0x00000001    remained 1 for the full hold
```

After the hold, `0x05600100` was restored to `0x00010000`.  The operator saw no
visual change.

This is not an admissible visual negative: the channel-0 READY latch never
cleared, so the running pipeline did not service that commit.

## Phase B: stock encoding on the serviced logo channel

The stock disabled control encoding was applied to the channel currently
carrying the logo:

```
0x05600140 <- 0x83001900
0x05600144 <- 0x00000001    consumed immediately; read back 0
```

The logo disappeared and the panel became black.  Restoring
`0x05600140 = 0x03001901` and committing again restored the logo, with the
READY latch again consumed.

This is the positive control for the method.  It proves that `0x05600140`
accepts legal control encodings and that the visible channel responds to the
commit.  It also confirms that stock's `0x83001900` is a disabled-channel
encoding, not a selector that exposes DECD video.

## Phase C: all differing stock channel-0 descriptor words

All stock values that differ from our idle channel-0 descriptor were applied:

```
0x05600100 <- 0x83001901
0x05600108 <- 0x008000ff
0x0560010c <- 0x00ff0080
0x0560012c <- 0x00000021
0x05600104 <- 0x00000001
```

Every descriptor word read back exactly.  The READY latch nevertheless stayed
at 1 throughout the eight-second hold.  The values were restored to
`0x00010000`, `0`, `0`, and `0`; the latch remains set until a clean reboot.
The operator saw no visual change.

Again, the visual null is not evidence against the descriptor: the commit was
not consumed.

## Conclusions and correction to earlier notes

1. `0x05600100`, `0x05600108`, `0x0560010c`, `0x0560012c`, and
   `0x05600140` are writable with legal encodings.  The earlier `deadbeef`
   result means only that they reject or mask that arbitrary pattern.
2. Channel 1 is serviced in our U-Boot-initialised pipeline; channel 0 is not.
3. Stock Android's settled captures show the opposite-looking AFBD control
   state: channel 0 carries `0x83001901` and channel 1 carries `0x83001900`.
   That does **not** identify the serviced channel.  A follow-up no-op commit on
   stock left channel 0's READY at 1 across eight polls while channel 1's READY
   cleared immediately.  Both stacks therefore service channel 1 only.
4. These results do **not** show that either OSD channel is the missing DECD
   video gate.  Earlier committed stock tests found that toggling both OSD
   channel controls did not disturb playing video, while committing source 0
   did.  The immediate next question is which coupled OSD/LVDS initialization
   state makes a channel's READY latch serviceable, not another isolated AFBD
   control permutation.

The current Linux snapshot taken immediately afterwards has OSD0
`0x05248000..0x052481fc` entirely zero, OSD1 configured and open, and the
plane-specific LVDS state populated only on the channel-1 side
(`0x051c006c = 0x29000000`, `0x051c0070 = 0x000000ff`; channel-0
`0x051c0060..0x068` are zero).  The matching stock capture was subsequently
taken in [`stock-osd-lvds-coupled-2026-08-31.txt`](stock-osd-lvds-coupled-2026-08-31.txt).
It confirms the same serviced-bank topology and exposes a new active-path
difference at `0x051c006c` (`stock 0x39000000`, ours `0x29000000`).
