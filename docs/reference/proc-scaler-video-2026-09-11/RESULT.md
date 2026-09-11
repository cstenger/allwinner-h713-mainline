# POSITIVE — the two-axis scaler at 0x05180000 IS on our video raster

2026-09-11. `proc-scaler-sweep.sh --engage` with `SWEEPS=1`, filmed
(`local/lcd-photos/test_82/IMG_0822.MOV`, 4K HEVC, 30 fps, 216 s) and measured
frame by frame rather than described.

**This is the first positive control on a scaler in this project.** Engaging
`0x05180000` grossly and repeatably changes the picture on the DECD video path.
Disengaging restores it.

## The measurement

Whole-frame mean luminance at 5 fps separates the two states cleanly — the
engaged state is a flat light field (mean ≈ 69), normal video is a dark field
with a bright face (mean ≈ 30). Threshold 53.

```
   from      to    dur  state
   41.4    54.4   13.0  normal      <- mpv takes the panel at 41.4 s
   54.4    71.2   16.8  ENGAGED
   71.2    78.8    7.6  normal
   78.8    95.8   17.0  ENGAGED
   95.8    98.8    3.0  normal
   98.8   110.4   11.6  ENGAGED
  110.4   116.2    5.8  normal
  116.2   119.2    3.0  ENGAGED
  119.2   188.2   69.0  normal
```

Full trace in [luminance-trace.txt](luminance-trace.txt); contact sheets in
[contact-48s-118s.jpg](contact-48s-118s.jpg) and
[contact-116s-186s.jpg](contact-116s-186s.jpg).

## Why the durations identify the instances

Every engage is **nine separate `ssh` round trips**, and so is every restore and
every verify. Measured on the same link immediately afterwards: **0.62 s per
call**, 5.6 s for a nine-write sequence.

The picture breaks about three writes into the engage (bypass clear and both
ratios land first) and recovers only on the **last** restore write, because the
restore runs in reverse order and puts the bypass back last. So

```
broken ≈ (9-3)·r + [verify 9·r] + hold 2 s + restore 9·r
```

| window | predicted | observed | delta |
| --- | --- | --- | --- |
| instance 0, blink 1 (verified) | 16.9 s | **16.8 s** | −0.1 |
| instance 1, blink 1 (verified) | 16.9 s | **17.0 s** | +0.1 |
| instance 1, blink 2 | 11.3 s | **11.6 s** | +0.3 |
| instance 2, blink 1 (verified) | 16.9 s | **3.0 s** | **−13.9** |

Three windows land within 0.3 s of a model whose only free parameter was
measured independently. The fourth misses by fourteen seconds.

## What this says, instance by instance

- **Instance 0 — LIVE.** One blink, sustained 16.8 s.
- **Instance 1 — LIVE.** Two blinks, 17.0 s and 11.6 s, the second correctly
  shorter because it skips the readback verify.
- **Instance 2 — NOT on our raster.** Its engage produced a 3.0 s disturbance
  *while the nine writes were landing* and then the picture returned to normal
  and stayed normal for 69 s, through blinks 2 and 3. A transient during a write
  sequence is not the same thing as a sustained change under a held
  configuration.
- **Instance 3 — never ran.** The raster re-check aborted first.

## The effect is NOT a clean 2x downscale

Compare [normal-t74.jpg](normal-t74.jpg) with [engaged-t86.jpg](engaged-t86.jpg),
twelve seconds apart with the camera untouched.

Engaged, the panel shows a **flat light-grey field** with the picture crushed
into a narrow vertical sliver hard against the **right edge**, full height. Not
a half-size picture in the corner — a gross horizontal collapse with the content
displaced right.

So the block is unambiguously in the path, but `in 1280x720 / out 640x360 /
ratio 0x8000` is not a configuration the rest of the pipeline agrees with. The
ratio and the geometry are being consumed; something else downstream still
expects 1280 columns.

## This also explains yesterday's "negative"

The 2026-09-10 stills were taken **after mpv fell back to software decode into
the primary XR24 plane**, which reaches the panel through the RGB/OSD route. That
route does not pass through this scaler, so the picture looked normal with all
four instances engaged. Both observations are consistent, and the earlier
correction was right to restrict that result to the RGB raster.

> The RGB/OSD raster does **not** traverse `0x05180000`. The DECD video raster
> **does**.

## What this retires

- **"We inject downstream of the whole WCE chain."** Refuted for this block. Our
  DECD raster demonstrably passes through the proc stage's scaler.
- **The 2026-09-10 negative**, already restricted to the RGB path, is now
  positively explained rather than merely doubted.

## Next

The question is no longer *whether* this block scales our raster but *what
configuration produces a correct picture*. Concretely:

1. Sweep `ratio_h` alone with the geometry left at 1280x720 and `ratio_v` at
   unity. If the picture stretches or compresses horizontally in proportion,
   the ratio path is understood and only the geometry registers are wrong.
2. The right-edge displacement points at `0x0518002c[31:16]` (`node->0x30 + 4`)
   and `0x05180044` (`node->0x2c`), the two fields carrying 53 and 49 — offsets
   nobody has varied.
3. Instances 0 and 1 both being live is unexplained and worth a thought: the
   firmware's stage table names `proc-vs_upscaler` and `proc-vde_upscaler`, so
   two live instances may be the video-stream and video-decoder taps of the same
   picture.

Use instance 0 or 1 for any further work. Instance 2 is not in our path and
instance 3 is untested.
