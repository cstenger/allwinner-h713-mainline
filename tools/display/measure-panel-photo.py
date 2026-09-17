#!/usr/bin/env python3
"""Measure a photograph of the scaler test card on the panel.

WHY RECTIFY. The card's border sits at the very edge of the source frame, so it
always maps to the whole output buffer -- 1280x720, 16:9, on a 16:9 panel --
whatever the scaler did. Mapping those four border corners onto a 16:9 rectangle
therefore removes EVERY projective distortion in the chain at once: projector
throw, keystone, and wherever the photographer happened to be standing. The
camera position does not need to be reproducible.

What survives rectification is what the pixel pipeline did:

  * BORDER SYMMETRY. The card's border is the same thickness on all four edges.
    H.264 stores 1080p as 1088 coded rows, so a scaler fed the coded raster
    squeezes 8 rows of encoder padding into the picture. Encoders pad by
    replicating the last row -- which here IS the bottom border -- so the
    signature is a bottom border markedly thicker than the top one.

  * CIRCLE AXIS RATIO. Anisotropic scaling turns the card's circles into
    ellipses. Note this is a weak instrument for OUR pipeline specifically:
    since the border defines the output rectangle, any anisotropy we introduce
    is shared by border and content alike and is normalised away here. It is a
    strong instrument for deciding whether an elongation seen in the photograph
    came from the projection geometry (it rectifies away) or from inside the
    image (it does not).

Run the reference PNG through the same code to check the measurement itself.
"""
import sys

import cv2
import numpy as np

W, H = 1280, 720


def find_card_quad(bgr):
    """The four outer corners of the bright projected rectangle."""
    grey = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    grey = cv2.GaussianBlur(grey, (7, 7), 0)
    # The wall is dark and the projection is bright; Otsu separates them.
    _, mask = cv2.threshold(grey, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    card = max(contours, key=cv2.contourArea)

    # Relax the polygon tolerance until it collapses to a quadrilateral.
    peri = cv2.arcLength(card, True)
    for frac in np.arange(0.005, 0.10, 0.005):
        approx = cv2.approxPolyDP(card, frac * peri, True)
        if len(approx) == 4:
            return approx.reshape(4, 2).astype(np.float32)
    return None


def order_corners(pts):
    """TL, TR, BR, BL."""
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)],
                     pts[np.argmax(s)], pts[np.argmax(d)]], dtype=np.float32)


def rectify(bgr):
    quad = find_card_quad(bgr)
    if quad is None:
        return None
    dst = np.array([[0, 0], [W - 1, 0], [W - 1, H - 1], [0, H - 1]], np.float32)
    m = cv2.getPerspectiveTransform(order_corners(quad), dst)
    return cv2.warpPerspective(bgr, m, (W, H), flags=cv2.INTER_CUBIC)


def edge_fwhm(prof, span=40):
    """Full width at half maximum of the border line at the start of a profile.

    A projector's optics and a camera lens both blur, so the border is not a
    hard-edged run and a fixed threshold measures the blur as much as the line.
    FWHM against each edge's OWN peak and its own local background is
    comparable between edges even when they differ in brightness -- which they
    do here, because a thicker band survives the point-spread function better
    and therefore also reads brighter.
    """
    seg = prof[:span].astype(float)
    peak_i = int(np.argmax(seg))
    peak = seg[peak_i]
    # Background is the flat card interior just inside the border.
    base = float(np.median(prof[span: span + 60]))
    if peak <= base:
        return 0.0
    half = base + 0.5 * (peak - base)

    def cross(a, b):
        """Sub-pixel crossing of `half` between samples a and b, as a fraction.

        Clamped, because a hard edge -- the reference card has them -- puts both
        samples on the same side and the unclamped ratio then explodes.
        """
        span_ = b - a
        if abs(span_) < 1e-6:
            return 0.0
        return min(1.0, max(0.0, (half - a) / span_))

    i = peak_i
    while i > 0 and seg[i] >= half:
        i -= 1
    lo = i + cross(seg[i], seg[i + 1])
    j = peak_i
    while j < span - 1 and seg[j] >= half:
        j += 1
    hi = j - cross(seg[j], seg[j - 1])
    return float(hi - lo)


def border_thickness(grey):
    """Border FWHM on all four edges, in panel rows/columns.

    Measured over the middle half of each edge so the corner markers, which are
    deliberately different on every corner, cannot bias it.
    """
    rows = grey[:, W // 4: 3 * W // 4].mean(axis=1)
    cols = grey[H // 4: 3 * H // 4, :].mean(axis=0)
    return {
        "top": edge_fwhm(rows),
        "bottom": edge_fwhm(rows[::-1]),
        "left": edge_fwhm(cols),
        "right": edge_fwhm(cols[::-1]),
    }


def circle_axis_ratio(grey):
    """Mean width/height of the card's circle row, by ellipse fit."""
    band = grey[int(H * 0.42):int(H * 0.80), :]
    band = cv2.GaussianBlur(band, (5, 5), 0)
    _, mask = cv2.threshold(band, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    ratios = []
    for c in contours:
        if len(c) < 40 or cv2.contourArea(c) < 1500:
            continue
        (_, _), (a, b), _ = cv2.fitEllipse(c)
        if not a or not b:
            continue
        # Keep only contours the ellipse actually describes. Without this the
        # crosshairs and the band's own frame get fitted too, and a bad fit is
        # indistinguishable from a real distortion in the average.
        if abs(cv2.contourArea(c) - np.pi * a * b / 4) > 0.25 * np.pi * a * b / 4:
            continue
        if not (0.8 < a / b < 1.25):
            continue
        ratios.append(a / b)
    return ratios


def report(label, path, is_reference=False):
    img = cv2.imread(path)
    if img is None:
        print(f"{label}: cannot read {path}")
        return
    if is_reference:
        rect = cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)
    else:
        rect = rectify(img)
        if rect is None:
            print(f"{label}: could not locate the card")
            return

    grey = cv2.cvtColor(rect, cv2.COLOR_BGR2GRAY)
    b = border_thickness(grey)
    ratios = circle_axis_ratio(grey)

    # Left and right carry no coded padding, so they are the control: they say
    # what an unpadded border of this card measures through this optical chain.
    control = (b["left"] + b["right"]) / 2
    print(f"--- {label}")
    print(f"    border FWHM, panel px:  top {b['top']:5.2f}   bottom {b['bottom']:5.2f}"
          f"   left {b['left']:5.2f}   right {b['right']:5.2f}")
    print(f"    bottom/top {b['bottom'] / b['top']:.2f}"
          f"    bottom/(left,right avg) {b['bottom'] / control:.2f}"
          if b["top"] and control else "    (degenerate)")
    if ratios:
        arr = np.array(ratios)
        print(f"    circles: {len(arr)} fitted, width/height "
              f"mean {arr.mean():.3f}  sd {arr.std():.3f}")
    else:
        print("    circles: none fitted")
    cv2.imwrite(f"/tmp/rect-{label.replace(' ', '_').replace('/', '_')}.png", rect)


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        if "=" in arg:
            label, path = arg.split("=", 1)
        else:
            label, path = arg, arg
        report(label, path, is_reference=path.endswith(".png"))
