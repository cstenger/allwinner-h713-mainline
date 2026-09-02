# H713 runtime-IOMMU handoff — 2026-09-01 (RESOLVED)

**Moving decoded video renders on the panel through segmented IOVAs at 27 fps
with zero IOMMU faults.** The full result, with all six runs and the register
evidence, is in
[`docs/reference/iommu-runtime-flip-ordering-2026-09-01.md`](reference/iommu-runtime-flip-ordering-2026-09-01.md).
Read that first; this document is the operational handoff.

An earlier revision of this file described a race between the visible wrapper's
route rewrite and the first frame submit, and staged a retry to test it. **That
hypothesis was wrong.** The failed runs it was based on are preserved below,
because re-running a known-good control against them is what found the real
answer.

## The rule that matters

> Do the master-2 `IOMMU_BYPASS 0x7c -> 0x78` transition while the DECD **video
> source is disabled** — only the inherited logo route live. After the flip is
> spent, the video route and visible playback are clean.

The video source rests at base `0x00000000` with inherited 1920x1088 geometry,
so enabling it starts a raster scan through the first ~2 MB of physical memory.
Harmless under bypass; L1-invalid the instant translation arrives.

## Working bench procedure

**On a kernel carrying 0076, just run the test.** Boot a RAM FIT, load modules by
path with hash checks, confirm the logo is on the panel, then:

```sh
ARMED=yes ALLOW_STOPPED_MIPS=yes PLAYER=/root/freeze-at/decd-play-freeze-at \
  /root/iommu-0076/decd-visible-sequence.sh --play /root/leota-720p.h264 300
```

**Confirm the logo is visible after loading the modules, every time.** U-Boot
prints `boot logo published and committed` on a black boot too, so the log is not
a control. Two runs in this session were watched against a panel whose state was
unknown, and "the test showed nothing" is indistinguishable from "the panel died
an hour ago".

**Fallback for a kernel without 0076** — spend the flip nonvisibly first:

```sh
# Step 1 — nonvisible. Spends the flip against the logo route. Logo stays up.
DECD_FREEZE=1 DECD_FREEZE_AT=60 \
  /root/freeze-at/decd-play-freeze-at /root/leota-720p.h264 300

# Step 2 — visible. No flip occurs; dec->iommu_runtime_enabled is already set.
ARMED=yes ALLOW_STOPPED_MIPS=yes PLAYER=/root/freeze-at/decd-play-freeze-at \
  /root/decd-visible-sequence-fence.sh --play /root/leota-720p.h264 300
```

Provisioning that works, from the U-Boot prompt after a `reboot`:

```sh
python3 tools/serial/boot_kernel.py --secs 55 \
  --load /root/fits/h713-kernel-decd-iommu-runtime-segmented.fit \
  --extra "modprobe.blacklist=sunxi_decd,sunxi_cedrus,sunxi_scanout_dmabuf"
```

Then `insmod` in the order `sunxi-scanout-dmabuf`, `sunxi-decd`,
`sunxi-cedrus`, verifying each SHA-256 first. Blacklisting at boot and loading
by path is not optional: `CONFIG_SUNXI_DECD=m` with no `CONFIG_MODVERSIONS`
means a stale `.ko` from `/lib/modules` loads silently against a new kernel.

Pre-test state should read: `0x02010030 = 0x7C`, `0x0306101c = 0` (MIPS parked),
DECD interrupt counts zero, no faults in `dmesg`.

## The ordering is now a driver behaviour

**DONE — `patches/kernel/0076-misc-decd-flip-the-iommu-with-the-video-source-parked.patch`
is hardware-validated.** Patch 0075 flips inside `dec_frame_submit()`, the one
place guaranteed to be reachable with the video source already enabled. 0076
parks source 0 across the transition and re-enables it after `dec_reg_enable()`,
gated on the Y ring holding a real address. It applies on top of 0075 and shares
its out-of-series status.

Validated as the **first DECD session of a boot**, with no operator procedure:

- frozen frame 60: zero faults, `video source unparked onto 0xfe000000 after
  75 us`, operator-confirmed still, logo restored;
- moving playback: zero faults, 300 frames at 27.12 fps, 299 fence retirements,
  zero stalls, operator-confirmed animation, logo restored.

**The two-step procedure is no longer required** on a kernel carrying 0076. It
still works and remains the fallback without it.

`decd-visible-sequence.sh` was fixed alongside: its play branch enabled the video
source at a fixed `sleep 0.2`, long before any frame existed, putting garbage on
the panel for up to two seconds on a `--freeze-at` run. It now waits for the Y
ring to arm. With that in place the moving run needed **no park at all** — the
source was already disabled at flip time — so the wrapper ordering is the
mechanism and 0076 is the safety net. Keep both: userspace should not enable a
source with no frame behind it, and the driver should not assume it didn't.

