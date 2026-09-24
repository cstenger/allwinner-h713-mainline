# The 2-hour soak fails after ~35 minutes: cedrus collides with the display's identity-mapped scanout

**2026-09-23.** First long soak run after the display-scaling retirement and
patch 0125. It did **not** pass. Failure is progressive, ends near-total, and
the cause is an IOVA address-space collision — not memory exhaustion, not a
decode-correctness bug, and not (on current evidence) anything the retirement
changed.

**CONFIRMED FIXED the same night** by patches 0126 + 0127 — a full clean 7200 s
soak, 5934/5934 iterations, 0 failures, 0 IOVA collisions. Details at the end.

Artifacts in this directory: `soak.log` (the failing run),
`dmesg-iova-failure.txt`, and `soak-after-fix.log` (the passing run).

## What happened

| soak time | state |
| --- | --- |
| t=0 → t=2041s | 1683 iterations, **0 failures** |
| t=2119s | first failure, `v05-1920x1080-high` only |
| t=2119 → 2199s | only v05, once per 17-iteration rotation |
| t=2205s onward | spreads to 720p, then to every vector including `m01-352x288` |
| t=2281s (stopped) | **iter=1879 pass=1837 fail=42**, ~40% failing and climbing |

94 `SOAK-FAIL` lines total. Every one is an md5 MISMATCH, but the mismatch is a
*symptom*: the decode is truncated because buffer allocation failed partway
(`ve+47`, `ve+33`, `ve+37` against an expected 60 frames). No frame was ever
decoded to wrong pixels.

I stopped the run at t=2281s rather than letting it reach 7200s. The verdict
was already determined, and the failure was flooding the kernel ring buffer —
which had **already wrapped**, destroying the earliest collision messages.

## It is not memory

This was the obvious first hypothesis and it is wrong:

- `MemAvailable` **oscillates, with no trend** — 867 MB at baseline, between
  792 and 840 MB for the whole run, and 827 MB *after* failures began. No leak.
- `CmaFree` is **perfectly constant** at 127924 kB from first sample to last.
- `/proc/buddyinfo` at failure time: 61 free order-10 blocks, 49 order-9,
  99 order-8. The allocator is not fragmented.
- No `page allocation failure`, no OOM, nothing in dmesg from the mm layer.
- No process leak: 1 ffmpeg, 0 zombies, 1 open handle on `/dev/video0`,
  115 processes, 860 open files.

## What it actually is

```
sun50i-iommu 2010000.iommu: iova 0x000000006c800000 already mapped to
    0x000000006c800000 cannot remap to 0x0000000040e21000 prot: 0x3
cedrus 1c0e000.video-codec: dma alloc of size 3133440 failed
```

606 collision messages. Every colliding IOVA — `0x6c400000`, `0x6c600000`,
`0x6c800000`, `0x6c880000`, `0x6c8c0000` — falls inside **one** range:

```
/sys/kernel/iommu_groups/0/reserved_regions
0x000000006c100000 0x000000006c8fffff direct
```

That is `uboot-scanout@6c100000` (8 MiB), the framebuffer the afbd driver
adopts from U-Boot, identity-mapped into the IOMMU so the display can scan it.
`already mapped to <the same address>` is the signature of an identity map.

**Cedrus and the display share IOMMU group 0** — one address space:

```
0 -> 1c0e000.video-codec
0 -> 5600000.display
```

So cedrus's DMA allocator walks up the IOVA space for ~35 minutes, eventually
reaches 0x6c1–0x6c8, and from then on every allocation that lands there is
refused. The largest buffer (1080p) hits it first because it needs the widest
contiguous IOVA range; as the allocator keeps returning to that neighbourhood,
smaller ones fail too. It never recovers, because the identity map is permanent.

## The fix — patches 0126 and 0127

**0126** adds a second reserved-memory node with **no `reg`**, naming the VE:

```dts
ve_scanout_iova: iova-reserve-scanout {
	iommu-addresses = <&ve 0x6c100000 0x800000>;
};
```

