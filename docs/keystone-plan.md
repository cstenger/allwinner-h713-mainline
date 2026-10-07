# Automatic keystone: plan (2026-10-06)

> **Status 2026-10-06: Phase 3 DONE, verified on the wall.** At 20°, the corrected picture matches the projector's level baseline to within 0.1% (tape measure). Phase 2 DONE, verified on hardware. `h713-keystone` and its service ship in the image. They publish the settled tilt and drive the ceiling flip. **Next: Phase 3**, the GL warp.
> - **Hardware run** ([log](reference/keystone-phase2-flip-2026-10-06.log)), with `ceiling auto` on:
>   - Pitch tracked the stand from −1° to 89° and back.
>   - Turning the projector upside down set mode 3 (`ceiling`) within a second; setting it upright again restored 0 (`front`).
>   - The correction held while the projector was being moved, and roll stayed within ±1.5°.
> - **The stand has ~10° detents.** Coming down, it settled at 89.3, 79.0, 68.4, 58.5, 48.1, 38.2, 29.0, 18.2, 8.9 and −1.0°.
>
> **Phase 1 DONE (2026-10-06), kernel 0168.** The tilt sensor is a Silan SC7A20, not the STK8BA58 the stock DT names. Mainline `st_accel` drives it, with a measured mount-matrix.

The projector has an accelerometer, so the picture can be corrected for vertical tilt without the user doing anything. An accelerometer sees **pitch and roll only**: the angle to the wall (yaw) needs a camera or ToF sensor, which this board doesn't have. So this is vertical keystone, which is what the stock firmware's auto keystone is as well.

There is no hardware warp: the scaler census found three scalers, none of which can do a perspective transform. So any correction other than zero is a GL warp, as it is in stock SurfaceFlinger (`libkeystone.so`). It forces the GPU route ([gpu-fallback-plan.md](gpu-fallback-plan.md)).

## Phase 1: the sensor (kernel 0168)

- **Bus and chip:** TWI1 (PH2/PH3) at 0x18, Linux `i2c-0`. WHO_AM_I `0x0f` = `0x11` identifies a Silan SC7A20, a LIS3DH clone. Stock's `stk83xx` driver handles several chips.
- **Driver:** `CONFIG_IIO_ST_ACCEL_3AXIS=y`, node `compatible = "silan,sc7a20"`. It appears as an IIO device named `sc7a20` with `in_accel_{x,y,z}_raw` and per-axis `_scale`.
- **Mount-matrix:** measured by standing the projector lens-up, level and right side raised. The projector frame is the IIO device frame seen from behind the projector: **X right, Y up, Z back toward the viewer, so the lens points along −Z**. Level reads Y ≈ +1.04 g; the 4% gain error is below a degree of angle.
- **Gotchas:**
  - Every sysfs read powers the chip up for one sample. At the 1 Hz default ODR that takes about a second per axis; at 100 Hz, a sample of all three axes takes about 70 ms.
  - Noise is 15–37 mg per axis, about 2°.
  - No IRQ is wired.
- **Dev reader:** `tools/sensors/accel-read.py`.

## Phase 2: `h713-keystone` (tools/sensors/h713-keystone)

```
h713-keystone                          status
h713-keystone auto|off [--persist]     keystone follows the tilt, or none
h713-keystone manual DEG [--persist]   a fixed correction
h713-keystone ceiling auto|off [--persist]
h713-keystone daemon                   h713-keystone.service
```

- **Sampling:** about 14 samples a second (ODR 100), in 10-sample windows. A window is still when every axis has an SD below 0.06 g. Still windows feed a running average that resets on movement or on a jump of more than 1.5°. Changes are published with 0.5° of hysteresis. Measured at rest: one publish in 30 s, and 1.2% of one core.
- **Ceiling auto:** turning the projector over is `h713-mirror` mode XOR 3 (front ↔ ceiling, rear ↔ rear-ceiling), so only the top/bottom half follows gravity.
  - The projector counts as upside down past −0.5 g on Y and as upright past +0.5 g. In between, the state holds, so a lens pointed at the ceiling doesn't flip the picture.
  - A refused flip (P010 on the plane) is retried every 10 s.
  - Ceiling auto is off by default, so `h713-mirror --persist` keeps working.
