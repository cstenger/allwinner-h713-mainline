# The live-MIPS lock is in the vsync ring rewrite — localised, not fixed

2026-09-04. Third mechanism proposed for this lock; the first two were wrong and
are retracted in [decd-videoinfo-handover](decd-videoinfo-handover-2026-09-04.md)
and [videoinfo-descriptor-decoded](videoinfo-descriptor-decoded-2026-09-04.md).

## The premise of the obvious test was wrong

The plan was "patch decd-client to skip the geometry writes". **`decd-client`
writes no registers at all** — it only issues ioctls (`DECD_IOC_FRAME_SUBMIT`,
`PM_HINT`). And the geometry writer in the driver,
`dec_reg_video_channel_attr_config`, **has no callers in our tree either**, the
same as stock. So neither the client nor the driver ever writes the
source-geometry block, and the two-master-contention-on-geometry story was
already dead before it was tested.

What the submit path *does* touch, from `dec_frame_queue_sync()` running in the
vsync handler: the four ring slots (Y at `0x05600070`, C at `0x05600084`,
VideoInfo at `0x05600098`), `int_to_display`, and the dirty latch. Our handler
owns **GIC SPI 142** and was measured firing at ~60/s (38238 -> 38358 over 2 s).

## The test

A module parameter gating that rewrite
(`patches/kernel/0094`, out of series), then, with the core alive:

```
insmod /root/sunxi-decd-nosync.ko suppress_vsync_sync=1
decd-client show /root/decd-test-frame.nv12 4000
```

**Result: the board survived.** Submit returned 0, `0x0306101c` still `1`,
zero oops. Every previous attempt at this locked the SoC.

So the lock lives in `dec_frame_queue_sync`'s register writes. That **rules out**
the ioctl path, the dma-buf import, the IOMMU mapping, the VideoInfo descriptor
and PM — all of which ran identically here.

## What it does NOT show, which matters

```
0x05600070  0x00000000     Y
0x05600084  0x00000000     C
0x05600098  0x00000000     VideoInfo
```

**No frame was delivered.** With the rewrite suppressed the ring is never
written, so "it survived" is not "we found a safe submit path" — it is only
"not writing the ring does not lock". The elog agrees: nothing but `sys`
heartbeats, no WCE activity.

This localises the fault to a handful of register writes. It does not yet
distinguish between:

1. **the 60 Hz repetition** — rewriting all four slots every vsync while the
   firmware is also programming source 0;
2. **`int_to_display`** — signalling the firmware at a moment it does not
   expect;
3. **writing those registers at all** while the window layer owns the source.

## SEPARATED — it is the repetition. One ring write is safe and delivers.

Same boot, `ring_writes_max=1` (exactly one rewrite permitted, then never
again), core alive:

```
FRAME_SUBMIT format=6 desc=112 repeat@+0x10=1 fence_fd=7
EXIT=0        core 0x00000001        ring_writes_done = 1

0x05600070  0xFFC00000     Y            <- populated
0x05600084  0xFFCE1000     C            <- populated
0x05600098  0x4D941000     VideoInfo    <- populated
```

**A frame reached the hardware with a live MIPS and nothing locked.** Zero
oops, IOMMU `INT_STA` clean. Contrast the default (unlimited) case, which locks
every time.

So of the three candidates above it is **(1), the 60 Hz repetition**. Touching
the ring with a live core is fine; rewriting all four slots every vsync is not.

**The architectural consequence.** Driving the ring from Linux's vsync handler
is wrong whenever the MIPS is alive — the firmware owns presentation, and on
stock it is the firmware that advances the ring. Our driver was written for the
MIPS-parked world, where Linux legitimately owns the display, and that
assumption does not survive here. A live-core mode should enqueue and let the
firmware repeat.

## But the window layer still does not react

With the frame genuinely in the ring, the elog *still* shows only timestamp `[0]`
records — bring-up. No `UpdateWce`, no `SetSignalInfo` beyond the initial one,
and `PanelWinNode.cpp:328` still reads `bypass`.

So delivering a frame is necessary and not sufficient: the window layer has to
be told, and writing the ring is not what tells it. That is the same gap the
blue test found, now reached from the other side and with the lock out of the
way.

## The superseded next-step note

The following was written before the budget test and is kept for the record:

## The next experiment separates them

Allow exactly **one** ring write and never repeat: submit, write the slots once,
skip every subsequent vsync. If that survives, the fault is the repetition (1)
and the fix is to stop driving the ring from Linux's vsync when the MIPS is
alive — which is architecturally what stock does, since the firmware owns
presentation. If a single write still locks, it is (3), and the ring is simply
not ours to touch with a live core.

## Method notes

- **Module/tree mismatch is real and it bit here.** The first build probed with
  `-ENOENT`; the board's working module is 62960 bytes and came from a
  *different* build tree. Matching it by SHA-256 against
  `/lib/modules/6.18.38/.../sunxi-decd.ko` found the right tree
  (`0b698d85...`), and the rebuilt module then probed and logged
  "tvtop link unavailable (-19); continuing unordered" — patch 0033's behaviour,
  absent from the tree first tried. Always match the tree by checksum before
  building a module to test against a running kernel.
- The `Bash` tool's working directory persists across calls, so a `cd` into a
  build tree silently breaks later relative paths. Twice in this session that
  produced alarming-looking output ("`build/` does not exist"). Use absolute
  paths after any `cd`.
