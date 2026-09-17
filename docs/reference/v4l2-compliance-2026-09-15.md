# v4l2-compliance on cedrus — 2026-09-15

**Update 2026-09-17:** [Patch 0121 fixes the remaining TRY_EXT_CTRLS failure](cedrus-controls-2026-09-17/README.md).
Compliance is now **49/49, zero warnings**. The comparisons below are historical.

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
| full series, `0110` reworked | 46/49 | + `Requests`, `blocking wait` |
| full series + `0114` (request validate), grab dropped | **48/49** | `TRY_EXT_CTRLS` only |

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

## FIXED by 0114 — and they were newly EXPOSED, not regressions

```
fail: v4l2-test-buffers.cpp(2753): ret != ENOENT (got 0)      test Requests
fail: v4l2-test-buffers.cpp(3085): q.reqbufs(node, 2)         test blocking wait
fail: v4l2-test-buffers.cpp(3139): testBlockingDQBuf(node, q)
```

Settled by reading `v4l-utils` at tag `v4l-utils-1.30.1`, the exact version of
the binary on the board. **`0110` does not break these. It makes them testable
for the first time.**

`testRequests` opens by hunting for a control it can drive
(`v4l2-test-buffers.cpp:2360`):

```c
    if (qctrl.type != V4L2_CTRL_TYPE_INTEGER &&
        qctrl.type != V4L2_CTRL_TYPE_BOOLEAN)
            continue;
    ...
    if (qctrl.minimum != qctrl.maximum) { valid_qctrl = qctrl; ctrl.id = qctrl.id; break; }
```

and gives up entirely if it finds none:

```c
    if (ctrl.id == 0) {
            info("could not test the Request API, no suitable control found\n");
            return (node->buf_caps & V4L2_BUF_CAP_SUPPORTS_REQUESTS) ? 0 : ENOTTY;
    }
```

Every control cedrus had before `0110` is a compound, U32 or menu type — the
`V4L2_CID_STATELESS_*` family plus `V4L2_CID_MPEG_VIDEO_H264_PROFILE`. **Not one
is INTEGER or BOOLEAN.** So on stock cedrus this test has always returned "OK"
after testing nothing, and line 2651 is not even reachable. `0110` adds
`V4L2_CID_ROTATE`, an INTEGER with min 0 != max 270, and the suite runs.

What it then finds is a real cedrus gap. `cedrus_request_validate()` only
rejects a request with no buffer or more than one; it never checks that the
current codec's controls are present, so a request carrying a buffer and an
unrelated control queues successfully. Compliance expects a stateless decoder to
answer `ENOENT` there:

```c
    // Stateless decoders might require that certain
    // controls are present in the request. In that
    // case they return ENOENT and we just stop testing
    // since we don't know what those controls are.
    fail_on_test_val(ret != ENOENT, ret);
```

The `blocking wait` failure is a knock-on. `fail_on_test_val` **returns** from
`testRequests` on failure, so the `test_streaming = false; break;` two lines
below never runs and neither does the cleanup after the loop: buffers stay
allocated and request fds stay open. The independent `testBlockingDQBuf` then
fails on its own `q.reqbufs(node, 2)` at 3085. Had cedrus answered `ENOENT`, the
test would have broken out cleanly and cleaned up.

So the fix is one change, in cedrus rather than in `0110`: make
`cedrus_request_validate()` require the current codec's controls in the request
and return `-ENOENT` when they are missing, as other stateless decoders do.
That is an upstream-worthy fix on its own merits — decoding a slice with no SPS,
PPS or slice params is meaningless, and today the driver accepts it.

**The baseline's 48/49 was inflated.** It skipped the entire Request API suite.
This is the same trap as the `vo=drm` black-panel bug: a passing suite that
could not fail. Ask what it is blind to.

## What this run does NOT cover

`test Composing: OK (Not Supported)` is compliance seeing `EINVAL` from
`G_SELECTION`, because the default output format is MPEG-2 and our selection
support is gated on H.264. **The entire compose surface added by this series is
invisible to a stock compliance run** — the compose/canvas split, the
rotation-swapped rectangles, and the known `COMPOSE` vs `COMPOSE_BOUNDS`
inconsistency under 90/270. Testing it needs a wrapper that sets an H.264 output
format first.


## Closed 2026-09-15 by patch 0114

Both are fixed; the driver scores **48/49**, and the only remaining failure is
the pre-existing `TRY_EXT_CTRLS`.

`cedrus_request_validate()` now checks the current codec's required controls
against the request's own control handler, following vicodec. Two things about
the fix are worth carrying forward:

- **It required dropping `0110`'s `v4l2_ctrl_grab()` at the same time.** A
  grabbed control cannot be set into a REQUEST either, so the grab moved the
  `Requests` failure from the queue (2753) to `VIDIOC_S_EXT_CTRLS` (2651)
  rather than fixing it. The ENOENT check is unreachable while the grab
  rejects the request's control set first. Neither change passes alone.
- **Only PER-FRAME controls may be required.** Marking SPS and PPS required
  broke every HEVC clip on the board — GStreamer's `v4l2slh265dec` sets the
  HEVC SPS once on the fd, while libva-v4l2-request repeats the H.264 SPS in
  every request. Per-sequence state is client-dependent; requiring it is a
  userspace break, which is exactly the objection Jernej Skrabec raised
  against the H.264 bounds patch validating in `try_ctrl`.