- **Calibration:** the zero-g offsets are tens of mg (this unit: 14 mg side, 30 mg lens axis), about a degree, so uncalibrated the stand read −1° to 89°.
  - `h713-keystone calibrate level`, at the lowest detent, zeroes the lens and side axes. `calibrate up`, lens straight up, zeroes the up axis.
  - Each averages 8 still windows, taking about 13 s with the daemon running (repeatable to 4 mg, ~0.2°). It refuses a pose more than ~6° off.
  - **This unit, 2026-10-06:** `bias_x=0.0368 bias_y=0.0255 bias_z=0.0544` (g). Bottom detent 0.1°, top 90.0° by construction. The earlier level-only run gave `bias_z=0.0302 bias_x=0.0140`: the seat moved 1.4° in pitch and 1.3° in roll between the two.
  - **The stand reseats to within about 1°:** after a full tilt up and back, the bottom detent read −1° against the 0.1° just after calibrating. That is the mechanism, not the sensor.
- **Noise and thresholds:** normal (10-bit) mode reads 27–53 mg SD per axis. A window counts as still below 0.10 g SD; at 0.06 g, 7% of still windows read as moving. A jump past 3° counts as a new pose. One window is about 0.7° of pitch noise.
  - The offsets are always saved to `/etc`. Then the stand reads 0° to 90°.
- **Settings:** `/etc/h713-keystone.conf` (with `--persist`) or `/run/h713-keystone/conf`. They are reread every window.
- **sh + mawk:** the product image has no python3.
- **Test:** `tools/sensors/h713-keystone-test.sh` runs on the board against a fake sensor and a fake mirror: 43 checks covering both flips, the refusal retry, the moving hold, hysteresis, persistence and calibration.
  - The fake writes each axis atomically and costs 20 ms per read, like the chip. Earlier, instant reads of half-written files made the "moving" check pass for the wrong reason.
  - Fixed along the way: hysteresis could latch up to 0.5° short (the converged estimate is now republished after 8 still windows); the first still window after a move is skipped (its tail seeded the average); a flip that leaves the angles unchanged is now published.

### The contract for Phase 3: `/run/h713-keystone/state`

Written atomically (rename), only when something changes:

| Key | Meaning |
| --- | --- |
| `keystone_deg` | the correction to apply: settled pitch in `auto`, DEG in `manual`, 0 when `off` |
| `pitch_deg` | lens tilt toward the projector's **own** top (+Y). It keeps its meaning upside down |
| `roll_deg` | the projector's right side above the horizon |
| `inverted` | 1 upside down (held near vertical) |
| `settled` | 0 while moving. `keystone_deg` keeps its last value, so the picture doesn't swim |
| `keystone`, `ceiling`, `updated` | the settings in force, and the time (CLOCK_BOOTTIME seconds) |

Both angles are in the projector's frame, **before the panel mirror**. The GPU draws the framebuffer and the panel mirrors it afterwards, so the warp has to apply `h713-mirror`'s current mode itself: under a V flip, the framebuffer's top is the panel's bottom.

## Phase 3: the GL warp

> **Status 2026-10-06: DONE.** Verified on the GPU by scanout grab, then on the wall with a tape measure. Without a measured lens, everything stays idle.

### Wall result (2026-10-06, cold boot, bottom detent calibrated to 0°)

