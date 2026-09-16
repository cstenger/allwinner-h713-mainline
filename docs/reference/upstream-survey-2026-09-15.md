# Upstream survey — 2026-09-15

Run to answer one question before building more: has anyone already done the
work this branch is doing? Short answer: **no, none of it** — not the cedrus
scale-down, not the rotation, not the GStreamer side, not the request-validate
fix. But the survey found two things worth more than that answer.

## How to repeat this — read first

Two hosts refuse automated fetches entirely, including their APIs and raw file
endpoints, behind an Anubis bot wall:

- `git.linuxtv.org`
- `gitlab.freedesktop.org`

**Ask the operator to clone them.** That worked twice this session and is the
only route. GitHub fetches fine.

```
git clone --depth 1 --branch v4l-utils-1.30.1 https://git.linuxtv.org/v4l-utils.git
git clone --depth 1 https://gitlab.freedesktop.org/gstreamer/gstreamer.git
git clone --depth 1 https://github.com/allwinner-zh/media-codec.git
git clone --depth 1 https://github.com/aodzip/libcedarc.git
git clone --depth 1 https://github.com/LibreELEC/LibreELEC.tv.git
git clone         https://github.com/bootlin/libva-v4l2-request.git
```

A `--depth 1` clone cannot answer "was this ever there and removed" — `git log
-S` silently returns nothing useful. Clone full when history matters.

Local `objdump` cannot disassemble aarch64 ("architecture UNKNOWN"). Use
capstone, as `tools/mips/disasm.py` already does for MIPS. In `libawh265.so`
the `.text` vaddr equals its file offset, so a symbol address indexes the file
directly.

## THE FIND: libcedarc unlocks H.265 scale/rotate

`libawh265.so` exports **register-named symbols**, and three of them land
exactly on the dead defines mainline carries:

| vendor symbol | offset | mainline name |
| --- | --- | --- |
| `regHEVC_ExtraCtrl_reg50` | +0x50 | `VE_DEC_H265_SDRT_CTRL` |
| `regHEVC_ExtraYBuf_reg54` | +0x54 | `VE_DEC_H265_SDRT_LUMA_ADDR` |
| `regHEVC_ExtraCBuf_reg58` | +0x58 | `VE_DEC_H265_SDRT_CHROMA_ADDR` |

For comparison, the H.264 blob exports `sd_rotate_ctrl_reg40`,
`sd_rotate_buf_addr_reg44`, `sd_rotate_chroma_buf_addr_reg48` — the same
scheme, which is what `cedrus_regs.h` already cites.

**This upgrades the H.265 secondary output from an inference off H.264
symmetry to an independently confirmed fact.** What is still missing is the
FIELD LAYOUT of `reg50` — H.264 has `ROTATE[2:0]`, `H_SHIFT[9:8]`,
`V_SHIFT[11:10]`; H.265 has no field macros anywhere.

Two named RE targets, both in
`/tmp/libcedarc/library/toolchain-sunxi-aarch64-glibc/libawh265.so`:

- `H265DecoderSetExtraScaleInfo` @ `0x9208`
- `HevcSetOutputConfigReg` @ `0x15238`

The first is already disassembled and is only a setter:

```
9208  ldr x5, [x0, #0x148]     ; ctx
9210  str w1, [x5, #0x3008]    ; four scale values into a SOFTWARE context
9214  str w2, [x5, #0x300c]
9218  str w3, [x5, #0x3010]
921c  str w4, [x5, #0x3014]
...
9260  ldr w1, [x2, #0x3018]    ; enable path
926c  orr w1, w1, #1           ; ctx+0x3018 bit 0 = enable
9270  str w1, [x2, #0x3018]
```

So `+0x3008..0x3014` are the scale parameters and `+0x3018[0]` is the enable,
all in software state. **Follow those offsets into `HevcSetOutputConfigReg` to
recover how they are packed into `reg50`.** That is the whole remaining task,
and it is desk work — the four-quadrant card and probe in
`tools/video/cedrus-compose-probe.c` already verify the result headlessly.

### Bonus: the 10-bit second output is no longer a dead end

`vaapi-hardware-decode-scope` records that the VE's second output "CANNOT emit
P010" because `VE_DEC_H265_LOW_ADDR` was never written and "the base addressing
is unknown". The blob names them:

