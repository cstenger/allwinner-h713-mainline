# How the ARM tells the MIPS about a frame — and why our submit kills it

Static RE, no board time. This replaces the guess in
[decd-with-live-mips-2026-09-04.md](decd-with-live-mips-2026-09-04.md) that stock
pairs each `/dev/decd` submit with a CPU_COMM notification.

## There is no CPU_COMM frame notification. The whole surface is now known.

The elog's registration records give the **complete** CPU_COMM routine table
straight from the firmware — 82 routines with names, entry addresses and
FuncIDs, in [wce-elog-decd-blue-2026-09-04.txt](wce-elog-decd-blue-2026-09-04.txt).
That is better evidence than the hash-matching the call table was built from.

Nothing in it is a per-frame notification. There is no `Present`, no `Flip`, no
`QueueBuffer`, no `SubmitFrame`. The only frame-shaped entries are
`THal_Vp_SetImageBufferAddr_1_000` (`0x8B10ADA8`, FuncID `396f16bf`) and
`THal_Vp_GetImageBufferAddr_1_000` (`0x8B10ADB0`, FuncID `2f02f7dd`) — both
long-verified stubs (`jr ra; nop`), now confirmed registered but empty.

**So the handover is not an RPC.** It is a register.

## `0x05600098` is a pointer to a 144-byte descriptor, dereferenced by the MIPS

From `0x8b147860`:

```
v0 = readl(0x05600098)                    ; ARM writes this
if (v0 == 0) skip
if (v0 <  0x40000000) skip                ; must look like DRAM
v0 = (v0 & 0x0fffffff) | 0xa0000000       ; -> MIPS kseg1, UNCACHED
copy 0x90 bytes (144) from v0 into a local buffer   ; 4 words per iteration
```

The ARM writes a **physical address** into `0x05600098`; the firmware converts it
to an uncached MIPS address and copies 144 bytes out of it. That is the
VideoInfo descriptor handover, and it is the only path by which frame metadata
reaches the window layer.

Consistent with `decd.ko`'s map, where `dec_reg_set_address` writes
`0x05600094`–`0x0560009c` alongside the dirty latch, and with stock HWC
submitting a second dma-buf (the VideoInfo block) beside the pixels.

## What our driver publishes there — and why that is the bug

`patches/kernel/0078`:

```c
h->video_info = dmam_alloc_coherent(dev, PAGE_SIZE, &h->video_info_dma, ...);
...
writel(lower_32_bits(h->video_info_dma), h->regs + AFBD_VIDEO_INFO0 + i * 4);
```

`AFBD_VIDEO_INFO0` is `0x098`. So we publish `video_info_dma` — and once the
display device is attached to the IOMMU (patches 0076/0080), **that is an IOVA,
not a physical address.**

The MIPS is not behind that IOMMU. It takes the value as physical and
dereferences it. So with a live core we hand the firmware a pointer that means
something only to the IOMMU, and it reads 144 bytes from wherever that number
lands in real DRAM.

**This is the first mechanism proposed for the frame-submit lock that explains
the whole pattern:**

- MIPS parked: nobody dereferences the pointer, so the same submit is harmless —
  which is every successful DECD test we have ever run.
- MIPS alive, `decd-client blue`: no descriptor pointer is involved, and it did
  not lock.
- MIPS alive, real frame: the pointer is dereferenced, and it locked.

## What is established and what is not

**Established:** the firmware reads `0x05600098` as a physical pointer and copies
144 bytes from it; our driver writes a DMA address there that is an IOVA when the
IOMMU is attached; the MIPS does not share that translation.

**Not established:** that this is *the* cause of the lock. Reading the wrong DRAM
would give the firmware a garbage descriptor rather than a bus fault, so the lock
could equally come from what it does with garbage geometry afterwards. The
observed IOVAs are around `0xffc85000`, which after the firmware's
`& 0x0fffffff | 0xa0000000` becomes kseg1 `0xafc85000` — real DRAM, not an
unmapped address. So "wild pointer hangs the bus" is *not* the obvious reading;
"firmware acts on nonsense" is at least as likely.

## The experiment this suggests

Publish a **physical** address in `0x05600098` when the MIPS is alive: allocate
the VideoInfo page from the contiguous carveout rather than the IOMMU-attached
device, or write its physical address explicitly. Patch 0074's contiguous pool
was dropped from `series` and is the obvious donor.

Cheap pre-check with no risk, and worth doing first: on a MIPS-parked boot,
submit one frame and read back `0x05600098`, then compare against
`/proc/self/pagemap`-style ground truth for the VideoInfo page. If the register
holds something that is not the page's physical address, the diagnosis is
confirmed before any live-core attempt.

## A tool caveat found while doing this

The `lui`-tracking scanner in this session mis-attributed several accesses:
after `lw $v0, 0x38($v0)` the base register is **reloaded from memory**, so the
following `lw $a3, ($v0)` is not MMIO at all, but the scanner kept the stale base
and reported hits at `0x05600060`/`0x64`/`0x6c`. Any address-tracking pass over
this firmware must invalidate a register when it becomes the destination of a
load. The counts in earlier sections of this session's notes are safe because
they were used only to compare *which blocks* a function touches.
