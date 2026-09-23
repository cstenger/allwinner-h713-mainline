# 10-bit HEVC on the H713

Measured 2026-08-24, re-measured and substantially corrected 2026-09-23.

**Headline: the H713 VE decodes HEVC Main10 to full, bit-exact 10-bit today.**
Every sample of every plane matches a software 10-bit decode exactly. Nothing
is lost, nothing is truncated, and no kernel change is needed to produce the
data. What is missing is a *V4L2 pixel format that describes the layout*, so a
client has no supported way to ask for the bits that are already in the buffer.

---

## 1. 10-bit decodes, and it is bit-exact

The 2026-08-24 revision of this file reported 55.91 dB against a software
decode and explained the residual as the VE truncating to 8 bits. That
explanation was right about the *8-bit plane* and wrong about the engine: the
low two bits are written too, in a separate plane, and when they are read back
the result is exact.

Measured 2026-09-23 on the bench board, production module
`00c23affce3ba298bd7352889ad5895b`, against `ffmpeg -pix_fmt yuv420p10le`
software decodes of the same streams:

| vector | coded | Y | U | V |
| --- | --- | --- | --- | --- |
| `h07-640x480-main10.h265` | 640x480 | **100.00%** | **100.00%** | **100.00%** |
| generated 1280x720 Main10 | 1280x720 | **100.00%** | **100.00%** | **100.00%** |
| generated 642x482 Main10 | 656x496 canvas | **100.00%** | **100.00%** | **100.00%** |

Percentages are exactly-matching samples, not a PSNR proxy: 307200/307200 luma
and 76800/76800 each of U and V on the first vector, `maxerr 0` throughout.

The 8-bit plane alone scores **59.11 dB** against the same 10-bit reference,
which is what every previous measurement here was actually reporting.

Reproduce with [`tools/video/hevc-10bit-verify.py`](../tools/video/hevc-10bit-verify.py).

## 2. The layout

The capture buffer is ordinary NV12 followed by a packed 2-bit plane. The
driver already sizes it this way — `cedrus_h265_extra_cap_size()` appends the
2-bit plane and `VE_DEC_H265_OFFSET_ADDR_FIRST_OUT` points the engine at it —
so this is a description of what is in the buffer today, not a proposal.

```
+---------------------------------------+  0
| luma, 8 bit, bytesperline x ALIGN(h,16)|
+---------------------------------------+  bytesperline * ALIGN(h,16)
| chroma, 8 bit, NV12 interleaved, half  |
+---------------------------------------+  sizeimage - two_bit_size
| 2-bit luma,   coded_h rows             |
| 2-bit chroma, coded_h/2 rows           |
+---------------------------------------+  sizeimage
```

- 2-bit pitch is `ALIGN(DIV_ROUND_UP(canvas_width, 4), 32)` bytes.
- Four samples per byte; sample `n` of a row is in bits `[2*(n&3)+1 : 2*(n&3)]`,
  low-order sample first.
- Full sample value is `(eight_bit << 2) | two_bit`.

**The one trap.** The 2-bit chroma rows begin after **`coded_h`** luma rows —
the SPS height, a multiple of 8 — *not* after the capture canvas height, which
is a multiple of 16. The two agree for 640x480 and 1280x720 and disagree for
642x482, where the canvas is 496 rows but chroma starts at row **488**. Reading
it at the canvas height gives bit-exact luma and quietly wrong chroma: 81.6%
of samples correct with `maxerr 3`, which is small enough to look like decoder
rounding rather than a layout error. Two vectors out of three cannot see this;
pick a height that is `8 mod 16` or the test proves nothing.

The driver reserves the 2-bit plane at the canvas height, so it over-reserves
by `(ALIGN(h,16) - ALIGN(h,8)) * 3/2 * pitch` bytes. That is safe and is not a
bug — the engine writes less than is reserved.

## 3. The P010 second-output route is dead — now measured, with a control

The attractive shortcut was `VE_DEC_H265_10BIT_CONFIGURE[24:23]`
(`SECOND_OUT_FMT`), whose value 1 is documented as P010. If the second output
could emit P010, 10-bit would cost one *existing* fourcc that ffmpeg, GStreamer
and mpv all already understand.

