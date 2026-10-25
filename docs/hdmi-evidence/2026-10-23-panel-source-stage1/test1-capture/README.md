# Test 1: the capture front end, measured from the pristine ring (10-23)

§10.23.1 of [the design](../../../hdmi-panel-source-design-2026-10-23.md);
tool `tools/hdmi/characterise-capture.py` with `capture-probe-board.py`.

* **Boot:** production cold boot `24837bd8…` (after the stock round trip).
  Read-only on the board; the only state change was the host's own
  HDMI-A-1 mode, restored after each run (verified: `1280x720 @ 60`).
* **Reference:** what the host actually sends, as a `cosmic-screenshot`
  cropped to HDMI-A-1. The full screenshot was deleted at once, and the
  cropped references stay in `local/panel-source-t5/test1-*/`, not in git.
* **Modes:** the host offers only two under our EDID: 640×480 @ 59.94 and
  1280×720 @ 60.
* **First run:** the 640×480 screenshot timed out, very likely the screen
  capture portal's first-use permission. A rerun of that mode alone
  succeeded (`test1-2026-10-23-vga/`).
* **Data:** raw frames are in `local/panel-source-t5/test1-*/`, with hashes
  in `*/frame.sha256`.

| Mode | Ring (firmware `fb_in`) | Stride | PSNR Y vs host output | Rows Y / C | Chroma shift | RGB→YUV fit | Line doubling | Cadence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1280×720 @ 60 | 1280×720, colour 4 | 1280 | **54.9 dB** | 1:1 (0.21) / 1:1 (0.23) | 0 | **BT.709 limited**, coefficients ±0.002, offsets ±0.33, RMS 0.39/0.32/0.34 codes | 0.022 (no) | 3 slots, 62 changes/s |
| 640×480 @ 59.94 | **640×480** (not scaled), colour 4 | 640 | **54.2 dB** | 1:1 (0.25) / 1:1 (0.30) | 0 | **BT.709 limited**, coefficients ±0.0023, offsets ±0.34 | 0.033 (no) | 3 slots, 64 changes/s |

**Findings:**
* **The capture is essentially lossless for these inputs.** 54–55 dB luma
  against the host's own RGB output, residuals under 0.4 codes after
  conversion, and chroma correctly placed at full 4:2:2 vertical
  resolution with no horizontal shift.
* **Conversion is BT.709, limited range, for both modes**, including
  640×480, where BT.601 is the usual convention for SD. Whatever presents
  the ring must use BT.709 limited.
* **No capture-side scaling at these sizes.** 640×480 arrives as a
  640×480 ring, and the firmware's input buffer follows the input. Scaling
  to the panel would have to happen downstream. Stock's 1080p → 720p
  capture downscale (10-07 elog) can't be tested until the EDID offers
  1080p.
* **The ring is a 3-slot rotation at the input rate.** The cadence
  method, timed polling with 2 ms sleeps, reads about 4–7 % high. It's
  good enough to tell 60 from 50/24, but not for fine timing.

## Wide-EDID run (10-23, §10.24 bench change)

* **Install:** `update-signal-owner.sh` with the wide bundle changed only
  `h713-hdmi-signal.ko` (→ `d221c5ef`).
* **Cold boot** `dc11ba5b…`. Verified: signal owner ready, no failed units,
  the handoff, the speaker service active, and the host reading EDID
  `a78b6946` with 720p60 still current and preferred.
* **Not offered:** COSMIC doesn't list the 1080i VICs, so interlaced input
  couldn't be tested.

| Mode | Ring | PSNR Y | Rows Y / C | RGB→YUV fit | Cadence |
| --- | --- | --- | --- | --- | --- |
| 640×480 @ 59.94 | 640×480 | 54.24 | 1:1 / 1:1 | **BT.709** limited (0.0023) | ok |
| 720×480 @ 59.94 | **720×480** | 54.68 | 1:1 / 1:1 | **BT.601** limited (0.0024) | ok |
| 720×576 @ 50 | **720×576** | 54.83 | 1:1 / 1:1 | **BT.601** limited (0.0023) | 51/s |
| 1280×720 @ 60 | 1280×720 | 54.90 | 1:1 / 1:1 | BT.709 limited (0.002) | ok |
| 1280×720 @ 50 | 1280×720 | 54.89 | 1:1 / 1:1 | BT.709 limited (0.002) | 51/s |
| 1920×1080 @ 59.94 | **1280×720 (downscaled at capture)** | 42.61 | 1:1 / 1:1 | BT.709 limited (0.0018) | about 57–60/s |
| 1920×1080 @ 50 | 1280×720 (downscaled) | 42.61 | 1:1 / 1:1 | BT.709 limited | **about 30–34/s: drops about ⅓** |
| 1920×1080 @ 29.97 | 1280×720 (downscaled) | 42.61 | 1:1 / 1:1 | BT.709 limited | 31/s |
| 1920×1080 @ 23.98 | 1280×720 (downscaled) | 42.61 | 1:1 / 1:1 | BT.709 limited | 25/s |

* **Colour conversion follows the input format:** BT.601 for 480p/576p,
  BT.709 for 640×480 (IT) and HD, always limited range. The fits are
  within 0.0024 of the standards.
* **Capture downscales 1080p to 1280×720 in hardware**, as stock's elog
  shows (CapWinNode ratio `0xaaaa`), with rows 1:1 and chroma correct.
  The 42.6 dB is against a host-side bicubic downscale, so it measures
  filter difference, not damage.
* **SD and 720p arrive at native size**; nothing is scaled up at capture.
* **The 1080p50 frame drop (`cadence-recheck.json`):**
  * The capture pair advances on 60 Hz ticks for every input (gaps are
    multiples of 16.7 ms), presumably latched at the panel's vsync.
  * 720p50 and 576p50 still deliver about 51/s.
  * 1080p50 delivers only about 30–34/s over two separate 3 s windows; the
    1080p60 control gives about 57–58/s.
  * So the downscaled 1080p50 path loses roughly a third of the frames.
    The cause is open: the capture downscaler's timing, or the frame-lock
    policy at 50 → 60 Hz.
* **Revert:** the production bundle was installed with
  `update-signal-owner.sh`.
  * The first attempt's manifest had a different line order (same entries
    and hashes). The installed `SHA256SUMS` was then restored byte-exact
    to the pre-session file after an entry-set check.
  * `/usr/lib/h713-hdmi` now matches the pre-session state exactly
    (`SHA256SUMS 1b7725b7`, module `0a6987ce`).
  * The production EDID returns at the next cold boot.
* **Revert verified after a cold boot** (boot `18458dd3…`, 10-24):
  * module `0a6987ce`, manifest `1b7725b7`;
  * the signal owner ready, no failed units, the handoff present, the
    speaker service active;
  * the host reads EDID **`edab9bfc`** (production) and offers only
    1280×720 and 640×480, with 720p60 current and preferred.