```
regHEVC_8BIT_Addr_reg80                    (mainline VE_DEC_H265_LOW_ADDR, +0x80)
regHEVC_lower_2bit_addr_first_output_reg84
regHEVC_lower_2bit_addr_second_output_reg88
regHEVC_10bit_configure_reg8c
```

The 8+2 layout needs a 2-bit plane address per output, and `reg84`/`reg88` are
exactly that. The unknown is no longer unknown; whether it then works is
untested.

## Hantro is the API precedent, and we diverged from it

`drivers/media/platform/verisilicon` is a **mainline stateless decoder whose G2
post-processor does power-of-two down-scaling** — structurally our SDROT. It
exposes it as:

```c
static int down_scale_factor(struct hantro_ctx *ctx)
{
	if (ctx->src_fmt.width <= ctx->dst_fmt.width)
		return 0;
	return DIV_ROUND_CLOSEST(ctx->src_fmt.width, ctx->dst_fmt.width);
}
```

Userspace sets a **smaller capture format with `S_FMT`**, and available sizes
come from **`VIDIOC_ENUM_FRAMESIZES`** (`hanto_postproc_enum_framesizes`).

We chose `S_SELECTION(COMPOSE)`. That is a different mechanism from the only
mainline stateless decoder doing this, and it is what maintainers will ask
about. Two consequences:

- **cedrus implements no `enum_framesizes` at all** (grep count: 0). Userspace
  cannot discover which scaled sizes exist; it has to guess and read back.
- A defensible synthesis: take hantro's mechanism for SCALE SELECTION (`S_FMT`
  plus `ENUM_FRAMESIZES`) and keep `COMPOSE` for what it actually means in
  V4L2 — the active rectangle inside a larger allocation. We genuinely need
  that second thing, because patch `0106` requires a native 1280-pitch raster.
  Today we conflate the two into one mechanism.

Hantro has no rotation. `V4L2_CID_ROTATE` on a stateless decoder remains
novel; the nearest precedent is the Qualcomm Iris **encoder**.

## Per-source results

### allwinner-zh/media-codec — architectural confirmation only

Vendor CedarX. H.265 is a blob and `SOURCE/vdecoder/include/veregister.h`
predates it — its register groups are only Top Level / MPEG / H264. What it
does confirm is the vendor's model: `bSecOutputEn`, `nSecHorizonScaleDownRatio`,
`nSecVerticalScaleDownRatio` and `nRotateDegree` are generic `VCONFIG` fields
(`include/vdecoder.h`), not H.264-specific.

### LibreELEC.tv — four cedrus patches, none ours

All Jernej Skrabec's, under `projects/Allwinner/patches/linux/`:

- `0049-media-cedrus-Implement-AFBC-YUV420-formats-for-H265`
- `0050-media-cedrus-Increase-H6-clock-rate`
- `0048-media-cedrus-add-format-filtering-based-on-depth-and`
- `0033-media-cedrus-Don-t-CPU-map-source-buffers`

`0049` is worth knowing: the VE emitting **AFBC-compressed** YUV420, the format
family our display fetcher natively consumes. It does NOT touch the secondary
output or `+0x50` — it is output-format selection, a different mechanism. A
possible future route that would skip the linear-NV12 round trip entirely.
Context, not a correction: our route works.

Nobody there has driven the secondary output.

### bootlin/libva-v4l2-request — nothing, and our pin is stale

No `COMPOSE`, `G_SELECTION`, `S_SELECTION` or `CID_ROTATE` anywhere in the
source. The PR list is mostly abandoned; **our pinned #38 has been open since
2021-08-12**. The one live item is **#44 "Kernel 6.18"**, opened 2026-06-12 —
plausibly relevant since we run 6.18.38. Look at it before more shim work.

### gstreamer — absent from master

Every `COMPOSE`/`ROTATE` hit under `subprojects/gst-plugins-bad/sys/v4l2codecs/`
is in the vendored uapi headers. **No GStreamer source file** references
`V4L2_SEL_TGT_COMPOSE`, `VIDIOC_G_SELECTION` or `V4L2_CID_ROTATE`. Capture
buffers are sized arithmetically and negotiated with plain `G_FMT`/`S_FMT`.

The clone was shallow, so open merge requests remain unchecked — `gitlab`
blocks the MR list, its API and raw files alike. That part of the answer is
still open.

### linux-media — two fixes we were missing, now backported

Patches `0112` and `0113`. See their commit message; the H.264 one is a
userspace-reachable out-of-bounds read.
