# Decode: from "correct" to "production ready"

Started 2026-08-22. The bit-exactness gates say the decoder produces the right
pixels for good input — 5/5 H.264, 5/5 HEVC, an independent GStreamer oracle
agreeing on every vector. That is a claim about **correctness**, and it was
being read as a claim about **readiness**, which it is not. Three properties
stood between the two, and none of them had ever been measured:

| | what was actually known before |
| --- | --- |
| endurance | longest hardware decode on the fixed kernel was one gate run — 25–60 frames per vector, under a minute total |
| recovery | a `frame processing timed out!` was *believed* to wedge the VE for every client until reboot, and was documented as a trap for the test harness rather than treated as a defect. **That belief turned out to be wrong — see §3** |
| bad input | every stream ever fed to this decoder was well-formed |

This document is those three, plus one more that turned up while writing them
(concurrent clients, which nothing had exercised either).

---

## 1. The timeout path: a real code defect that costs nothing

> **Read §3 before acting on this section.** The premise it was written from —
> that a decode timeout wedges the engine — was refuted by measurement: the VE
> recovers from ten consecutive timeouts, for the shim and for GStreamer alike,
> with and without the fix. The code analysis below is still correct and is
> kept because it is worth knowing; the conclusion that it *matters* is not.
> Patch 0057 is consequently **out of `series`**.

Read the code first, because the answer is legible there and it explains why
this looked like an H713 problem that upstream would never see.

`cedrus_watchdog()` in `cedrus_hw.c` does exactly three things: print, reset,
finish the job.

```c
v4l2_err(&dev->v4l2_dev, "frame processing timed out!\n");
reset_control_reset(dev->rstc);
v4l2_m2m_buf_done_and_job_finish(..., VB2_BUF_STATE_ERROR);
```

**It resets half the engine.** `dev->rstc` is the `ve` reset line. This board's
`video-codec` node carries `reset-names = "ve", "ve3"` — confirmed on the
running board, not inferred from the DTS:

```
# tr -d '\0' < /proc/device-tree/soc/video-codec@1c0e000/reset-names
veve3
```

Every other power transition in the driver handles both lines.
`cedrus_hw_resume()` deasserts `ve` then `ve3`; `cedrus_hw_suspend()` asserts
`ve3` then `ve`; and since patch 0040, `cedrus_stop_streaming()` pulses both on
every teardown. The timeout path is the one place that was never updated when
the second reset arrived for this SoC. Upstream has no `ve3` at all — on H3,
A64 and H6 there is one reset line and `reset_control_reset(dev->rstc)` really
is the whole engine — so this is a porting gap, not an upstream bug.

**It acknowledges nothing.** The watchdog never calls the codec's
`irq_disable()`/`irq_clear()`, though `cedrus_irq()` calls both on the normal
path. The VE interrupt is `IRQ_TYPE_LEVEL_HIGH` on this board (patch 0024's
node: `interrupts = <GIC_SPI 75 IRQ_TYPE_LEVEL_HIGH>`), and after the watchdog
has run, `cedrus_irq()` takes its `!cancel_delayed_work()` early return —
acknowledging nothing. A status bit the engine left set is therefore re-raised
indefinitely.

Patch **0057** fixes both, behind `sunxi_cedrus.watchdog_full_reset` (default
on, writable at runtime) so the two behaviours can be compared *inside one
boot*.

Two safety questions were answered before touching it rather than after:

- **Is register access legal from the watchdog?** Yes.
  `pm_runtime_resume_and_get()` is taken in `cedrus_start_streaming()` on the
  OUTPUT queue and released in `stop_streaming()`, so the device is powered and
  clocked for the whole streaming session, watchdog included.
- **Is pulsing both resets safe at runtime?** It is already done: patch 0040
  pulses exactly this pair in `stop_streaming()`, which runs once per decode.
  A decode soak performs several hundred of them in its first ten minutes.

### Inducing the fault on purpose — and why this one failed

*(Patch 0058 did not work as designed; see §3. Kept for the register fact it
established.)*

A recovery path cannot be tested by hoping a malformed stream stalls the engine.
Patch **0058** (DEBUG, deliberately not in `series`) adds
`sunxi_cedrus.fault_stall_hevc=N`: the next N HEVC slices are programmed with a
bit length four times the data actually queued, so the VLD starves waiting for
bits that were never sent.

