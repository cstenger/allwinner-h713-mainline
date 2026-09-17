# H713 4:2:2 decode: quick assessment

The stock H713 HEVC and H.264 hardware decoder paths do not provide evidence
of working 4:2:2 decoding. Keep Cedrus restricted to 4:2:0. This investigation
does **not** establish that 4:2:2 is physically impossible in the silicon.
No module changes or board probes were made for this assessment.

## Evidence from H713's own vendor libraries

Libraries are under `local/h713-lab/ve-extract/libs/`. Addresses below are ELF
virtual addresses with the Thumb function-pointer low bit cleared.

### HEVC

`libawh265.so`, `HevcDecodeNalSps`:

```text
0x11f90  bl      0x11974       ; read unsigned Exp-Golomb chroma_format_idc
0x11f94  cmp     r0, #1
0x11f96  str     r0, [r5, #4]
0x11f98  bne     0x1204e       ; reject every value except 4:2:0
```

The error block resolves its PC-relative format string to VA `0x2aca`:
`h265 decode nal sps, chroma_format_idc(%d) != 1, not support`.
It reaches the failure return (`r0 = -1` at `0x11f76`). This is an explicit
vendor software rejection, rather than a hardware capability measurement.

### H.264

`libawh264.so`, `H264DecodeSps`, reads chroma format at `0x11214` and compares
it with 1 at `0x11216`. A nonzero configuration word at decoder-context offset
`0xa4` bypasses rejection. Consequently the parser alone cannot rule out 4:2:2.
`H264DecoderInit` copies VConfig to context offset `0x38`, making that word
VConfig offset `0x6c`. An older Allwinner header labels the matching offset
`bIsTvStream`; that older layout is supporting context, not proof of the H713
field's identity.

The decisive check is `H264ConfigureSliceRegister`: it **always programs
4:2:0**, regardless of the parser exception:

```text
0xe466  movs    r3, #1
...
0xe47c  bfi     r1, r3, #19, #3 ; SPS chroma_format_idc bits 21:19 = 1
0xe480  str     r1, [r0]        ; register shadow
...
0xe48e  str     r1, [r3]        ; hardware SPS register
```

The older [Allwinner H.264 register setup source](https://github.com/hanetzer/H6-CedarC/blob/master/vdecoder/videoengine/h264/h264_hal.c)
likewise hardcodes `avc_sps_reg00.chroma_format_idc = 1`. Its comment names
encodings for 4:2:2 and 4:4:4, but named register encodings do not establish
that those modes work on H713. The current Cedrus driver also exposes a chroma
field in its register recipe; that is not capability proof either.

## Limits and decision

- Vendor HEVC rejects 4:2:2; vendor H.264 always selects 4:2:0 for hardware.
- `libawmjpeg.so` exports `MjpegTransformPlanner422To420`, so a blanket claim
  that the entire VE has no 4:2:2-related functionality would be unjustified.
  The symbol alone does not prove JPEG hardware input support.
- A Cedrus rejection test only tests driver policy. Removing the check and
  decoding into existing NV12 buffers would not reliably test silicon support:
  reconstruction/chroma storage, motion-vector storage, and reference layout
  also need checking. A timeout or corrupt frame with an unverified setup
  cannot prove absence of support.

Treat 4:2:2 as unsupported in the current driver and vendor decode paths.
There is no quick, conclusive silicon-level exclusion in the evidence above.
Keep the working 4:2:0 implementation and compliance result unchanged.

## Library identity (SHA-256)

```text
libawh264.so  0e6321833d03cf2c2a00445198c5d5d039658d0eec66351e1a3b3583bb215919
libawh265.so  6fbbf8acce91a3b69485431f3ce07206d6c965679ca93400b6de254e60c0a3ff
libawmjpeg.so 024d25817964bbe8c6a3abc405a316203b1f8295dcfc0a9838111963dacbce62
```