**Lens** (front of the lens 25 3/4" from the wall):
- The picture is 27" wide, with its bottom edge 7 9/16" below the lens centre and its top edge 7 9/16" above. The axis passes through the picture's centre, and the height agrees with 16:9 to 0.4%.
- At that distance the throw ratio is 0.95, but the projection point sits about 1.2" behind the front glass. **Effective distance: 26.92"**, throw ratio 1.00. Stored as `lens_s=0.50149 lens_tb=-0.28092 lens_tt=0.28325`.

Widths of the white border, outer edge to outer edge:

| Pose | Top | Bottom | Top/bottom | Model |
| --- | --- | --- | --- | --- |
| Bottom detent (0.1°), no warp | 26 7/8" | 27 1/8" | 0.991 | 1.000 (baseline) |
| 20.1°, no warp | 32" | 26 1/4" | 1.219 | 1.242 (tape D) / 1.230 (D 26.92) × baseline |
| 20°, warp, tape D 25.75 | 25 3/4" | 26 1/4" | 0.981 | 0.981 predicted from the fit |
| **20.0–20.3°, warp, D 26.92** | **25 3/4"** | **26"** | **0.990** | 0.991 (= baseline) |

- **The fit:** both the uncorrected and the first corrected measurement were 1% off with the tape distance, and in the direction a projection point behind the glass predicts. Fitting D to the uncorrected shape predicted the corrected one exactly, and the refitted lens then corrected the picture to the baseline.
- **The baseline −0.9%** (top narrower at level, with no warp) is outside the sensor's view: the wall, or the detent, is slightly off vertical. A manual trim could take it out; auto can't see it.
- **For `lens`:** measure DIST to the lens front and add ~1.2", or do as here: measure the uncorrected top/bottom ratio at a known tilt and fit D.

- **Model:** the projector is a pinhole. Frame position (u, v) leaves the lens along tangents x = s(2u − 1) and t = tt − (tt − tb)·v.
  - Pitching by φ toward a surface at unit distance puts that ray at R(φ)·(x, t, 1). The rotation matrix itself is the homography.
  - The frame lands as a trapezoid. The picture goes in the largest rectangle with the panel's aspect that fits, standing on the near (narrow) edge, letterboxed inside by the video's aspect.
  - One 3×3 matrix maps a frame position to a picture position. The shader only divides and samples, and returns black outside the picture.
- **Mirror:** under a top/bottom flip, the lens tangents and φ change sign; left/right flips change nothing. Verified: the `ceiling` frame is pre-warped narrow at the bottom (the panel's raw top, which is the far edge when inverted), and the picture is still upright.
- **Auto past 45°:** the surface is the ceiling (or the floor), so the correction is pitch − 90 (or + 90). `h713-keystone` publishes `surface=`.
- **Files:**
  - `tools/video/shaders/keystone.glsl`: an `OUTPUT` hook template.
  - `tools/video/keystone.lua`: runs in mpv. It polls the state every 0.5 s and writes a copy of the shader per matrix to `/tmp`, because `vo=gpu` has no `//!PARAM` (only gpu-next does).
  - It sets `keepaspect=no` while the warp is on. mpv's own letterbox bars would clip a picture the warp moves down; the shader letterboxes instead.
  - The warp turns on at |correction| ≥ 0.5° and is removed below that. A level projector costs nothing.
- **h713-play:** once the lens is measured, the GPU route always loads the script, so a tilt mid-playback is followed. A correction due at start forces the GPU route; `--route=plane` refuses it.
- **Lens:** `h713-keystone lens DIST WIDTH BOTTOM [TOP]` takes tape measurements. The projector must be level on its bottom detent, square to a wall. DIST is lens to wall; BOTTOM and TOP are the picture's edge heights above the lens centre. The height follows from the 16:9 square pixels, so TOP only checks it (±10%). Nothing is assumed.
- **Verification so far:**
  - `tools/video/keystone-check.py` inverts the Lua's matrices and casts the picture's corners through an independently written ray model: 15/15 land as the right rectangle. It does catch a 0.2° pitch error, a sign error and an aspect error.
  - **On the GPU:** test cards played through mpv at 20°, grabbed with `scanout-grab` (6 grabs merged, because single grabs miss rows). The slanted side edges sit within 0.6 px of prediction on every interior row of the 16:9 and 2.39:1 cards.
  - **Live:** 20° → 0° → 20° and a mirror change mid-playback switch the warp on, off and back.
- **Known limits:**
  - mpv's OSD (seek bar, messages) is drawn after every shader hook in `vo=gpu`, so it stays unwarped; subtitles are warped (below).
  - Digital keystone discards the far edge's resolution.

### Follow-ups (2026-10-06): roll, subtitles, mid-file handover

- **Roll.** The warp now rebuilds the projector's full attitude from the published pitch, roll and upside-down flag. It takes the lens as facing the wall square, since yaw is invisible to gravity.
  - The display mirror enters as R·D with D = diag(±1, ±1, 1). That is not a pure rotation for the rear modes.
  - The picture keeps the orientation the mirror gives the unwarped frame: upright for front and ceiling, mirrored for rear.
  - The daemon publishes `level_deg`, the roll to correct. It is non-zero only in `auto` on a wall; on a ceiling the picture's rotation is the projector's yaw.
- **Largest fit.** The picture is now the largest level rectangle inside the frame's footprint, found by bisecting on width over the feasible centres (the edges moved in by the rectangle's half extent).
  - For pure pitch this is **not** the old "stand on the near edge" rectangle: at 20° with this lens, the old one left the far edge unused. The new rectangle touches the far edge and both sides, and is ~3% wider.
  - The wall result above was measured with the old rule. Its shape check stands, because the model is the same.
- **Checker.** `keystone-check.py` is now fully independent of the Lua. It builds the attitude from Euler angles solved numerically to the published values, applies the mirror to panel positions, takes the expected orientation from where the unwarped frame lands, and compares the size against a brute-force largest-rectangle search.
  - 360/360 pass: 2 lenses × front/rear/ceiling/rear-ceiling × 5 pitches × 3 rolls × 3 aspects.
  - Mutants fail: a roll sign error (0/30 pass), a wrong mirror with roll (0/30), and the right shape but 2% smaller (0/12).
  - The mutant rows that still pass are genuinely equivalent corrections: zero pose, or pitch-only with a centred lens.
- **GPU with roll** (20° pitch, 5° roll; 6 merged grabs): all four slanted edges sit within 0.6 px of the matrix.
- **Subtitles.** While warping, the script sets `blend-subtitles=video`, so subtitles are drawn into the video and warp with it; it restores the setting afterwards. Verified: all 2020 pixels of a cyan test subtitle lie inside the warped picture, and its baseline tilts with the picture's bottom edge.
- **Surface choice fixed.** The daemon used to pick the ceiling or floor from `pitch_deg`, which is measured toward the projector's own top. Turned lens-up while still flagged upside down, it read −90° and chose the floor.
  - It now uses the lens's elevation in the world.
  - On a ceiling or floor, the correction is the lens's tilt from that surface's normal toward the projector's own top: upright by construction, so `keystone.lua` ignores the upside-down flag off a wall.
  - Smoothing now averages the gravity vector, not the angles. A turn of more than 3° counts as a new pose.
  - The daemon suite is 49/49, adding `level_deg`, the surface, and a lens 80° up reading −10° to the ceiling.
- **Mid-file handover.** When the lens is measured, `h713-play` runs a plane route under watch. If a correction comes due, it SIGTERMs `gst-plane-play`, which prints its position, and execs the GPU route with `--start` at that position.
  - Verified: plane-native at 0°, the state went to 20° → "handed over at 4.463 s"; mpv resumed at 00:00:04 with VA decode, warped.
  - A correction due at start (pitch or roll ≥ 0.5°) still goes straight to the GPU.
