# The proc upscaler works with geometry set — the composite route is viable

2026-09-12, one operator turn at the panel. Settles the last unvalidated
hardware fact in the composite 1080p->720p route, which
[ROUTE-COMPARISON.md](ROUTE-COMPARISON.md) priced but could not confirm.

**Result: PASS.** The clipping seen in every earlier run was the untouched input
geometry, exactly as predicted. Both halves of the composite route are now
hardware-confirmed.

## What was programmed

Instance 0 at `0x05180000`, with the 1280x720 test card on the DECD video plane.
Gates verified before any write *and again after*, so the configuration was
applied to a demonstrably live raster:

```
0x34 = 0x03c00220   input window  960x544      (was 0x050002D0 = 1280x720)
0x2c = 0x00350500   out_w  1280                (unchanged, already correct)
0x30 = 0x000102D0   out_h  720                 (unchanged, already correct)
0x08 = 0x4300c000   ratio_h 0xC000  -> 1.3333x magnification
0x3c = 0x0000c16c   ratio_v 0xC16C  -> 1.3235x magnification
0x00 = 0x0f007000   H phase 0x7000  = (unity + ratio_h) >> 2
0x38 = 0x0010e0b6   V phase 0xE0B6  = (unity + ratio_v) >> 1
0x14 = 0x00000000   bypass CLEARED
```

Every write read back correctly. Restore afterwards was byte-for-byte identical
to the pre-run block across all nine registers.

## Reading the photograph

The operator's photograph was supplied in-session and not filed under
`local/lcd-photos/` (which is ignored anyway); what follows is the reading of
it, and the observations are the record. The block was asked to magnify the
*top-left 960x544 window* of a 1280x720 card to fill the panel, so a correct
result shows
75% of the card's width and 75.6% of its height, edge to edge. The card is
self-measuring, and all four independent scales agree:

| what | observed | predicted |
| --- | --- | --- |
| top ruler (card spans 0-9 over 1280 px) | reads 0..6, partial 7 at the right edge | ends at 6.75 |
| left ruler | reads down to 3 at the bottom edge | ends at 3.0 |
| circles (5 across the card) | 3 full + 1 half visible | 3.75 |
| circle shape | round, not oval | H and V differ by 0.7%, imperceptible |

**The absent right and bottom borders are correct, not clipping.** Those edges
live at x=1280 and y=720 in the source, outside the 960x544 input window. Any
input window smaller than the source necessarily loses the far edges — that is
what a window *is*.

### Why this is not the old failure

The distinction matters, because "borders missing" is superficially what the
failures looked like too. The earlier runs produced:

> a flat light-grey field with the picture crushed into a narrow sliver hard
> against the RIGHT edge ... content sits inside a hard-edged rectangle,
> straight vertical/horizontal cuts, flat grey outside

Here the magnified content **fills the entire output** — no grey field, no
interior hard-edged rectangle, no sliver. The picture is uniformly magnified
across the whole panel. Those are different phenomena, and the difference is the
one register this run changed.

So the standing hypothesis from
[the ratio ramp](../proc-scaler-ratio-ramp-2026-09-11/RESULT.md) and
[the block's field map](../two-axis-scaler-found-2026-09-10.md) is confirmed:
the clip window was `0x34`. The block had been told its input was 1280x720 while the ratio said
magnify, so it magnified a 1280x720 window and showed the part that fitted.

## Caveats, stated plainly

- No frame grab was taken, so this rests on a photograph read by eye. The
  observations above are categorical rather than metric, which is what makes
  that acceptable here.
- The photograph is **keystoned** (shot off-axis), so it cannot measure the
  magnification factor precisely. What it measures is categorical — which ruler
  digits are present, how many circles, round vs oval, filled vs grey-fielded —
  and those are unambiguous. A precise factor would need an on-axis shot or a
  frame grab, and is not what this test was for.
- This validates the **geometry and ratio** behaviour at the sizes the composite
  route needs. It does **not** exercise a real 960x544 source: the input was a
  window onto a 1280x720 framebuffer, because `kms-nv12-plane-test` hardcodes
  1280x720 and the KMS driver rejects other sizes. The configuration is the
  same, but a genuine 960x544 framebuffer has not been scanned out yet.

## Two false negatives found in the harness itself

Both were in code that had never been executed before this run, and both would
have read as "the hardware refused the write":

1. **Case-sensitive readback comparison.** `busybox devmem` prints uppercase
   hex; `printf '0x%08x'` emits lowercase. The first `set` aborted reporting
   `0x05180030 <- 0x000102d0 reads 0x000102D0 *** DID NOT STICK` — the write had
   landed perfectly. Only values containing `a`-`f` were affected, which is why
   the preceding register passed.
2. **Unmasked V-phase write.** `(unity + unity) >> 1 = 0x10000` does not fit the
   16-bit phase field. The firmware leaves `0x38[15:0]` at **0**, which is that
   value truncated — so the formula is right, but `restore` would have written
   `0x00110000` where `0x00100000` belongs. Caught by comparing the live block
   against the formula before running, not after.

Both are fixed. The lesson that generalises: a harness that has never run is
itself untested, and its first failure is more likely to be its own than the
hardware's.

## Where the route stands now

| stage | status |
| --- | --- |
| VE 1920x1088 -> 960x544, power-of-two | hardware-confirmed ([RESULT.md](RESULT.md)) |
| proc upscaler 960x544 -> 1280x720 | **hardware-confirmed, this run** |
| cedrus: secondary output as the V4L2 capture buffer | **not written** |
| KMS: accept 960x544, program the upscaler from atomic_update | **not written** |

Both hardware halves are now proven. What remains is entirely software, and the
two pieces are described in [ROUTE-COMPARISON.md](ROUTE-COMPARISON.md) — the
cedrus side is the risky one, because redirecting the primary reconstruction to
internal buffers means keeping every DPB reference pointer aimed at them, and
that is what makes decoding correct at all.

Worth keeping in view: this route costs ~8.5 dB against the arbitrary-ratio path
and delivers 56% of the panel's samples. It is viable, it is the only no-GPU
option, and it is not good.
