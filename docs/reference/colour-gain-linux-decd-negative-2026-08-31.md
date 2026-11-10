# Stock chroma gain does not restore Linux DECD video, 2026-08-31

The calibrated stock chroma gain was transferred to the Linux DECD path on a
clean boot. It remained programmed through an accepted fmt-0 submission, but
the submitted YUV frame did not become visible: the boot logo stayed visible
and no decoded image, flash, corruption, or blackout appeared.

This closes `0x05140508 = 0x144C0000` as a sufficient fix. The field is still a
real defect in our YUV setup—the stock-side experiment proves that—but the
missing picture is gated elsewhere.

## Clean controlled run

The first attempt was not used for the visual result because the operator had
not been watching during the hold. The board was rebooted and the test was then
repeated only after the operator explicitly confirmed both that the boot logo
was visible and that they were watching.

Setup:

- restored our first stage with `build/out/h713-restore-spl.bin`, SHA-256
  `02147d8e5edb6a2810e67066d1986f5663cdb73e35d51dd30c4ebe550e349276`;
- U-Boot automatically completed project-`0x34` display initialization once;
- booted `/root/h713-kernel-decd-test.fit`, 7,750,776 bytes, whose FIT hashes
  verified in U-Boot;
- corrected client `/root/decd-client.coord1080`, SHA-256
  `256143c876bd6fa2f1564946436564c7a32c5c13b79abe26f78bf1fdff363651`;
- input `/root/decd-test-frame.nv12`, SHA-256
  `3d5f3ac3865b2a2a33afd2e0a60ba9b66f5ab076af9cb38dbcdfb283fa66105a`.

Before the submit:

```
0x05140508                   0x04000000
write/readback               0x144C0000
DECD IRQ 331                 0
panel                        boot logo visible
```

Command:

```
DECD_FMT=0 timeout 10s /root/decd-client.coord1080 show \
    /root/decd-test-frame.nv12 5000
```

The client reported a successful `FRAME_SUBMIT`, format descriptor 6, a valid
fence fd, and held the repeating frame for 5,000 ms. Afterwards:

```
0x05140508                   0x144C0000
DECD IRQ 331                 302
operator observation         no change
```

The 302 interrupts in five seconds are the established ~60 Hz DECD cadence.
The gain readback proves the submit did not overwrite or discard the stock
coefficient. The direct before/after observation proves that adding the
coefficient did not make the submitted frame reach the panel.

The boot logo is black-and-white XRGB8888, so it contains no useful chroma
observable. Its unchanged appearance is **not** evidence about whether the gain
would alter visible YUV colour. This run tests sufficiency only: if the missing
gain were the output gate, adding it would make the submitted frame appear. It
did not. The gain's actual effect on Linux remains visually untestable until
YUV video reaches the panel.

## Consequence

All writable differences in the six-window stock-versus-Linux comparison are
now accounted for:

- the tone ramps and the fifteen remaining writable candidates are benign when
  forced from Linux onto working stock;
- the OSD source address is expected to differ;
- the chroma gain is a real YUV calibration defect, but transferring it to
  Linux does not restore video.

The next useful evidence must therefore come from a read-only downstream status
boundary, an uncaptured ARM-owned register block, or sequencing/latching that a
settled-value diff cannot reveal. Another writable-value replay of the existing
six windows cannot advance the result.