The choice matters. The easy fault injections — skip `trigger()`, or finish the
job early — make the watchdog fire on an engine that is perfectly healthy, and
so test nothing about recovering one that is stalled. Over-programming the bit
length reproduces the real stall. It is bounded (a few hundred kB at most), the
VE is behind the IOMMU on this board since patch 0042, and the count decrements
so one write buys exactly one stall — the *next* decode is the measurement.

`tools/video/watchdog-recovery-test.sh` runs the A/B, fixed arm first, and then
asks a diagnostic question worth having on record: once wedged, does reloading
the module bring the engine back? If yes the stall lives in driver state; if no
it is in the hardware and only a reset sequence clears it.

---

## 2. The gates that did not exist

Three new harnesses, all scoring properties the bit-exactness gates cannot see.

**`soak-decode.sh`** — the same bit-exactness check, made continuously for
hours. Every iteration re-asserts the md5, because a soak that only checks "did
it exit 0" would have passed straight through the scaling-list bug fixed in
libva patch 0005: 25 frames decoded on the engine, to the wrong answer, exit
status 0. It also watches the VE interrupt delta (a flat counter with a correct
md5 is a silent software fallback, which is a failure however good the output
looks), per-vector wall time (throughput decay as the board heats), and the
kernel's own complaints.

Nothing is written to disk per iteration — frames go down a pipe to `md5sum`,
because 82 MB a vector for hours is pointless eMMC wear and `/tmp` is a tmpfs
whose ENOSPC would produce a truncated file with a perfectly valid md5.

> **A trap this harness had to be taught:** raw `CmaFree` is not a leak
> indicator. It fell 42,908 kB → 7,156 kB across a 100-second run and looked
> exactly like a leak, then returned to **115,704 kB** — higher than the
> starting value — the moment caches were dropped. CMA hosts movable
> allocations, so the page cache lives there legitimately. The before/after
> pair is now taken after reclaim; the heartbeat value is labelled `cma_raw`
> and is a liveness signal only.

**`decode-robustness-test.sh`** with **`make-bad-streams.sh`** — sixteen
deliberately malformed streams (truncated at a NAL boundary and inside one,
bit-flipped payload, bit-flipped headers, empty, garbage after valid parameter
sets, no first slice, every NAL halved), derived deterministically with seed
713 from `h01` and `v03`.

The verdict is **not** the decoder's exit status. Wrong output from a corrupt
stream is not a defect and refusing to decode it is not a defect; a decoder
that is dead for the *next* stream is. So every case is followed by a recovery
check that decodes a known-good vector and demands bit-exactness, and the run
stops at the first wedge because everything after it would be measuring the
wedge rather than the case.

The gate reports the VE interrupt delta per case, so it is visible rather than
assumed which cases actually reached the hardware: ffmpeg parses headers in
software, so a corrupted SPS is usually refused before the engine is ever
opened. That is a legitimate outcome — it tests ffmpeg, not us — and the cases
that exercise the engine are the ones that keep headers valid and damage the
payload.

**`decode-concurrency-test.sh`** — cedrus is one m2m device, and every test in
this project had opened it alone. Two failure modes are invisible to a
single-client test: jobs interleaving while state does not (one client's
picture parameters leaking into another's frame, so both "succeed" and at least
one is wrong), and a device-wide action taken for one client breaking another's
job — which is precisely the risk patch 0040's own comment flags about its
reset. Clients decode *different* vectors across a codec boundary, so a mix-up
between them cannot hide.

---

## 3. Results

### Endurance: PASS — 2 hours, 195,332 frames, nothing moved

```
SOAK-DECODE DONE t=7201s
  iterations   5238  (5238 pass, 0 fail, 0 software fallbacks)
  frames on VE 195332
  timeouts     0
  oops/BUG     0 -> 0
  CmaFree      115760kB -> 115816kB   (delta 56kB, both after reclaim)
```

Ten vectors in rotation, md5 re-verified on every one of 5,238 iterations. The
VE interrupt count rose by 195,332 — one per frame, so every iteration really
ran on the hardware. Per-vector wall time did not drift (1080p high: 2,799 ms
at the end against 2,798 ms on the first iteration; 640x480 HEVC: 708 ms
against 740 ms) at 58–61 °C throughout, so there is no thermal decay to
report at the 1296 MHz ceiling.

Against the previous longest hardware-decode evidence — a single gate run of
25–60 frames per vector — this is about **3,000x the exposure**.

### Bad input: PASS — 16 of 16, and the engine survived every one

