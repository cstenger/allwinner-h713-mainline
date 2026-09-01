# `0x05140508[23:16]` is the colour enable, 2026-08-31

Isolated on stock Android during the vendor-boot session, by bisecting the
cross-stack diff down to a single register.

```
0x05140508     stock 0x144C0000     ours 0x14000000
                     ^^                    ^^
                  bits 23:16 = 0x4C     bits 23:16 = 0x00
```

**Writing our value onto stock makes the display greyscale.** Restoring stock's
value brings colour back. Reproduced at every stage of the bisection.

## How it was isolated

Seven rounds, each written through `/dev/hidtvreg` with
`tools/display/hidtvreg-replay.c`, verified by readback, held ~12–20 s, and
restored unconditionally:

| round | registers under test | result |
| --- | ---: | --- |
| full route block | 65 | greyscale |
| half A | 33 | greyscale |
| A1 | 17 | greyscale |
| B1 | 9 | greyscale |
| C1 (`05140700`/`704` alone) | 2 | **writes rejected — read-only** |
| D1 | 4 | greyscale |
| E1 | 2 | greyscale |
| **F1 — `0x05140508` alone** | **1** | **greyscale** |

## Why the observable got better mid-bisection

The first rounds were run against playing video and needed a decoded-frame count
inside each hold to be admissible. Then the effect was seen to grey the *menu*
with no video playing at all — it acts on the whole display output, not the
video layer. That removed the clip entirely: no playback, no frame counting, and
no `onCompletion` confound, which had already invalidated one round when the
clip ended mid-test and made it look as though the writes had killed the video.

**Correction carried from that round:** this was first described as breaking
colour "in the video path". Wrong scope. It greys the UI with no video present,
so it is a display-output-wide setting.

## Two symptoms pruned on the way

- **`0x050c0000` is entirely read-only.** Four addresses across the block all
  rejected `0xDEADBEEF` while `0x05000108` accepted it in the same run. Its 39
  differences are status output, not configuration — symptoms of the two stacks
  being in different states, not causes. An earlier replay attempt against this
  block wrote nothing at all and was void.
- **`0x05140700`/`0x05140704` are read-only too**, and they were the most
  dramatic-looking difference in the block (`0x00000EFF`/`0x00000FFF` against
  `0x035F035F`/`0x03980398`). Shape said "prime suspect"; the write probe said
  "cannot be a cause".

That gives a triage rule worth applying to the whole diff before spending any
more observations: **probe writability first. Writable is a candidate cause;
read-only is a symptom.**

## What this does and does not resolve

**Does:** a real, reproducible defect in our display configuration, in a
register no previous sweep ever captured — the eleven-window ROUTE window starts
at `0x05140050`, well above this. Our output is missing whatever `0x4C` enables.

**Does not:** explain why our panel shows *nothing* rather than greyscale video.
Stock with our value still shows a picture; ours shows none. So this is
necessary-looking but not sufficient, exactly as fmt 0 was. Do not treat the
video path as solved.

## Next

1. Write `0x144C0000` to `0x05140508` on our stack and re-test the DECD path.
   One register, and the state is reproducible (`h713_disp init 0x34`, DECD FIT).
2. Characterise the field: is `0x4C` a magic coefficient or does any non-zero
   value enable colour? One more stock observation would settle it, and it
   determines whether we hardcode `0x4C` or a bit.
3. Apply the writability triage to the remaining differences before spending
   further observations on them.