The 2026-08-24 probe found zero bytes written and concluded the base addressing
was unknown. **That conclusion is superseded**: the second output was simply
never armed — no `ROTATE_SCALE_OUT_EN`, no DDR consistency, no VE+0xf00
geometry. Patch 0118 arms it, and since then the second output demonstrably
writes real pixels.

Retested 2026-09-23 with the output armed and writing, on a Main10 decode
scaled 640x480 -> 320x240, with the capture pitch forced to 640 so the buffer
is byte-for-byte a P010 frame of that size:

| `SECOND_OUT_FMT` | result |
| --- | --- |
| 0 — 8+2 | `md5 076112d2…` |
| 1 — P010 | `md5 076112d2…` |
| 2 — 10-bit 4x4 tiled | `md5 076112d2…` |
| 3 — undefined | `md5 076112d2…` |

**Byte-identical on all four arms.** The register write lands — the probe logs
`10bit_cfg=008000a0`, bit 23 set — and the engine ignores it.

That null is trustworthy because the same run carries a positive control on the
register group that *does* select the secondary format,
`VE_PRIMARY_OUT_FMT[3:0]`. Every documented value produces a different picture:

| value | 4 NV12 | 5 NV21 | 2 YU12 | 3 YV12 | 0 tiled32 | 1 tiled128 | 6/7 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| md5 | `076112d2` | `35ae977b` | `1f1adfc3` | `12be2240` | `cd00cada` | `a038e2de` | `80fe38e6` |

Values 8–15 mirror 0–7, so the field is three bits. The undocumented 6/7 pair
differs from NV12 **only in chroma** — its luma plane is byte-identical — so it
is another chroma arrangement, not a wider sample. **No value of any secondary
format selector produces more than one byte per sample.**

Note what this does *not* say. The vendor's own decoder libraries carry the
strings `sec out not support AW 10bit foramt, use p010` and `10bit video sec
out not support aw 10bit format, not open sec out` (in both `libawh265.so` and
`libawh264.so`, so it is shared framework code). Read plainly, the vendor
intends P010 on the second output. On this part, through every register we can
reach, it does not happen. Either the selector is elsewhere or the datapath is
absent; we cannot tell which, and it does not matter for the conclusion.

**Consequence worth carrying: 10-bit output and the VE scaler are mutually
exclusive.** Scaling routes the picture through the second output, and the
second output is 8-bit. A scaled Main10 decode is a correct 8-bit rendition of
a 10-bit stream, which is exactly what it is today.

## 4. What is actually left

Not a hardware question any more. Two things, in order:

1. **A fourcc for the 8+2 layout.** None of `NV15`, `P010`, `NV15_4L4`,
   `P010_4L4` or `NV12_10BE_8L128` describes it, and nothing in the 6.18 uAPI
   does either.

   **Checked upstream 2026-09-23, and the earlier framing here was wrong.**
   Jernej Škrabec's series did not stall on a fourcc negotiation — it landed,
   having deliberately chosen not to expose one. `media: cedrus: h265: Support
   decoding 10-bit frames` (v3, 2022-11-09) is titled and written as *decoding
   10-bit frames into an 8-bit capture format*; the 2-bit plane is allocated
   through the `extra_cap_size` callback as **extra capture buffer space the
   hardware requires**, not as output. That code is in our tree today. So the
   upstream position is not "unfinished", it is "the 2-bit plane is scratch".

   No 8+2 output fourcc has ever been proposed, by anyone. The 10-bit formats
   that *did* land — Rockchip's `NV15`/`NV20` — are genuinely packed (four
   samples in five bytes, no padding, no second plane) and took seven revisions
   between 2022 and 2025 to get in. They cannot describe this layout.

   Inventing one downstream therefore means arguing a case upstream has not
   been asked, against a maintainer who already made the opposite call for this
   exact driver.
2. **A consumer.** ffmpeg, GStreamer and mpv would all need the new format.
   Against that: this projector's panel is 8-bit, the display path takes 8-bit
   NV12, and Main10 files already play correctly on the panel through the 8-bit
   plane (confirmed on the glass 2026-09-17, commit 5451b9c).

So the honest position is that **10-bit support is complete at the hardware and
driver level and blocked on uAPI**, and the remaining benefit on *this* device
is precision for something that would consume it, not visible picture quality.
Anyone adding the fourcc should read §2 first: the coded-height trap is the
part that will silently produce nearly-right chroma.
