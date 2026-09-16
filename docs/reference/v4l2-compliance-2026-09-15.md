# v4l2-compliance on cedrus — 2026-09-15

First compliance run on this driver. `v4l2-compliance 1.30.1`, `-d /dev/video0`,
no streaming flags. cedrus is a module, so every arm below was swapped in with
`tools/install-kernel-module.sh` with **no reboot** — that is what made a clean
A/B affordable, and it is the way to do this again.

## Result

| arm | score | failures |
| --- | --- | --- |
| baseline — this series' cedrus patches reverted | **48/49** | `TRY_EXT_CTRLS` |
| scaling only — `0110` reverted, `0097/0099/0101/0102/0104/0107` in | **48/49** | `TRY_EXT_CTRLS` |
| full series, `0110` as first written | 45/49 | + `G/S_CTRL`, `Requests`, `blocking wait` |
| full series, `0110` reworked | **46/49** | + `Requests`, `blocking wait` |

Three conclusions, each from the A/B rather than from reading code:

1. **The scaling work is compliance-clean.** Reverting `0110` alone returns the
   score to baseline exactly, so `0099`, `0101`, `0102`, `0104` and `0107`
   introduce nothing.
2. **All three regressions came from `0110`,** the rotation patch.
3. **`TRY_EXT_CTRLS` is pre-existing**, present with the whole series reverted:
   `v4l2-test-controls.cpp(939): try_ext_ctrls returned an error (22)`. Not ours;
   worth reporting upstream.

## Fixed: the control range failure

```
fail: v4l2-test-controls.cpp(517): invalid maximum range check
```

`0110` did state-dependent validation in `.s_ctrl`, returning `-EINVAL` when the
output format was not H.264. The control framework probes a control's range
against the **current** configuration, and the default output format is MPEG-2,
so every non-zero value was refused and the advertised maximum of 270 was
unreachable.

Reworked: `s_ctrl` stores whatever the range allows and never fails;
`cedrus_rotation()` reports zero unless the format is H.264, so the value is
inert rather than rejected; `v4l2_ctrl_grab()` on the capture queue replaces the
`EBUSY` that `s_ctrl` used to invent. The four-quadrant rotation matrix still
passes at 0/90/180/270 after the rework, so the behaviour did not change.

## Open: Requests and blocking wait

```
fail: v4l2-test-buffers.cpp(2753): ret != ENOENT (got 0)      test Requests
fail: v4l2-test-buffers.cpp(3085): q.reqbufs(node, 2)         test blocking wait
fail: v4l2-test-buffers.cpp(3139): testBlockingDQBuf(node, q)
```

Introduced by `0110` and **not** fixed by the rework. What is established:

- They are not caused by the `s_ctrl` error paths: removing those fixed only the
  range check.
- They are not caused by `v4l2_ctrl_grab()`: building without the grab scores the
  same 46/49. The grab only moves where `Requests` fails — 2753 without it, 2651
  (`doioctl(node, VIDIOC_S_EXT_CTRLS, &ctrls)`) with it.
- The ENOENT check requires a stateless decoder to reject a request that is
  missing its mandatory contents. `cedrus_request_validate()` returns `-ENOENT`
  when the request carries no buffer, and nothing in `0110` touches it, so the
  mechanism is **not yet identified**.

The one structural difference `0110` introduces is that `V4L2_CID_ROTATE` is the
only **plain integer** control in a handler whose other controls are all
payload-carrying stateless codec controls, and
`v4l2_ctrl_request_clone()` copies every control into every request with no
filtering by flags. That is the lead, not a conclusion.

Next step, in order: instrument `cedrus_request_validate()` to log what the
request actually contains on the failing call, and read the 1.30.1 sources for
`v4l2-test-buffers.cpp` around those lines — the linuxtv git web view is behind
a bot wall, so use a mirror or `apt-get source v4l-utils`.

## What this run does NOT cover

`test Composing: OK (Not Supported)` is compliance seeing `EINVAL` from
`G_SELECTION`, because the default output format is MPEG-2 and our selection
support is gated on H.264. **The entire compose surface added by this series is
invisible to a stock compliance run** — the compose/canvas split, the
rotation-swapped rectangles, and the known `COMPOSE` vs `COMPOSE_BOUNDS`
inconsistency under 90/270. Testing it needs a wrapper that sets an H.264 output
format first.
