# The two-axis scaler at 0x05180000 — NEGATIVE on our raster

2026-09-10, operator watching, photographed before and after. Cold-booted board,
MIPS parked, kernel 6.18.38.

## What was run

`tools/display/proc-scaler-sweep.sh --engage` was started and interrupted
partway. The interruption is what produced the cleanest possible experiment: the
script got through its engages on **all four instances** and never reached the
restore, so the board sat in the fully-engaged state while a photograph was
taken, and was then restored for a second photograph with **nothing else
changed**.

Engaged state, read back from the board (`engaged-all4.txt`), identical on all
four instances:

```
+0x00  0x0F006000    H phase 0x6000
+0x08  0x43008000    H ratio 0x8000, integer phases preserved
+0x14  0x00000000    bypass CLEARED
+0x2c  0x00350280    out_w 640
+0x30  0x00010168    out_h 360
+0x34  0x050002D0    in 1280x720
+0x38  0x0010C000    V phase 0xC000
+0x3c  0x00008000    V ratio 0x8000
+0x40  0xC0000280    out_w 640
```

Ratio `0x8000` is exactly one half on both axes.

## The result

**No change.** In both photographs the face spans about **30% of the lit
rectangle's width** and **~55% of its height**. Had the block been acting on our
raster, the engaged shot would have shown it at half linear size — a quarter of
the area.

Measurement caveat, stated plainly: the camera moved between the two shots, so
absolute sizes are not comparable and the comparison is of **ratios internal to
each photograph**. Those agree to within a few percent. That is nowhere near a
factor of two, so the conclusion survives the imprecision — but a repeat with a
fixed camera would be stronger.

**Frames were flowing.** The face is in a different pose between the two
photographs — mouth and eyes differ — so this was live video advancing, not a
frozen buffer being rescanned.

## What the run did establish

- **The block accepts writes with the MIPS parked.** All four instances read
  back engaged. Not gated, unlike the wall `0x05000000` hit.
- **Restore is exact.** All four instances returned byte-for-byte to the values
  read twice today and in the 2026-08-31 capture.
- **The whole proc stage was in the firmware's own configured state.** Not just
  the scaler: the route block `0x05140000` reads `0x104 = 0x05000000`,
  `0x108 = 0x02D00000`, `0x114[31] = 0` — exactly what `ProcWinNode::WriteReg`
  writes. So this was not a case of a half-configured stage.

## The pattern across three blocks, which is now the real finding

| block | what it is | result on our raster |
| --- | --- | --- |
| `0x05000000` | NR/composition — **no scaler at all** | n/a |
| `0x051c0120` | panel down-scaler, **vertical only** | negative, stage on |
| `0x05180000` | proc scaler, **two-axis** | negative, bypass cleared |

Three independent blocks, each tested with its own bypass or enable correctly
handled, each already sitting in the state its own firmware node produces, and
each inert on our raster.

**The unifying explanation is that we inject downstream of all of them.** Our
driver enters at AFBD (`0x05600000`) and takes output at the LVDS selector
(`0x051c006c`). The entire WCE chain — NR → DETN → Proc → Panel — and every
scaler in it sits in a path our raster never traverses. That hypothesis was
raised for `0x05000000` on 2026-09-04 and has now been independently confirmed
twice more.

> Continuing block-by-block is the wrong next move. Three nulls with three
> correct bypass handlings is no longer evidence about individual blocks.

## The next question, and it is static

**What does `0x051c006c` select between, and where do its sources come from?**

If both the RGB/OSD source and the DECD video source enter downstream of the
proc stage, that closes the whole WCE scaler family at once — and the only way
to use any of them is to drive the window pipeline, which
[status.md](../../status.md) already costs as a much larger port than mapping
one more register window.

That is disassembly, not board time, and it should be answered before another
run is spent.

## Aside worth keeping

While video was visibly live on the glass, DRM reported
`plane[38] video-0  crtc=(null)  fb=0` and only the OSD plane attached. The AFBD
path scans independently of DRM's plane accounting — the same "unbound is not
quiesced" behaviour noted on 2026-09-04. Do not use the DRM plane state alone to
decide whether video is reaching the panel.
