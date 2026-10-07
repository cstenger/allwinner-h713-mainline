# Automatic keystone: plan (2026-10-06)

> **Status 2026-10-06: Phase 3 built and verified on the GPU (scanout); needs the lens measured and a look at the wall.** Phase 2 DONE, verified on hardware. `h713-keystone` and its service ship in the image. They publish the settled tilt and drive the ceiling flip. **Next: Phase 3**, the GL warp.
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

> **Status 2026-10-06: built and verified on the GPU by scanout grab. Waiting on the lens measurement and a look at the wall.** Without a measured lens, everything stays idle.

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
  - Roll is not corrected.
  - The OSD is drawn after the warp, so it isn't warped.
  - A plane route already playing doesn't warp when the projector is tilted mid-file.
  - Digital keystone discards the far edge's resolution.
