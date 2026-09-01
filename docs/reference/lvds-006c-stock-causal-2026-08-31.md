# `0x051c006c` is causal on stock video, 2026-08-31

## Setup

Stock Android was playing the existing ten-minute moving clip through
`com.softwinner.TvdVideo/.TvdVideoActivity`.  Decoder logcat showed
`QueueBufferToShow` advancing once per second.  The operator was told the exact
test and hold duration, confirmed they were watching, and the write did not
start until that confirmation.

The widened coupled-state capture had found the first active-plane LVDS
difference outside the old sixteen-word sweep:

```
0x051c006c    stock 0x39000000    ours 0x29000000
```

## Test

Only that word was forced to the Linux value for eight seconds using
`hidtvreg-replay`, then restored automatically:

```
--- before ---
051c006c 0x39000000
--- replayed, holding ---
051c006c 0x29000000
--- restored ---
051c006c 0x39000000
051c006c 0x39000000
```

Playback remained valid throughout: decoded PTS advanced continuously from
93.000 through 101.000, with no `onCompletion`.

## Operator observation

> During those 8 seconds the screen was black

The blackout duration matched the forced-value window, and the register was
verified restored afterwards.

## Conclusion

`0x051c006c` is load-bearing for stock video output, and the cross-stack bit-28
difference (`0x39000000` versus `0x29000000`) is causal.  This is the first
settled static difference shown to remove a verified playing picture rather
than merely perturb or flicker it.

The result does not yet prove sufficiency on Linux.  Our XRGB logo already
scans out with `0x29000000`, so bit 28 may enable a video-specific path or a
timing/reset-vsync-delay mode rather than the whole LVDS output.  The required
reverse test is one clean Linux boot with DECD repeating, write
`0x051c006c = 0x39000000`, verify readback, then make one bounded fmt-0 submit
while the operator watches.  Restore to `0x29000000` after the hold unless the
board becomes unreachable.
