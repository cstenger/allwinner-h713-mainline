# Coupled decoder reset (0298, 0305–0308) — November 16, 2026

**Status: the 0298 failure reproduces on our tree. No fix is chosen yet.**

## Assessment

well0nez's group fixes three things:

- **0298:** VP9 leaves state in the shared H.265 engine, so concurrent
  VP9+H.265 decoding fails. Their fix is a `RST_BUS_VE` pulse at every
  codec switch.
- **0305–0307:** that bus pulse, landing while an AV1 frame is in flight,
  stalls the AV1 core and then the SoC. They add a hold/pulse guard, about
  430 lines, which forces the pulse anyway after 3 s.
- **0308:** releasing the VE's IOMMU ports next to AV1 also stalls it, so
  they skip that recovery while an AV1 stream is open. 0310 then disables
  AV1.

How this maps onto our tree (0209 release, boot `2cfc0d6c`):

- **Sequential streams are clean.** `cedrus_stop_streaming()` drops the
  runtime-PM reference with a plain `pm_runtime_put()`, so the VE suspends
  and is reset between back-to-back streams. Both failures need concurrent
  decode: two cedrus streams, or cedrus beside AV1. While an AV1 stream is
  open, its runtime-PM device link keeps the VE active, so sequential cedrus
  streams then skip that reset too.
- **Our concurrency gate never covered this.**
  [decode-concurrency-test.sh](../../../tools/video/decode-concurrency-test.sh)
  pools H.264, H.265 8/10-bit and MPEG-2 only. VP9 (0143), VP8 and AV1
  have never been decoded concurrently with another codec.
- **We already carry the AV1 hazard, in a rare form.** `cedrus_watchdog()`
  pulses `RST_BUS_VE` and calls `sun50i_iommu_reset_masters()` (0158) with
  no AV1 interlock. That is reachable only when a cedrus job times out
  while an AV1 frame is in flight.
- **0298 alone would make the hazard routine.** It adds a bus pulse to
  valid-stream operation, so any codec switch beside AV1 would trigger it.
  It must not land on its own.
- **A narrower candidate exists.** Our VE has a second reset,
  `RST_BUS_VE3` (CCU `0x69c` bit 18), which the AV1 node does not name. If
  a VE3-only pulse at a codec switch clears VP9's residue, it fixes 0298's
  failure without touching the line AV1 depends on. Untested.

## Reproduction

[`tools/video/decode-codec-pair-test.py`](../../../tools/video/decode-codec-pair-test.py)
decodes the pinned vectors (`/root/kernel-followups-20261114/vectors`, with
manifest software references) through stock GStreamer
`v4l2slvp9dec`/`v4l2slh265dec`. It hashes NV12 straight from a pipe and
records VE interrupts and new kernel lines per phase.

Boot `2cfc0d6c-17d6-44db-a5cf-874770f7a947`, cedrus module `1c8c87ba…`
(0209 production). The HDMI-in display pipeline was running; it does not use
cedrus.

| Phase | Result | VE IRQs | Kernel lines |
| --- | --- | ---: | --- |
| VP9 alone (300 frames) | exact | 308 | none |
| H.265 alone (300 frames) | exact | 300 | none |
| H.265 + H.265 at once | both exact | 325 | none |
| VP9 + H.265, round 0 | VP9 exact, **H.265 wrong** | 308 | `Failed to setup decoding job: -22` |
| short VP9 + short H.265, round 0 | VP9 exact, **H.265 wrong** | 52 | same |
| VP9 + H.265, round 1 | VP9 exact, **H.265 wrong** | 311 | same |
| short VP9 + short H.265, round 1 | VP9 exact, **H.265 wrong** | 52 | same |
| H.265 alone afterwards | exact | 300 | none |
| VP9 alone afterwards | exact | 308 | none |

- **4 of 4 pair runs fail, exactly as well0nez reported.**
- In each failing pair, H.265 delivers the full byte count with exit status
  0, but none of its frames is decoded: the pair's VE interrupt count equals
  VP9's alone, and the kernel logs a setup `-EINVAL` per job (639 this
  boot). The wrong frames are distinct, non-zero stale buffer contents.
- There are no timeouts or IOMMU faults, and single streams afterwards are
  exact. So this concurrency failure is contained: it is not a VE wedge and
  carries no SoC risk.

Raw evidence (SHA-256): `repro-results.json` `b72fffec…`, `repro.log`
`d21953dc…`, in `local/recovery/2026-11-16-decoder-reset/`.

## Next steps

1. **Narrow fix first.** A diagnostic cedrus that pulses only `RST_BUS_VE3`
   at a codec switch, scored with the same pairs (plus VP8 and H.264 pairs).
   0298's full `RST_BUS_VE` pulse is the comparison arm. Neither has run
   beside AV1 yet.
2. **AV1 interplay, with the operator present and UART connected:**
   - AV1 beside cedrus codec switching, under the chosen reset;
   - AV1 beside a damaged cedrus stream, to measure our existing watchdog
     and 0158 exposure.
3. **Arbitration only if step 2 shows it is needed,** and without a forced
   pulse after a timeout.
