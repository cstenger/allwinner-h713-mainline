# Stock OSD/LVDS coupled-state result, 2026-08-31

The raw two-sample capture is
[`stock-osd-lvds-coupled-2026-08-31.txt`](stock-osd-lvds-coupled-2026-08-31.txt).
It was taken from idle stock Android through `/dev/hidtvreg`; OSD0, OSD1,
`0x051c0000..0x051c01ff`, and both AFBD channel descriptors were sampled twice
one second apart.

## The channel-service question

Stock's AFBD controls look opposite to ours:

```
                       stock          ours
0x05600100 ch0 ctrl    0x83001901     0x00010000
0x05600140 ch1 ctrl    0x83001900     0x03001901
```

That is not service status.  A safe no-op test rewrote each stock control to
its unchanged value, wrote 1 to its READY latch, and polled eight times during
a three-second hold:

```
channel 0, 0x05600104: 1 1 1 1 1 1 1 1; final 1
channel 1, 0x05600144: 0 0 0 0 0 0 0 0; final 0
```

Channel 0 is unserviced on stock just as it is on our U-Boot handoff.  Channel
1 consumes READY immediately even with stock's `0x83001900` control word.

The coupled blocks agree:

- stock OSD0 contains the `init_osd_plane` 1080p configuration literals, but
  `0x0524801c = 0`, so it is closed;
- stock and ours both have OSD1 configured/open at `0x0524c000`;
- `0x051c0060..68`, the channel-0 LVDS pair, is zero on both;
- `0x051c006c/70`, the channel-1 pair, is populated on both.

This preserves the direct old conclusion that channel 0 is not serviced.  It
also shows why AFBD control encodings cannot be treated as enable/status bits
without observing READY consumption.

## New active-path difference

The previous stock/Linux LVDS comparison captured only sixteen words
`0x051c0010..4c`.  The widened capture finds:

```
0x051c006c    stock 0x39000000    ours 0x29000000
0x051c0070    stock 0x000000ff    ours 0x000000ff
```

`0x051c006c` belongs to the serviced plane-1 table in `ge2d_dev.ko`.  Static
reverse engineering places writes to `0x051c006c/70` in the driver's
reset-vsync-delay sub-path.  No earlier causal test mentioned `0x39000000` or
this bit-28 delta.

The one-register stock test is now complete and causal.  During verified
playback, forcing `0x29000000` for eight seconds made the screen black for
those eight seconds; restore to `0x39000000` restored the picture.  PTS advanced
continuously from 93 through 101.  Full record:
[`lvds-006c-stock-causal-2026-08-31.md`](lvds-006c-stock-causal-2026-08-31.md).

The next test is the reverse transfer on the Linux DECD run.  Do not batch any
other widened-LVDS difference into it.

Two words changed between the one-second stock samples:
`0x051c0170` and `0x051c0174`.  Treat them as free-running status, not settled
configuration.
