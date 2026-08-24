# Mid-stream resolution change: a confirmed shim bug, not fixed

Measured 2026-08-24 with `tools/video/decode-reinit-test.sh`.

## What happens

Every vector before this one holds one resolution from first frame to last,
which is not what real files do — adaptive streams, broadcast splices and
concatenated recordings all change resolution mid-stream. Two vectors now
cover it (`r01` HEVC, `r02` H.264: three segments, two changes each).

| path | result |
| --- | --- |
| software | 75 / 150 frames, correct |
| **GStreamer `v4l2slh265dec`** | **ve+75 — decodes it in full** |
| our VA-API shim | **26 of 75 frames**, then `Timeout when waiting for media request` |

The engine recovers afterwards, and the oracle handling the same stream on the
same kernel is what makes this ours rather than cedrus's.

## Why

PR #38 sets the coded format exactly once, behind a process-wide flag its own
comment calls a HACK:

```c
// we declare SET_FORMAT_OF_OUTPUT_ONCE to ensure v4l2_set_format only gets
// called once (in the first RequestCreateSurfaces2 call ...)
```

ffmpeg reacts to a new SPS by destroying the context and its surfaces and
creating both again at the new size. With the flag latched, the driver is never
told: the engine keeps decoding at the old geometry until it stalls.

## Attempt 2, and a correction to attempt 1 — still NOT landed

**The heap corruption blamed on the fix below was probably not its fault.**
Those runs hit a device that had already been poisoned by an earlier crash —
`Failed to setup decoding job: -22` for *every* client, GStreamer included —
which was only discovered afterwards, because the "restore verified" check
compared md5 alone and a software decode reproduces it. Re-run from a clean
boot, the geometry fix gets `r01` (HEVC) through the resolution changes.

**But `r02` (H.264, 1280x720 → 320x240 → 1280x720) takes the whole board
down.** ssh still accepts connections, no command completes, and only a
*power cycle* recovers it — not even a reboot, because reboot needs a command
to run. That is worse than the bug it replaces, which merely failed the
decode.

So the H.264 path reaches something the HEVC path does not, and per-surface
V4L2 state is still not being rebuilt in step with the format. The
work-in-progress diff is kept as
`patches/libva-v4l2-request/WIP-0007-resolution-change-INCOMPLETE.patch`, out
of `series`, with that warning in its header.

**A practical note for whoever picks this up:** every failed attempt here can
cost a physical power cycle, because a client that dies mid-decode takes the
engine down for everything (see below). Budget for that, and prefer the HEVC
vector for iteration — it is the one that fails safely.

## The original diagnosis — the flag

Replacing the latch with a geometry comparison is obviously right, and
`RequestDestroyContext` has already streamed both queues off and released their
buffers by that point, so `S_FMT` is legal there. It is also **not sufficient**.
With that change the failure moves rather than disappears:

- non-ASAN build: `malloc(): invalid size (unsorted)` — ffmpeg aborts
- ASAN build: no memory error at all, and the true fault surfaces —
  **`VIDIOC_QBUF` returns EINVAL** after the change

So per-surface V4L2 state (buffer indices, mapped lengths, the cached
`video_format` and the sizes derived from it) has to be rebuilt in step with the
format, not just the format itself. That is a state-machine change across
`surface.c`, `picture.c` and `image.c`, and a half-done version corrupts a
client's heap — which is precisely the kind of change this project has twice
this session refused to ship on a partial result.

**Left as a known limitation with a reproducer.** The work-in-progress diff is
not in `patches/libva-v4l2-request/series`.

## A second finding, worth as much as the first

While the broken build was crashing mid-decode, **the engine was left unusable
for every client**: `cedrus 1c0e000.video-codec: Failed to setup decoding job:
-22`, repeatedly, for GStreamer as well as the shim, until a reboot. So a client
that dies mid-decode can take the device down for everything else.

That is a robustness gap in the same family as the concurrency deadlock fixed
earlier — a production system meets it the first time a player segfaults — and
it is not fixed here either. It was found only because a *crashing* client was
in play, which no gate had produced before.

**And it nearly poisoned two other results.** After restoring the good driver I
"verified" it by md5 alone, which passes for a software decode, so a stuck
engine went unnoticed and the first two leak-test runs measured a CPU decoder.
Both harnesses now fail on `ve+0` rather than reporting a number, which is the
rule every other gate here already applied.