and lists it in the VE's `memory-region`. Reusing the existing node would not
work: it *has* a `reg`, so `iommu_resv_region_get_type()` returns
`IOMMU_RESV_DIRECT` for the VE too and the direct-mapping pass would try to
identity-map an already-mapped range. Without a `reg` the type is
`IOMMU_RESV_RESERVED` — the IOVA is withheld from the allocator and nothing is
mapped, which is what the VE needs. Verified in source:
`iommu_create_device_direct_mappings()` skips anything that is not `DIRECT`,
and `__reserved_mem_reserve_reg()` returns `-ENOENT` *silently* for a reg-less
node, so it costs no memory and warns about nothing.

**0127 exists because 0126 alone broke the probe outright:**

```
cedrus 1c0e000.video-codec: Failed to reserve memory
cedrus 1c0e000.video-codec: probe with driver cedrus failed with error -22
```

`cedrus_hw_probe()` calls `of_reserved_mem_device_init()` — index 0 of
`memory-region` — and a reg-less node has no `reserved_mem`, so the lookup
returns `-EINVAL`. cedrus tolerates `-ENODEV` but not that. All three gates went
to **0/5, 0/7, 0/6**: no `/dev/video0` at all.

0127 switches cedrus to `of_reserved_mem_device_init_by_name(..., "pool")`.
With no `memory-region-names` the match returns a negative index,
`__of_parse_phandle_with_args()` rejects it (`if (index < 0) return -EINVAL`),
and the result is `-ENODEV` — the same answer cedrus got when it had no
`memory-region` at all. **This is the same fix patch 0080 already applied to
the display driver, for the same reason**; the pattern and its rationale were
in the tree and should have been reached for the moment an entry was added to
a `memory-region` that a driver reads by index.

> **Two traps, both worth carrying.**
>
> 1. **`memory-region` is not only a list of buffer pools.** An entry can exist
>    purely to describe an IOVA reservation. Any driver that assumes index 0 is
>    its pool will break when one is added.
> 2. **cedrus is a MODULE (`CONFIG_VIDEO_SUNXI_CEDRUS=m`); the display driver
>    is built in.** Flashing a FIT delivers the Image and the DTB — *not* the
>    module. Flashing 0127 and cold-booting reproduced the failure exactly,
>    because the board came up with the **new DT and the old module**, which is
>    precisely the broken combination. `tools/install-kernel-module.sh` exists
>    for this, and its header already records the same mistake being made
>    before.

## Why the reservation did not protect cedrus — leading explanation

The driver already knows this hazard. `sun50i-h713-afbd.c:618`:

> By NAME, not index 0. The device must also list the adopted-scanout carveout
> in memory-region so `of_iommu_get_resv_regions()` can find its
> iommu-addresses and identity-map it

And the DT does carry it:

```
uboot-scanout@6c100000
  reg              = 0x6c100000  0x00800000
  iommu-addresses  = <phandle 0x03>  0x6c100000  0x00800000
```

Phandle `0x03` is `display@5600000`. **There is exactly one entry, and it names
the display only.**

`reserved_regions` is a *group*-level file, so it aggregates across the group
and shows the region — which makes the configuration look correct. But the IOVA
allocator is reserved per **device**, in `iova_reserve_iommu_regions()` at DMA
domain init, from `iommu_get_resv_regions(dev)` for that device. Cedrus's own
node claims no such region, so when cedrus's DMA domain came up it never
excluded 0x6c100000–0x6c8fffff from its allocator.

The boot order is consistent with this: cedrus joins group 0 **first**.

```
[1.175597] platform 1c0e000.video-codec: Adding to iommu group 0
[1.181833] platform 5600000.display: Adding to iommu group 0
```

**CONFIRMED** — this was written as a hypothesis and has since been verified
both in source and on hardware.

In `iommu_dma_init_domain()` the reservation runs for exactly **one** device
per domain, the first to initialise it. Every later device returns early and
never contributes its regions at all:

