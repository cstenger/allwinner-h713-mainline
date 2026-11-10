# The VideoInfo descriptor, decoded — and the IOVA hypothesis refuted

Parked-core check, 2026-09-04. Zero risk, no writes beyond one ordinary DECD
submit. It refutes the mechanism proposed in
[decd-videoinfo-handover-2026-09-04.md](decd-videoinfo-handover-2026-09-04.md).

## The check

DECD FIT (`dec` okay, `display` disabled), **core parked** (`0x0306101c = 0`),
IOMMU bypass `0x02010030 = 0x7C` before and after. One frame via
`decd-client show`. The client reported:

```
prepared image dma-buf at 0x6c500000 and VideoInfo dma-buf at 0x6c8f0000
FRAME_SUBMIT format=6 desc=112 repeat@+0x10=1 fence_fd=7
```

Registers afterwards:

```
0x05600070  0xFFE00000     Y     <- NOT DRAM: an IOVA
0x05600084  0xFFEE1000     C     <- NOT DRAM: an IOVA
0x05600098  0x4D941000     VideoInfo  <- real physical, decoder@4d941000
0x0560009c  0x4D941000     (slots 1-3 identical)
```

## The hypothesis was wrong

**`0x05600098` holds a genuine physical address.** `0x4D941000` is inside the
`decoder@4d941000` reserved region from the device tree — exactly where a
descriptor the MIPS must dereference should live. It is not an IOVA, so the
proposed "we hand the firmware an IOVA and it dereferences it as physical" does
not happen for this pointer, and cannot be the cause of the live-core lock.

Worth being precise about what *is* an IOVA: the **Y and C** addresses at
`0x05600070`/`0x05600084` read `0xFFE00000`/`0xFFEE1000`, far outside this
board's DRAM (`0x40000000`–`0x7fffffff`). Those are consumed by the AFBD fetch
engine, not by the firmware — the firmware's access scan shows it never reads
either register. So they are a separate concern from the handover.

## What the descriptor actually contains

144 bytes at `0x4D941000`, the exact span the firmware copies:

| offset | value | reading |
| --- | --- | --- |
| `+0x00` | `0x61770000` | fixed header/magic word (bytes `00 00 77 61`) |
| `+0x04` | `2` | |
| `+0x08` / `+0x0c` | `0x500` / `0x2D0` | **1280 x 720** |
| `+0x10` / `+0x14` | `0x500` / `0x2D0` | 1280 x 720 again |
| `+0x1c` / `+0x24` | `0x2D0` / `0x500` | 720, 1280 |
| `+0x34` / `+0x38` | `0x7530` | **30000** — frame rate x1000 |
| `+0x4c` / `+0x54` | `0xFFFF0000` | |
| `+0x58` | `0x500` | stride 1280 |
| `+0x64` | `0x4D941090` | **physical pointer, +0x90 into the same page** |
| `+0x68` | `0x4D9410AC` | **physical pointer, +0xAC** |
| `+0x70` / `+0x78` | `0x5000` / `0x2D00` | 1280<<4, 720<<4 — the 1/16-px form |
| `+0x80` / `+0x88` | `0x5000` / `0x2D00` | again |

Two things stand out. The sub-pointers at `+0x64`/`+0x68` land at exactly
`+0x90` and `+0xAC` — **immediately past the 144 bytes the firmware copies** —
so the header is copied and the tail is followed by pointer. And the geometry
appears in both plain pixels and the 1/16-pixel fixed point the window layer
uses (`0x5000` = 1280<<4), which independently corroborates that encoding.

**No Y or C address appears anywhere in the descriptor.** Frame addresses reach
the hardware only through the AFBD registers.

## So the live-core lock is still unexplained

What differs between the two live-core tests is now narrower rather than solved:

| | dma-buf import | VideoInfo written | Y/C written | source geometry + commit | result |
| --- | --- | --- | --- | --- | --- |
| `decd-client blue` | no | no | no | no | safe |
| `decd-client show` | yes | yes | yes | **yes** | locked |

The remaining candidate, and it is now the simple one: **both processors
read-modify-write the same source-geometry registers.** The firmware's
`NRWinNode` slot 4 writes `0x05600010`, `0x14`, `0x20`–`0x54` and commits; our
DECD path writes the same block for every submit. `blue` touches none of it.
That is ordinary two-master contention on one register file, not an address
translation problem.

Not established — but unlike the IOVA story it is consistent with every
observation, and it predicts that a submit which programs *only* Y/C and the
commit, leaving geometry to the firmware, would survive. That is testable and
is the obvious next experiment.
