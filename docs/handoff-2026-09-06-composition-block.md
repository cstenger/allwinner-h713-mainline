# Handoff — 2026-09-06: the fetcher was never the problem

> Follow-up: [September 8 Claude handoff](handoff-2026-09-08-mips-callback-trace.md) records later experiments, corrected interpretations, recovery state, and next steps.

One session, four operator looks, three of them wasted. It ends with the
corruption's cause identified by a free register read, a ready-to-run fix on
the board, and a clear recommendation not to run that fix but the better one
behind it.

**No power cycles.** The board ran the whole session on the boot it started on.

## The result

Our AFBD source block is **byte-identical** to the 2026-08-31 capture that put
full-colour NV12 on the panel:

```
0x05600020 0x02cf04ff    0x05600030 0x02d00500    0x05600040 0x00000500
0x0560004c 0x01680500    0x05600060 0x00000001    0x05600070 0x6c500000
```

...and the picture is still green noise. The difference is one stage
downstream. **All seventeen composition registers at `0x05000000` are at the
852x480 values**, including the scaler ratio:

```
0x05000174 = 0x002B002B     43/64, configured for an 852-wide source
0x05000224 = 0x01E00354     852 x 480
0x05000844 = 0x03540030     pitch 852
```

while AFBD fetches 1280x720 at stride 1280. **Composition drives the panel**,
so the two stages disagree about the frame and the one that wins is the one we
were not looking at.

This also explains an invariance visible in every photograph of test_76 and
test_77 and never accounted for: changing AFBD geometry never moved the
displayed footprint, because AFBD geometry does not size the output.

### How it got that way

`frame-composition-block-capture-2026-08-31.txt` records it: the
**source-coordinate** client (`/root/decd-client`) drives the whole composition
block to 852x480, and only a corrected-client (`decd-client.coord1080`) frame
that the firmware **services** reverses it.

The firmware has serviced none. The driver's ring writer is frozen at
`ring_writes_done == ring_writes_max` — the DECD-lock workaround from the
2026-09-04 handoff. So a submit stages a frame and programs nothing downstream.

**The lock workaround and the corruption are the same knot.** `ring_writes_max=1`
is what stops the 60 Hz ring rewrite from hard-locking the SoC with the MIPS
alive, and it is also what prevents the firmware from ever reprogramming
composition. This is the second time today the two turned out to be linked (see
the ring slots below).

## What was measured, all free

| finding | evidence |
| --- | --- |
| the frame really is where we say | phys `0x6c500000` reads `0x4B4B494A 0x4E4C4B4B 0x5251514F` — byte-exact against the file |
| chroma is present and non-zero | `0x6c5e1000` = `0xA2D9A6DC 0xA5D8A1DD` |
| three of four ring slots were dead | Y slots 1-3 held `0xFFC00000`, not DRAM under bypass |
| ...but that was not the cause | filling all four changed nothing |
| the submit rewrites no geometry | state before == state after, byte for byte |
| pixel format 0 is correct | stock playback capture also has `0x05600010 = 0x03000013` |
| stock geometry == our geometry | `0x02CF04FF`, `0x02D00500`, strides `0x500`, all identical |
| composition registers are writable | 17 written, 17 stuck, 0 reverted |

### Hypotheses killed today

- **Stride shear.** `0x05600040/44` were 852 against a 1280-stride frame — a real
  incoherence, quantitatively exactly a diagonal shear. Fixed it; no change.
- **Incoherent seven-word geometry.** `apply_visible_route` writes four of the
  seven source-geometry words; `0x30`, `0x48`, `0x4c` keep inherited 852x480
  values. Real bug, still worth fixing, not the cause.
- **IOMMU / addressing.** Physical addressing under bypass works; the frame is
  byte-exact at the programmed address. Not the cause.
- **Pixel format.** Refuted by the stock capture before it cost a look.
- **DRAM-relative addressing.** Stock's `0x05600070 = 0x00400000` looked like
  `physical - 0x40000000`, but our own known-good capture has the full
  `0x6c500000`. Refuted before it cost a look.
- **VideoInfo descriptor as the address source.** Refuted by
  `videoinfo-descriptor-decoded-2026-09-04.md`: "No Y or C address appears
  anywhere in the descriptor."
- **AFBD writeback as a byte-exact oracle.** The enable sequence was recovered
  from `__afbd_wb_en` (`0x121` to `0x056001C0`, commit through `0x05600014`) and
  it works, but it arms a *statistics* writeback — ten 16-bit values, not
  pixels. Not a frame-capture path.

## Corrections to the record

- **"The firmware rewrites the geometry registers on submit and rewrites them
  wrong"** — the premise `geom-restore-test.sh` was built on. Measured false for
  `decd-client.coord1080`: the block is byte-identical before and after a
  submit. The 852x480 is inherited state nothing overwrites.
- **`apply_visible_route` is incomplete**, and `7f5146a`'s seven-word fix was
  applied by hand and never landed in the script. Still unfixed.
- **`0x05600030`/`0x48`/`0x4c` are never written by any tool in the tree.**

## What is on the board

`/root/decd-composition-fix.sh` — sets AFBD to the known-good 2026-08-31 state
with all four ring slots, then writes all seventeen composition registers to
their 1280x720 values. Snapshots and restores everything, including on error and
SIGINT. Untested visually.

Also deployed and used this session: `decd-geom-measure.sh`,
`decd-stride-ab.sh`, `decd-ring-fill.sh`, `decd-block-capture.sh`,
`decd-physaddr-test.sh`.

## Recommended next step — and it is not the fix script

Writing composition by hand treats the symptom. The vendor path is that the
**firmware** programs that block when it services a frame, and the only reason
it never does is our frozen ring writer.

So: **raise `ring_writes_max` and let a `decd-client.coord1080` frame be
serviced**, then read the seventeen registers. If they flip to 1280x720 on
their own, the whole thing was the lock workaround and the real fix belongs in
the driver — teach it to write the ring once per frame rather than at 60 Hz,
which is what the firmware expects anyway.

**Hazard:** the 60 Hz ring rewrite is what hard-locks the SoC with the MIPS
alive. Raise it by a small increment (4, not unbounded), on a fresh boot, with
`/dev/kmsg` narration so a lock leaves a trace. This deserves its own session.

Fallback if that locks: run `decd-composition-fix.sh` and take the picture.

## Board state at handoff

Core alive (`0x0306101c = 1`), IOMMU master 2 in bypass (`0x02010030 = 0x7C`),
logo path restored (`0x051c006c = 0x29000000`), composition block back at its
inherited 852x480 values, AFBD geometry restored, `sunxi_decd` loaded with
`ring_writes_max = 40, ring_writes_done = 40`. Uptime unbroken since the session
began. `display_cfg.xml` on the FAT still has elog enabled — **leave it**.

## Method note

Every one of the three wasted looks was spent on a hypothesis that a register
read could have ranked for free beforehand, and the read that finally explained
the invariance was one command against a document already in the repo. The
08-31 known-good capture should have been the first thing consulted, not the
last.

The 2026-09-01 lesson was recorded as "do the cheap byte-level measurement
FIRST." It was not applied. Restating it, sharper:

> **Before asking the operator to look, diff the live state against the last
> capture that is known to have worked.** If no such capture exists, take one.
