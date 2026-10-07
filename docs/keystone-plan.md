# Automatic keystone: plan (2026-10-06)

> **Status 2026-10-06: Phase 2 DONE, verified on hardware.** `h713-keystone` and its service ship in the image. They publish the settled tilt and drive the ceiling flip. **Next: Phase 3**, the GL warp.
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
- **Settings:** `/etc/h713-keystone.conf` (with `--persist`) or `/run/h713-keystone/conf`. They are reread every window.
- **sh + mawk:** the product image has no python3.
- **Test:** `tools/sensors/h713-keystone-test.sh` runs on the board against a fake sensor and a fake mirror: 32 checks covering both flips, the refusal retry, the moving hold, hysteresis and persistence.

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

## Phase 3: the GL warp (open)

- **Lens geometry:** measure the vertical field of view and the optical offset. One photo-rectified frame at two known pitches is enough. With those, `keystone_deg` gives a homography: pre-shrink the far edge, so the wall shows a rectangle.
- **Warp:** a perspective shader on the GPU route (mpv user shader or `gles-play`). `h713-play` routes to the GPU when `keystone_deg` isn't zero.
- **Cost:** digital keystone loses resolution at the far edge. Stock accepts that loss.