Getting the unpark point right took three attempts, and the failures are
recorded in the reference doc because each moved the fault somewhere diagnostic:
restoring immediately after the flip faulted at exactly `0x00000000`, and
polling for the ring before `dec_reg_enable()` timed out with all four slots
still zero — a wrong *place*, not a short timeout.

**Still open, unrelated to the IOMMU:** after many short sessions in one boot,
moving playback has stalled waiting on a release fence (first at frame 210 with
cap 4, then frame 27 with cap 5), with no IOMMU fault. It did not reproduce
today — the third session of the boot ran `stalls=0`. Treat it as accumulated
cross-session DECD frame-manager/fence state. Do not claim the multi-session
lifecycle is complete.

## What was retracted

- "The IOMMU route is CLOSED — do not re-run it." The route works.
- "One master-2 fault wedges AFBD for the rest of the boot." The fault does
  wedge it, but it is avoidable. Design for zero faults, not one per boot.
- Patch 0074's contiguous Cedrus pool is **not required**. A buffer with 56
  physical breaks and a 32 KiB longest run played correctly.
- The banding was never a surface-reuse race. Patch 0071 (release-fence UAF)
  stands as a correct independent fix.

## The failed runs, kept as the record

Four visible runs failed before the control caught the problem. All four flipped
translation on while the video route was live, and all four faulted at a low
address inside the first 2 MB:

| run | configuration | fault VA | panel |
| --- | --- | --- | --- |
| 1 | segmented, moving, old wrapper | `0x29000` | blue, then black |
| 2 | segmented, moving, reordered wrapper | `0x26000` | bad frame, then magenta |
| 3 | segmented, frozen frame 60 | `0x81000` | garbage, then near-black |
| 4 | contiguous (0074), frozen frame 60 | `0x16000` | garbage, green, then black |

Run 2 is the important negative: it used a wrapper reordered specifically to
remove the suspected race, and failed identically. That eliminated the race.

Runs 3 and 4 are the controls that broke the deadlock. Both were faithful
reproductions of results recorded as successful — same FIT, same module hashes,
same wrapper, same player, bit-exact decoded output — and both failed. That
proved the fault was in the setup rather than in any theory about moving
playback, and pointed at ordering.

Two lessons worth keeping:

- **Userspace completion is not proof of visible playback**, and a readback-only
  restore is not proof the fetch engine recovered. Every failed run above
  reported `PLAY_COMPLETE frames=300` and restored plausible register values.
- **Re-run a known-good control before diagnosing a new failure.** Four runs
  went into a bug that did not exist.

## Recovery

A master-2 fault with the video route live leaves the panel wedged and the logo
gone. Reboot over serial; U-Boot republishes the logo and stops at `=>` with
`bootdelay=-1`:

```sh
python3 tools/serial/console.py --wait 25 'reboot'
```

Do not attempt to repair it with another submission.

## Hazards that still stand

- **Do not run real Cedrus traffic with the display MIPS alive.** That
  combination hard-locks the SoC with no watchdog. Park the MIPS; the Linux DECD
  IRQ owns the ring. Static frames with MIPS alive are fine.
- **Do not unload `sunxi_decd` or invoke DECD PM-off after a test.** Both can
  reset or clock-gate hardware shared with the adopted logo path. Blacklist and
  reboot instead.

## Repository state

- Branch `h713-display-video-path`. Nothing flashed.
- Patch 0075 remains out of series and pairs with the out-of-series 0068.
- `patches/kernel/series` ends at 0074.
- The dirty `external/u-boot` worktree is unrelated; preserve it.

Artifacts, all verified on the board this session:

```text
2b1581e6b023553ff6f31fc7161bb36b33e4693aa3fdcafb845ed08cd175307d  h713-kernel-decd-iommu-runtime-segmented.fit
bd72d65d73282ebbd8ec50eb97f3dbfaa0c5d945346e1373e6a3bc728d05bcf6  h713-kernel-decd-iommu-runtime-contiguous.fit
fae727a5a1348016a766b29b1e9d73a63ba1a645b988b610519ec69d287e1d82  segmented/sunxi-cedrus.ko
ffe199eb5939800b97569eadf148a5b768e5ec9be841e550fd6ad2ab8eff4392  contiguous/sunxi-cedrus.ko
b8724b1d07be15869a37750c78d827be109dd17eac044701599e3346e1d99423  sunxi-decd.ko          (both builds)
280e5460577a4105d52c4c2d1b07a3ea012006f80bf8730ecec1a1bef0865f49  sunxi-scanout-dmabuf.ko (both builds)
```

The two configurations differ **only** in `sunxi-cedrus.ko` and the DTB's
reserved-memory node; the display driver is byte-identical in both.
