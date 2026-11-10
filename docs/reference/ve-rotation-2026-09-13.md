# H713 H.264 decode-time rotation

The H.264 secondary-output block at `VE+0x240` rotates clockwise by 90, 180
or 270 degrees. Rotation works by itself and together with the block's
power-of-two scale-down. Patch 0110 exposes it as `V4L2_CID_ROTATE`.

## Corrected vendor disassembly

`H264ConfigureScaleRotateRegister` in
`local/h713-lab/ve-extract/libs/libawh264.so` is Thumb code at virtual address
`0xde78`, file offset `0xce78`. The executable segment has a `0x1000` virtual
address/file-offset skew. Disassembling the symbol address as a file offset was
the source of an earlier incorrect bit assignment.

The corrected function writes:

```
VE_H264_SDROT_CTRL[2:0]    rotation mode
VE_H264_SDROT_CTRL[9:8]    horizontal divide: 0, 2 or 4
VE_H264_SDROT_CTRL[11:10]  vertical divide: 0, 2 or 4
VE_H264_CTRL[9]            scale/rotate enable
VE_H264_SDROT_LUMA_ADDR    transformed luma destination
VE_H264_SDROT_CHROMA_ADDR  transformed chroma destination
```

`H264DecoderSetRotateInfo` stores the requested mode at context offset `0x54`.
Its odd-mode branches swap the aligned output dimensions. The configure
function inserts that value directly into `SDROT_CTRL[2:0]`.

The earlier raw sweep of modes 1 through 3 returned an untouched output
buffer because it did not set `VE_H264_CTRL[9]`. Scale-down appeared without
that bit because a nonzero ratio field starts that path; rotation alone does
not.

## Headless hardware results

A 128x64 H.264 frame was generated with four constant-luma quadrants:
black, white, red and blue. The rotated NV12 buffer was sampled at the center
of each output quadrant. Expected limited-range Y values are 16, 235, 81 and
41.

| SDROT control | output | sampled TL, TR, BL, BR | result |
| --- | --- | --- | --- |
| `0x001` | 64x128 | 81, 16, 41, 235 | clockwise 90 degrees |
| `0x002` | 128x64 | 41, 81, 235, 16 | 180 degrees |
| `0x003` | 64x128 | 235, 41, 16, 81 | clockwise 270 degrees |
| `0x501` | 32x64 | 81, 16, 41, 235 | half-scale plus clockwise 90 degrees |

All four cases wrote one complete NV12 payload. A 1920x1088 source likewise
wrote exactly 3,133,440 bytes for each angle. No display path was involved in
these tests.

For 90 and 270 degrees, the secondary line stride is the scaled source height
and the output height is the scaled source width. For 180 degrees neither is
swapped. The capture buffer remains separate from the full-size reconstruction
buffer so reference frames always use untransformed decoder output.

## V4L2 behavior

`V4L2_CID_ROTATE` accepts 0, 90, 180 and 270. It is marked
`V4L2_CTRL_FLAG_MODIFY_LAYOUT`, must be set before capture buffers are
allocated, and is currently available only for H.264. `G_SELECTION(COMPOSE)`
reports the transformed active rectangle. With 90/270 active,
`S_SELECTION(COMPOSE)` interprets width and height in final output
orientation, then maps them back to the pre-rotation scale axes.

Any nonzero scale or rotation uses a private coded-size reconstruction frame
for each capture buffer. The user-visible capture buffer holds the linear NV12
secondary output. This is required for inter-frame prediction and is the same
DPB separation already proven for scale-down.
