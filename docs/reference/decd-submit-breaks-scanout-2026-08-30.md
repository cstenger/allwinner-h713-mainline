# A DECD submit breaks the display path for the rest of the boot

Found while checking what the panel showed during the format test. It is the
more consequential result of that session, because it changes how a large body
of earlier "still black" observations should be read.

## The bisection

The marker matters as much as the method. `h713_disp init 0x34` publishes no
logo, so the scanout buffer at `0x6c100000` keeps whatever was in DRAM. Earlier
in the session `mem-fill` had written red over the top third of it, leaving
white below — a distinctive, unambiguous image that survives a warm reboot. So
"is the display path working" became a question with a yes/no answer rather than
a judgement call about shades of black.

| step | panel | DECD irqs |
| --- | --- | --- |
| U-Boot prompt, `init 0x34`, MIPS alive | **white with red top third** | — |
| + booted the DECD-exclusive kernel, ran nothing | **white with red top third** | 0 |
| + `decd-client pm on` alone | **white with red top third** | 0 |
| + one frame submit | **black** | 40 |

After the submit the panel stays black, and it is not simple occlusion by the
video source:

- source 0's enable bits cleared to 0 with the commit latch pulsed (latch
  written 1, reads back 0, so it was consumed) — still black
- the OSD channel left enabled the whole time, `0x05600140 = 0x03001901`,
  source `0x05600178 = 0x6C100000`
- its buffer still holding the red band and white, verified by reading DRAM
- the OSD's own commit latch pulsed and consumed — still black
- LVDS scan counter advancing throughout, TCON totals `0x02F80550` unchanged
- no IOMMU faults in dmesg, and master 2 is bypassed (`0x02010030 = 0x7C`)
  anyway, so this is **not** the known "one fault wedges the fetch engine"
  failure

So the composition output dies at the submit and does not come back, while every
register that describes it still reads healthy.

## Why this matters more than it first looks

The standing model was that DECD submits work, the firmware configures source 0
correctly, and source 0's output never reaches composition — the panel stays
black. The evidence for "never reaches composition" was a series of null results
measured **after** a submit: hiding the OSD gave black, the internal blue
generator gave black, source-0 enable values 1/2/3 gave black, mixer layer
values gave black.

If a submit kills the output path, those nulls were measuring a dead path. They
do not distinguish "source 0's output is not routed" from "nothing at all can
reach the panel any more". That is the same unfalsifiability trap this project
has hit before, and it is why the 2026-08-30 `mem-fill` scanout-liveness check
was introduced — but that check was run at the **U-Boot prompt**, before any
submit, so it certified a state that the submit then destroyed.

**This does not refute the earlier conclusions. It removes their support.** They
need re-testing with the panel verified live immediately before each
observation, not once at the start of the boot.

## What is not yet known

- **Which half of the submit does it.** `decd-client show` calls `dec_enable()`
  and `DECD_IOC_FRAME_SUBMIT` together; only `PM_HINT` was isolated and cleared.
- **The mechanism.** One hypothesis, untested: the firmware rewrites the
  geometry registers on submit, and it rewrites them wrong. After a submit
  `0x05600030` and `0x0560004c` read `0x0354` = 852 in the low half and 480/240
  in the high half — 852x480 on a 1280x720 panel — while `0x05600020` correctly
  reads 1280x720 minus one and the stride is 1280. Stock's playback capture has
  `0x0560004c = 0x02D00500`. If that geometry is what composition uses, it would
  break output for every layer, which fits the symptom and explains why clearing
  source 0's enable did not restore the OSD.
  The test is to restore `0x05600020`/`30`/`40`/`44`/`48`/`4c` to their
  pre-submit values after a submit and see whether the OSD returns. The attempt
  hard-locked the SoC before the post-submit geometry could even be read.

Healthy values, captured immediately before a submit, for that test:

    0x05600010  0x03000010      0x05600040  0x00000780
    0x05600020  0x043F077F      0x05600044  0x00000780
    0x05600024  0x00420077      0x05600048  0x02D00500
    0x05600030  0x02D00500      0x0560004c  0x01680500

## Operational

Two hard locks in five submits today, both inside the submit itself, both
needing a physical power cycle. The 500 ms dwell did not prevent them; the
earlier belief that a shorter hold would help is not supported. Budget a power
cycle per submit and get the observation out to disk before the next one.