```c
/* start_pfn is always nonzero for an already-initialised domain */
if (iovad->start_pfn) {
	...
	return 0;          /* skips iova_reserve_iommu_regions() */
}
```

And `of_iommu_get_resv_regions()` only produces a region when the device lists
the node in its **own** `memory-region` *and* the node's `iommu-addresses`
names that device's phandle (`if (np == dev->of_node)`). The VE satisfied
neither, and the VE is configured first, so the range was never reserved for
the only allocator that mattered.

The predicted falsifier was run and came back positive: with the region
declared for the VE, the collision does not occur in a full 7200 s soak.

## Is this a regression from today's work?

**Not established either way, and it should not be assumed.** What can be said:

- The retirement is display-register-only. It removed the proc block mapping
  and one source rectangle; it touches no DMA buffer, no IOMMU configuration,
  and the soak involves **no display at all** by design.
- Patch 0125 changes capture pitch alignment, which changes buffer *sizes* and
  therefore IOVA allocation patterns — it could plausibly change *when* the
  allocator reaches 0x6c1, but not whether the hazard exists. Note 1920 is
  already a multiple of 32, so `v05` — the first vector to fail — has the same
  buffer size before and after 0125.
- The hazard is structural: a shared IOMMU group, an identity-mapped 8 MiB
  region, and a reservation attached to only one of the two devices. Nothing
  about that is new today.

**The test that would settle it** is to run the same soak on the previous
kernel (`build/out/h713-kernel-fits/replaced-20260923-193425.fit`, backed up on
the board). Until that runs, "pre-existing" is the likely answer, not a
established one.

## What this does not change

The retirement's own hardware validation stands. It was signed off on the
panel — 1080p H.264, HEVC, Main10 and 720p all operator-confirmed, with the
video plane holding a changing NV12 1280x720 framebuffer — and all three
headless gates passed clean (5/5, 14/14, 6/6) before this soak started. The
gates are short; they never reach the collision.

**What this does mean is that no long decode run on this board is currently
trustworthy past ~35 minutes**, and that any prior "clean 2-hour soak" claim
should be re-checked against whether it ran with the display driver bound and
the scanout region identity-mapped.

## Confirmed on hardware — the full soak passes

Cold boot on the 88-patch series with 0126 and 0127 installed (and the cedrus
**module** installed, not just the FIT). cedrus probed at t=6.47 s with no
reserve failure; gates were green first (5/5, 14/14, 6/6).

```
SOAK-DECODE DONE t=7200s
  iterations   5934  (5934 pass, 0 fail, 0 software fallbacks)
  frames on VE 210472
  timeouts     +0  (was 0 at start)
  oops/BUG     0 -> 0
  CmaFree      130176kB -> 130176kB   (delta 0kB, both after reclaim)
  MemAvailable 870024kB -> 854656kB   (delta -15368kB)
```

`already mapped`: **0**. `dma alloc ... failed`: **0**. `SOAK-FAIL`: **0**.

Against the failing run, measured at the same points:

| | before | after |
| --- | --- | --- |
| first failure | t=2119s, iter=1747 | none in 5934 iterations |
| at t≈2281s | pass=1837 **fail=42** | pass=1881 **fail=0** |
| IOVA collisions | 606 | **0** |
| total SOAK-FAIL | 94 and climbing | **0** |
| `v05` 1080p | first to die | 2874 ms at t=7092s vs 2867 ms first iteration |

`0 software fallbacks` matters: every one of the 210472 frames was decoded on
the VE, so this is not a pass bought by quietly dropping to software.

**One number worth keeping an eye on, not a failure:** MemAvailable ended
15368 kB below where it started. The harness does not treat that as a fault and
CmaFree returned exactly to its starting value, so this is most likely slab and
page-cache growth over 5934 process launches rather than a driver leak. It is
recorded here so that if a future soak reports a *larger* delta there is a
baseline to compare against.
