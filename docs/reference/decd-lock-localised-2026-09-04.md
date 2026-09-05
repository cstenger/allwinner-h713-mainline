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
