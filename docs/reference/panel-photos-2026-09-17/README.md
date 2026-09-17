# Coded padding, measured on the projector — 2026-09-17

Photographs of the [scaler test card](../scaler-testcard.md) decoded to the panel,
rectified and measured by
[`tools/display/measure-panel-photo.py`](../../../tools/display/measure-panel-photo.py).

**Result:** the coded-padding artifact predicted by
[the headless input-crop measurement](../ve-input-crop-2026-09-17.md) is real,
visible, and the same size on the panel as it is in the decoder's own output —
and once the input crop landed, **it is gone**. The bottom border went from
10.70 panel pixels to 5.92, against 5.35 for a natively rasterised 720p card.

## Why a photograph can be measured at all

The card's border sits at the very edge of the source frame, so it always maps
to the whole output buffer — 1280x720, 16:9, on a 16:9 panel — whatever the
scaler did. Mapping its four corners onto a 16:9 rectangle therefore removes
**every** projective distortion in the chain at once: projector throw, keystone,
and wherever the photographer was standing. The camera position does not have to
be reproducible, which matters because it wasn't.

What survives is what the pixel pipeline did.

## Numbers

Border thickness as FWHM in panel pixels. FWHM rather than a threshold because
both the projector optics and the camera lens blur, and a thicker band survives
the point-spread function better — so it also reads brighter, which a fixed
threshold would score as extra width.

| image | top | **bottom** | left | right | bottom/top | circles w/h |
| --- | --- | --- | --- | --- | --- | --- |
| reference, native 720p card | 5.45 | 5.35 | 5.50 | 5.54 | 0.98 | 1.000 |
| IMG_0884 — hardware, VE-scaled | 4.63 | **10.95** | 5.63 | 7.13 | 2.37 | 0.989 |
| IMG_0886 — **software decode** | 4.45 | **6.08** | 5.63 | 8.05 | 1.37 | 0.987 |
| IMG_0888 — hardware, VE-scaled | 4.98 | **10.70** | 5.76 | 9.28 | 2.15 | 0.987 |
| IMG_0889 — hardware, **input crop** | 4.91 | **5.92** | 5.91 | 8.51 | 1.21 | 0.992 |

The headless dump predicted the bottom border at **11 rows** when the scaler is
fed the coded raster and **6 rows** when fed the visible one. The photographs
give 10.95 and 10.70 for the hardware path and 6.08 for software — through the
whole optical chain, from two camera positions, on different days.

## After the crop

IMG_0889 is the same card, same player, same projector, with kernel patch 0122
and libva 0010 in place so the scaler reads the visible 1920x1080 instead of the
coded 1920x1088. The bottom border measures **5.92** — below the 6.08 of the
software-decoded frame and close to the 5.35 of the native reference. The
prediction from the headless dump was "six rows instead of eleven"; the panel
says 5.92 against 10.70.

The residual bottom/top ratio of 1.21, where the native reference manages 0.98,
is the optics rather than the picture: focus falls off toward the bottom and the
right of this projection, which the right-edge column shows in every photograph
(8.51 here against 5.91 on the left). The software frame, which scales
correctly, reads 1.37 through the same lens.

The circles moved from 0.987 to 0.992, toward round, which is the direction the
crop predicts: both axes now scale by exactly 1.5, so the 0.74% anisotropy
should disappear. The shift is about one standard deviation of the ellipse fit,
so it is consistent with the prediction rather than independent proof of it. The
border is the measurement that carries weight.

## The control was an accident

IMG_0886 was taken after the flicker caused by
[the seek bug](../../handoff-2026-09-17-scaled-playback.md), so it is a
**software-decoded** frame: same projector, same optics, but scaling only the
visible 1080 rows. Its bottom border of 6.08 px is what correct output looks
like through this projector, and it is what separates padding from lens blur —
the optical bottom/top asymmetry is 1.37, while the hardware path shows
2.15–2.37.

A frame that was worthless as evidence about the scaler turned out to be the
best available control for the optics.

## The circles were the projector, not us

In the raw photographs the card's circles look roughly 10% taller than wide,
which the decode path cannot produce: it scales 0.6667 horizontally and 0.6618
vertically, so circles should be 0.74% *wider* than tall.

After rectification, width/height is 0.987–0.989 **in all three photographs,
including the software one**. It is common-mode, so it is not our scaling — the
software path does a correct 1080→720 and shows the same 1.3%. The apparent
elongation was projection geometry and the homography removed it. The residual
is projector optics, panel pixel aspect, or rectification error, and it is
identical on both decode paths.

## Reading the rectified images here

`reference-720p-native.png` is the card rasterised natively at 720p, put through
the same measurement code. Compare the bottom edge of the two `HW-scaled` images
against it and against `IMG_0886_SOFTWARE.png`.

The source photographs are not committed — they are ~4.5 MB each and live in
`local/lcd-photos/test_87/`, which is ignored. Reproduce with:

```bash
python3 tools/display/measure-panel-photo.py \
  "reference=local/testcards/scaler-testcard-1280x720.png" \
  "photo=local/lcd-photos/test_87/IMG_0888.JPEG"
```

## Limits

- The right-hand border reads thicker than the left (7.1–9.3 vs 5.6) in every
  photograph. That is the projection being angled — focus falls off across the
  throw. It is why `bottom/top` is the cleaner statistic than
  `bottom/(left,right)`: both are horizontal edges measured the same way.
- FWHM on a blurred edge is not the same quantity as a row count in a buffer.
  The agreement with 11 and 6 is close enough to be convincing but should not be
  read as sub-pixel accuracy.
- Only H.264 1080p was photographed.
