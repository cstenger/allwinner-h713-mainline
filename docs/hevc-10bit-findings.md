# 10-bit HEVC on the H713 — what is true, measured 2026-08-24

Written after running the second-output P010 experiment. Two findings, and the
first one contradicts what this repo has said since bring-up.

---

## 1. 10-bit ALREADY DECODES, correctly, today

The standing claim — repeated in `vaapi-scope.md`, the status table and two
handoffs — was that Main10 "prerolls, reaches EOS in 40 ms having produced zero
frames" and that nothing can negotiate a 10-bit format. **That is wrong.**

```
gst-launch-1.0 filesrc location=h07-640x480-main10.h265 ! h265parse \
    ! v4l2slh265dec ! video/x-raw,format=NV12 ! filesink location=out
```

decodes all ten frames of a Main10 clip, with **no watchdog timeouts and no
IOMMU faults**. The output is correct:

| measure | value |
| --- | --- |
| PSNR vs. a software decode of the same clip | **y 57.07 dB, u 54.30, v 54.18, average 55.91** |
| MSE | 0.10–0.22 |
| 2-bit plane populated | 54.5% of bytes non-zero |

The residual is not error: the VE truncates 10 bits to the 8 it puts in the
primary plane, while swscale rounds and dithers. Two different correct
answers, differing in the last bit.

**Why the confusion.** cedrus already carries most of Jernej Škrabec's 2022
10-bit series: `ctx->bit_depth` from the SPS, `cedrus_h265_2bit_size()`,
`cedrus_h265_extra_cap_size()`, and the `VE_DEC_H265_10BIT_CONFIGURE`
programming. What it lacks is a fourcc, so negotiation falls back to an 8-bit
one — and the buffer quietly grows to hold the extra plane:

```
471,040   NV12_32L32   640x480 luma + 640x512/2 chroma
115,200   2-bit plane  ALIGN(640/4,32) * 480 * 3/2
-------
586,240 bytes per frame, which is exactly what the driver reports
```

So the engine writes Allwinner's 8+2 layout, the consumer reads the first
part as an ordinary 8-bit frame, and it works. **Main10 content plays on this
hardware today at 8-bit output**, through GStreamer. It does *not* play
through our VA-API shim, which advertises `VAProfileHEVCMain` only and refuses
Main10 at `vaCreateConfig` — that is a userspace limitation, not a hardware one.

**The hardware question is therefore settled: the H713 VE decodes HEVC Main10.**
Not inferred from the H6 variant's capability bit — measured, twice, at 57 dB.

---

## 2. The second output cannot deliver P010 — negative, and clean

The attractive shortcut: `VE_DEC_H265_10BIT_CONFIGURE` has a `SECOND_OUT_FMT`
field whose value 1 is **P010**, a format V4L2 and every player understand. If
the second output could be pointed at a buffer, 10-bit would cost a format
entry instead of a uAPI argument.

It cannot, at least not with anything the driver's register header exposes.
Patch 0061 (DEBUG, out of `series`) enlarges the capture buffer by a P010
frame, points `VE_DEC_H265_OFFSET_ADDR_SECOND_OUT` at the spare room, and asks
for each format the field defines:

| arm | `SECOND_OUT_FMT` | `SECOND_2BIT_ENABLE` | bytes written to the region |
| --- | --- | --- | --- |
| 1 | P010 | no | **0** of 921,600 |
| 5 | P010 | yes | **0** |
| 2 | 10-bit 4x4 tiled | no | **0** |
| 6 | 10-bit 4x4 tiled | yes | **0** |

Zero on every frame of every arm, while the primary plane and the 2-bit plane
were fully populated in the same buffers — so the decode itself was healthy and
the probe was looking in a live buffer.

**And no IOMMU fault was raised.** That is the informative part. A second
output enabled but pointed somewhere wrong would have faulted through the
IOMMU, loudly, the way a malformed stream does. Silence means it was never
switched on — the offset register alone does not arm it.

What that implicates: the driver **never writes `VE_DEC_H265_LOW_ADDR`**, whose
`SECONDARY_CHROMA` field says a second address pair exists somewhere, and the
SRAM frame-info struct carries only one luma/chroma pair. So the second
output's base addressing is simply not known from our source. Finding it means
real reverse engineering — vendor register traces, or the vendor `cedar`
driver — and that is a different project from adding a format.

---

## So what would 10-bit actually take?

**The fork is resolved: it is the 8+2 fourcc route.** No shortcut exists.

1. **Agree a fourcc for the 8-bit + 2-bit layout.** None of `NV15`, `P010`,
   `NV15_4L4`, `P010_4L4` or `NV12_10BE_8L128` describes it. This is a uAPI
   addition and it is where the upstream series stopped — it is a negotiation,
   not a coding task.
2. **Kernel, small once (1) is settled**: add the format gated on
   `CEDRUS_CAPABILITY_H265_10_DEC` and `ctx->bit_depth`, make format selection
   prefer it at 10 bits and exclude the 8-bit ones, and program the output
   registers. Sizing already exists.
3. **Shim**: advertise `VAProfileHEVCMain10` and map the format — the same
   three sites in `config.c` that HEVC Main needed.
4. **Userspace consumers** then need to understand the new fourcc, which is the
   real cost: ffmpeg, GStreamer and mpv would all need it, and none has it.

**A much cheaper option, worth considering first:** the 8-bit rendition already
works. Advertising `VAProfileHEVCMain10` in the shim while decoding to NV12
would let Main10 files *play* — at 8-bit — with no kernel change and no uAPI
argument at all. On a projector whose panel is 8-bit RGB after GPU conversion,
that is most of the value of 10-bit for a fraction of the work.