Three of the sixteen stalled the engine hard enough to fire the watchdog
(`b03-h` bit-flipped payload, `b04-h` bit-flipped headers, `b07-h` no first
slice). All three recovered: the next known-good decode was bit-exact.

```
b03-h-bitflip-payload.h265         err(251)   ve+2     ok     WATCHDOG TIMEOUT
b04-h-bitflip-headers.h265         err(251)   ve+1     ok     WATCHDOG TIMEOUT
b07-h-no-first-slice.h265          err(251)   ve+0     ok     WATCHDOG TIMEOUT
...
R1: 16 pass, 0 fail
```

No hangs, no kernel complaints, no wedges. Note the `ve+N` column: the H.264
truncation cases decoded 30–60 frames of a damaged stream and returned
success, which is a decoder being permissive rather than a defect, and the
header-corruption cases never reached the hardware at all because ffmpeg
refused them in software first.

### The documented "a timeout wedges the VE" is REFUTED

This was the premise of patch 0057 and of a standing operational rule in this
repo ("reboot between runs once anything has timed out"). It does not hold:

| test | result |
| --- | --- |
| one timeout, then the **shim** decodes | bit-exact |
| one timeout, then the **GStreamer oracle** decodes | bit-exact |
| **ten** timeouts back to back, then decode | bit-exact |
| A/B: `watchdog_full_reset=Y` vs `=N`, same boot | **both recovered** |

So the engine comes back from a decode timeout with or without the second
reset line. **Patch 0057 fixes nothing this hardware can be made to
demonstrate**, and it is therefore NOT in `series` — it stays on disk with
this result attached, the way 0052 and 0054 did. The code observation behind
it is still true (the watchdog resets `ve` but not `ve3`, and acknowledges no
interrupt on a level-triggered line); what is false is that this costs
anything observable.

Patch 0058 failed differently and taught something worth keeping:
over-programming `VE_DEC_H265_BITS_LEN` by 4x did **not** starve the VLD — the
engine decoded all 25 frames anyway, with the injection message in dmesg
proving the knob fired. **That register is an upper bound, not a promise the
hardware waits on.** The stall that does work is real damage to slice data.

### Concurrency: FAIL — three clients deadlock the engine

The one gate that found a defect, on its first run.

| clients | mix | result |
| --- | --- | --- |
| 2 | both HEVC, through GStreamer | bit-exact, 0 faults, 0 timeouts |
| 2 | both HEVC, through the shim | bit-exact, 0 faults, 0 timeouts |
| 2 | **HEVC + H.264**, through the shim | bit-exact, 0 faults, 0 timeouts |
| **3** | mixed | **deadlock** (n=2 reproductions) |

Three concurrent decoders leave one stuck in `D` state and unkillable —
`SIGKILL` is pending but never delivered, because the task is inside:

```
[<0>] v4l2_m2m_cancel_job+0xe0/0x1e8
[<0>] v4l2_m2m_streamoff+0x2c/0x1c4
[<0>] v4l2_m2m_ioctl_streamoff+0x18/0x24
[<0>] v4l_streamoff+0x20/0x2c
```

`v4l2_m2m_cancel_job()` waits for `TRANS_RUNNING` to clear on a job that never
completes. From there the VE is dead for every client and only a reboot
recovers it — **this, not a decode timeout, is the wedge this project has
been describing.**

Two observations narrow it. The first reproduction came with IOMMU page faults
on both VE master ports (2 on master 0, 8 on master 1) and 28 watchdog
timeouts; **the second had neither — zero faults, zero timeouts, same
deadlock.** So the faults are a symptom of the same disorder, not its cause,
and the defect is in job/context lifetime rather than in addressing. Worth
noting that cedrus supplies no `job_abort` op, which is exactly what
`v4l2_m2m_cancel_job()` calls before it starts waiting.

**Not fixed here, and deliberately not guessed at.** It is a real kernel bug
in territory (m2m job lifetime across contexts) where a wrong fix is worse
than a documented limitation.

---

## 4. Where decode actually stands

**Ready:** single-client decode of 8-bit H.264 and HEVC. Bit-exact on 11
vectors including scaling lists and lossless, 195,332 frames of soak with no
drift, survives every malformed stream tested, and recovers from decode
timeouts by itself.

**Not ready:** three or more simultaneous decoders deadlock the engine. Two
are safe, including across codecs. Anything scheduling decode work should
serialise it or hold to two clients until the m2m lifetime bug is fixed.

**Still out of scope, unchanged:** 10-bit (no 10-bit capture format in
mainline cedrus), and tiles (no encoder here can produce them).
