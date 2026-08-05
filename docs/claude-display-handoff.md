# H713 display handoff

Last updated 2026-08-04. Operational companion to `docs/mips-display-recovery.md`
(detailed evidence log) and `docs/board-bringup-sequence.md` (boot chain and
state machines).

## Executive state

**The panel works.** It renders a correct red/blue checkerboard, correct solid
primaries, and correct colour bands, all through the ordinary panel init with no
per-test hardware manipulation.

The entire display fault was **one register**: the display PLL at `0x058c0014`.
The vendor table leaves N+1 = 43 (1032 MHz, DCLK 73.71 MHz); the panel needs
N+1 = 36 (864 MHz, DCLK 61.71 MHz against the 62.00 MHz `panel_config.ini` asks
for, 0.46% low, 59.71 Hz). At 43 every pattern arrives carrying colour but no
spatial information at all. Carried as
`h713_panel_cfg_board_b.pll_n_plus_1 = 36`, patched into the LogoRegData record
for `0x058c0014`, so it applies to every path that runs the display sequence.

**The framebuffer path is fixed** as of 2026-08-04, and it was **one register**,
not the two this page spent a day describing:

> `0x0528008c`, the layer's pixel X origin, came up holding **123**. Written to
> **0**, content starts at column 0, fills all 1280, and renders with **zero
> shear**: `fb-fix`'s stock-stride step is one dead-vertical red/blue edge
> drifting 0.0 px per row.

**The root cause was an omission in our own patch table.** `h713_disp_panel_patch`
transcribes stock's panel-patch sites, and left two out on the grounds that
stock's literal zero at `0x05280084[31:16]` and `0x0528008c[15:0]` "may be a
decode artefact rather than a real store; writing a zero we cannot justify is
worse than leaving the vendor default in place." The vendor default is another
panel's, and it is 123. The static analysis was right; the caution was wrong;
what it lacked was hardware.

Restored 2026-08-04 and confirmed (test_35): the record at blob `+0x3584` patches
`0000007b -> 00000000`, the count goes 21 -> 22, and `0x0528008c` reads
`00000000` in **both** dumps -- including after the DE replay, which used to
restore 123. Fixed at source, so no path can miss it.

`0x05280084[31:16]` is still omitted on the same reasoning and is now *more*
suspicious, not less. It holds 720 and stock appears to zero it. It has earned
its own two-sided perturbation before anyone touches it.

Both symptoms came from it. The pale left band was the origin directly. The
stride deficit -- the source pointer advancing ~1238 words per row instead of
1280 -- was a *consequence* of it, and disappeared when it was zeroed.
`0x05600170` turns out to be a plain byte stride that was correct all along:
with the origin at 0, `fb-fix` measures **`S = V`** across 1300..1340.

**This is worth reading as a method failure, not just a fix.** The stride was
measured twice, by unrelated experiments, and both agreed on 1237-1238. Neither
was wrong about what it measured -- `S` really was 1238 while the origin was 123
-- and both were wrong about what it *meant*, because a number measured
downstream of a fault got modelled as a fault of its own. That is exactly what
the old log did when it read the pale band as a stride. The same mistake, one
level up, made by the page correcting it.

Applied as a write after the DE replay, for every mode except `fb-band`. Whatever
sets 123 does so before that point and survives the replay, so it is LogoRegData
or the firmware, and a patched record would not be the last word.

**Confirmed on real content, 2026-08-04.** The stock vendor asset renders as
legible red "SMART PROJECTOR" text on a blue field. Legible means unsheared, so
the framebuffer path is correct end to end on the actual file, not just on
synthetic patterns.

It was `vendor-logo-late`, which settles the bisection: **the logo must be
loaded after the display sequence, not before it.** That is now the default for
every vendor-logo variant.

Loading before is why `vendor-logo` never showed anything across five runs.
Every `fb-*` mode seeds with a plain memory write and renders; `vendor-logo`
instead selected a block device, read 2.7 MB off FAT to `0x6d000000` and hashed
it, all between `h713_disp_load()` and `h713_disp_run()`. The panel stayed dark
with every register dump byte-identical to a working run, `fbcheck` proving the
framebuffer correct, and the TCON marker equally absent. Moving that work after
init -- changing nothing else -- renders it.

**The mechanism is not established, and the obvious guess is wrong.**
`h713_disp_load()` reads the same filesystem in every mode, so FAT access before
the sequence is not the problem by itself. What is new is the extra read plus a
SHA-256 over it: seconds of work, and a lot of cache traffic, in a window where
nothing else does any. `vendor-logo-early` reproduces the broken ordering for
whoever wants to chase it.

Consequences, for anyone reading older notes: horizontal variation in a
framebuffer image used to become vertical stripes and the bootlogo arrived as a
sheared streak. The TCON pattern generator bypasses this path entirely, which is
why its output was always perfect.

## What is proven, and how

| fact | evidence |
| --- | --- |
| display PLL is `0x058c0014` | `clkfind 0`: N+1 43->42 moved the clock witness -2.28% against -2.326% predicted |
| the PLL runs at 24 MHz x (N+1) | same, plus the counter tracking N to 0.1% across a six-step sweep |
| DCLK = PLL/14 | the panel decodes at 864 MHz and 864/14 = 61.71 vs the 62.00 requested |
| the free-running counter is PLL/56 | 18432 kHz measured against 18428.6 computed |
| the framebuffer conversion is correct | `fbcheck` reads the framebuffer back: bootlogo content in rows 343..378, columns 368..912, exactly matching the file |
| the stride was 1237-1238 px/row **while the origin was 123** | test_30: five `fb-edge` steps give 34.1/31.9/29.9/25.3/22.9 stripes; `S mod P` from five pitches leaves one candidate in 2..4000. test_31 gets 1238 from the register fit, sharing no assumption with it. Both correct, and both were about a symptom |
| `S = V`, once the origin is 0 | test_33: registers 1300..1340 give S = 1300.1/1309.8/1319.4/1329.1/1338.7, and the stock 0x1400 renders a vertical edge |
| the framebuffer path is correct | test_33: red/blue boundary drifts **0.0 display px per row** at the stock stride, full width, no band |
| `0x05600170` controls the stride | test_31: counts track the register 2.96/5.24/7.58/10.01 against 2.3/4.7/7.0/9.3 predicted, and the below-default step leans the other way |
| `0x0528008c` is the layer X origin | test_32: 123 -> band 119.4, **0 -> 0.0**, 400 -> 406.2. Four other candidates screened in the same run moved it by 1 px |
| the band was never framebuffer content | test_32 step 1: it stays pale against a saturated red fill, so a geometry fault, not addressing |
| the logo must load **after** the display sequence | five blank runs with the pre-run load; moving it after init, changing nothing else, renders legible text (test_34) |
| stride and width are different numbers | test_31 sweeps the stride 1230..1254 and the band holds at 1158 +- 4; test_30 sweeps the pattern and it holds at 1152 +- 2. Neither knob touches it |
| the real vendor asset renders correctly | test_34: legible red "SMART PROJECTOR" on blue -- a sheared frame smears those glyphs into diagonals |
| the band was at the **head** of the line, not the tail | ~120 px blank on the left, content running to the right edge, in all eleven photographs before the fix |
| the photographs are not mirrored | the stripe lean matches the model in absolute sign across five steps of test_31, including the flip at the one step below default; so left is left |
| the band belongs to the framebuffer path | operator observation: TCON generator patterns fill the whole screen, framebuffer patterns are truncated |

## Ready to run

Artifact hashes move on every rebuild -- U-Boot embeds a build timestamp -- so
the commit is the source identity, not the hash. Rebuild with
`./build/build.sh uboot`.

**The banner names the last commit, not the code.** A build made with
uncommitted edits reports `g<previous-commit>-dirty`, so a log can truthfully
show an older hash while running newer behaviour -- test_35 did exactly that.
Trust `-dirty` and the behaviour, not the hash.

**The display bring-up is done.** Both deferred-load vendor modes render the
stock asset correctly:

```
h713_disp panel-test 0x33 vendor-logo-chroma
```

Expect one blink, then two, then a **red "SMART PROJECTOR" on blue** filling the
frame -- rows 343..378 of 720, columns 368..912 of 1280, so about 5% of the
height a third of the way up. `vendor-logo-late` is an alias and behaves
identically.

A brief wrong-looking frame before the logo is normal: the framebuffer is seeded
with `fill_pattern(0)` so that the pre-run FAT read can be avoided, and that seed
is on the panel from the end of init until the logo is published and committed.

**`vendor-logo` works too, and renders the real asset visibly** -- confirmed
2026-08-04. The stock `bootlogo.bmp` is 99% black with pure grey lit pixels
(chroma `|R-B|` exactly 0), and it shows up fine: a light-grey bar on black.

That corrects something this page asserted for most of a day. The repeated blank
results from `vendor-logo` were the **load ordering**, not the palette -- the
2.7 MB FAT read before the display sequence left the panel dark, and every one of
those failures predates the fix. "This path cannot show luminance content" was a
plausible reading of a null that had a different cause, and it was wrong.

The older rule it leaned on is narrower than it was stated. What the old log
established is that *full-field* black/white and greyscale tests read blank --
a uniformly grey screen against a uniformly white one is genuinely hard to
judge. Structured, high-contrast luminance content like a grey bar on black is
not that, and it is perfectly visible.

`vendor-logo-chroma` is still the better instrument when a result must survive a
photograph, since it keeps the same file, hash check, geometry and `fbcheck`
bounds and swaps only the palette -- lit to red, unlit to blue. Use it for
measurement. Use `vendor-logo` when the question is what the product actually
shows.

**Read `fbcheck` before you read the panel.** It runs against the framebuffer in
memory, so it says whether the frame is even worth photographing. Its first
outing caught a broken build the rest of the console cheerfully denied:
`content rows 720..0, columns 1280..0` are untouched initial bounds, meaning *no
pixel matched at all*.

**A dark panel is not evidence about the framebuffer.** Every mode emits a TCON
chroma marker, which reaches the panel without touching the framebuffer path. No
blinks means the panel is not lit and nothing downstream is being tested. Five
runs were spent before that control existed.

To re-measure the framebuffer path itself:

```
h713_disp panel-test 0x33 fb-fix
```

Six steps at registers 1300/1310/1320/1330/1340/**1280**, predicting
11.3/16.9/22.5/28.1/33.8 stripes and, at the stock 1280, **one vertical edge**.

`fb-edge`, `fb-edge-fine`, `fb-stride` and `fb-band` measured the faults and are
superseded by the fixes. `fb-band` alone still skips the origin correction, since
it needs the untouched value for its control step.

### Scoring any of these

**Count the diagonal red/blue stripes.** Row Y starts at source word `Y*S`, so
the boundary slides `S mod P` pixels per row and wraps every `P/|D|` rows. A
720-row frame shows `N = 720*|D|/P` stripes, so every step measures the stride
independently and they must all agree -- much stronger than picking out the
vertical one, and it survives a blurry photograph, since counting a few coarse
diagonals is easy.

Feed the photographs straight to the analyser rather than counting by hand:

```bash
tools/display/edge-measure.py --pitches 1232,1234,1236,1237,1238,1240 IMG_*.jpeg
```

It counts by FFT and by autocorrelation (two methods, because one has no way to
report that it locked onto moire), then searches every stride for the one that
fits all steps. Photographs must be in step order, and **any step that was not
photographed must be dropped from `--pitches` too** -- test_30 has five photos
for six steps and a silently wrong mapping shifts the answer by 4 px.

Do **not** read a multi-stripe step as a failed step, or as moire. It is the
measurement. (An earlier version of this page promised "one boundary per step",
which is true only within ~1.6 px of the answer, and would have made every step
but one look broken.)

Do **not** score any of this on the pale band. The band measures `W`, not the
stride, and cannot respond to the pattern at all; that criterion was wrong and
wasted a run.

## Open work, in value order

Session of 2026-08-04/05 closed the display path. What follows is everything
still outstanding, with the exact next step for each.

### 1. Animated framebuffer test signal

The last thing static frames cannot test. Every render so far is one frame held
still, so sustained commits, frame timing and liveness are all unverified.
`h713_disp_commit_osd_frame` hand-manages what stock does in an IRQ handler
(*"without an ARM IRQ handler the old completion otherwise remains pending
forever"*), and at most six chained commits have ever been exercised. Observed
commit waits span 600 us to 16400 us; the upper end is about one frame at
59.71 Hz, which *suggests* vsync-locked completion but does not establish it.

Build a moving chroma bar: reuse `fill_edge` with a per-frame offset, commit
continuously, encode the frame number in the bar position and print a committed
count so one photograph cross-checks against the console. Smooth motion means
sustained commits work; a stall after *k* frames localises where the handshake
breaks; tearing shows as a horizontal discontinuity.

Deliberately **not** decoded video -- keep DECD separate so a decoder fault
cannot present as a display fault. This becomes the reference for DECD later.

If sustained commits do break, the likely cause is the missing ARM IRQ handler,
which is real work rather than a tweak. Better found now than under a
compositor.

### 2. Teardown as the single exit

`h713_disp_teardown()` works and is verified, but `h713_disp_panel_test` still
bails with bare `return ret` in about a dozen places, each leaving the panel
powered and the MIPS live. Not hypothetical: that is exactly what happened when
`vendor-logo-late` hit its bootlogo hash refusal.

Convert to a single exit -- `goto out` onto teardown-and-return, or wrap the
body in a helper called by a thin outer function that always tears down.
Deferred during the session because a background task is refactoring that
function's 19-bool signature and restructuring the body would collide.

Check whether `h713_disp_init_only`, `h713_disp_test` and the mips-test path
want the same treatment; they have the same shape of early returns.

### 3. The backlight, and what it blocks

PWM2/PB4 provably does **not** dim this panel -- see the evidence log. The
configuration is right in every respect (channel 2, PB4 mux 2, 25 kHz, active
high, all matching the stock DTB) and the registers read back correct.

Next, and it needs no new code: the firmware HAL exposes
`Thal_Vp_SetBacklightLevel` (`0x51ad877e`) and `Thal_Vp_SetBacklightPwmInfo`
(`0xb46ce545`), CPU_COMM works, and `commcall` already passes parameters.

```
h713_disp panel-test 0x33
h713_disp commcall 51ad877e chan=0 pid=8b8f32b0 64
h713_disp commcall 51ad877e chan=0 pid=8b8f32b0 0
```

Temper expectations: `THal_Vp_EnableBlackScreen` returned cleanly and did
nothing, because the firmware's own CRTC is not enabled in our configuration.
The backlight may be in the same category.

**Do not drive PB5 low.** The DT calls it `panel_bl_en` and it is shared with
fan power. On a projector with an LED light engine that is a thermal risk.

This blocks finishing the teardown, which should turn the backlight off first
and currently cannot.

### 4. Linux handoff

Unblocked now that the reservations are correct. Nothing has checked that the
framebuffer survives into Linux. Milestone 2b passed *before* any of the
framebuffer fixes existed, and "reaches userspace" is not "the panel still
shows a correct image".

Check: after handoff, is the panel still showing the U-Boot frame intact, and
for how long? Does anything in Linux disturb the display clocks, the layer X
origin, or the AFBD source address?

### 5. `auto`, and a design call that is not mine

`auto` cannot render as it stands -- no framebuffer content **and**
`stock_panel_power = false`. It is a MIPS-launch/prep path, not a display path,
which looks deliberate and matches Milestone 2b.

So either it is correctly prep-only, and the real question is whether the fixes
hold with the MIPS live and unquiesced (largely answered -- plain
`panel-test 0x33` runs that way and renders), or the product wants a boot logo
and `auto` should publish it. That is a behaviour change to the documented boot
path and wants a decision.

### 6. Smaller, opportunistic

- **`0x05280084[31:16]`** -- the *other* site `h713_disp_panel_patch` omitted on
  the same reasoning that turned out to be wrong for `0x0528008c`. It holds 720
  and stock appears to zero it. It has earned the same two-sided perturbation,
  via the `fb-band` harness. Do not change it blind.
- **Why a pre-run FAT read kills the display.** We have a workaround, not a
  cause, and it is a latent fragility: anything occupying that window might do
  the same. `vendor-logo-early` reproduces it. Three runs should isolate it --
  a bare `mdelay()` of equivalent duration, then read-without-hash, then
  hash-without-read.
- **The firmware's UART shell.** `shell_thread_uart` and `shell_thread_monitor`
  are in the binary, and `display_cfg.xml` references *"How to use elog
  command.md"* -- a command interface, not just an output stream. Establish
  from the binary which UART it binds and whether the thread starts in our
  configuration before spending bench time.
- **Two pinctrl patches disagree.** Patch 0002 gives PB4 `pwm2` mux 2, patch
  0018 gives 3 for the same pin and function. Only 0002's driver binds here
  (`allwinner,sun50i-h713-pinctrl`), and the vendor DT supports 2, so 0018 is
  probably wrong -- but it is inert, so this is tidiness.

## Working tools in `h713_disp`

| command | purpose |
| --- | --- |
| `init <id> [quiesce\|noboot]` | bring-up only, no test phases; `quiesce` parks the MIPS, which is what the register diagnostics want |
| `scanrate` | measures the free-running counter; a clock witness, **not** a raster counter |
| `regscan [base] [words]` | finds which registers move and what they count |
| `clkfind [n]` | lists candidates, or perturbs one and watches the clock witness |
| `panel-test <id> tcon-chroma` | RGB solids and red/blue checkers -- the reference that must render correctly |
| `panel-test <id> fb-edge` | the stride measurement, 1180..1200 -- the range that produced 1237 by extrapolation |
| `panel-test <id> fb-edge-fine` | 1232..1240, closes the stride to the pixel |
| `panel-test <id> fb-stride` | pattern fixed, AFBD `0x05600170` swept -- answered: live, `S = V - 42` |
| `panel-test <id> fb-fix` | pattern at the natural 1280, swept for the register that unshears it |
| `panel-test <id> fb-band` | solid fill, screens offset registers for the ~105 px left band |
| `panel-test <id> <mode> <stride>` | any mode with `0x05600170` forced to `<stride>` bytes, applied after the DE replay |
| `panel-test <id> fb-vprobe` / `fb-hprobe` / `fb-quad` / `fb-grid` | framebuffer geometry probes |
| `panel-test <id> vendor-logo` | the vendor bootlogo, with `fbcheck` verifying the conversion |
| `teardown` | stop scanout, park the MIPS, drop the panel rail; run twice to prove it |
| `tools/display/edge-measure.py` | host-side: stripe count -> stride, from the photographs |

**Power-cycling between runs is no longer needed.** `panel-test` tears down
first when it has already run this boot, and the second run renders correctly --
verified on hardware 2026-08-04, both chroma markers and the logo.

The old rule was: each mode ended holding the MIPS in reset, so a second run
initialised into a torn-down state and the panel stayed dark while the console
looked perfect. That cost at least four results. It was never a property of the
hardware -- it was the absence of a teardown.

`h713_disp teardown` also runs it standalone. What it does, in order: stop
scanout, park the MIPS, return the LVDS PHY and display route to their cold
values, then drop PH16 and PF6 with the panel's declared off timings
(20/75/250 ms). Confirmed output:

```
panel down (PF_DAT=00000000 PH_DAT=00000000), PHY 18000000/00000030,
route 40000000, MIPS reset=00000000
```

`0x00000000` on the reset register is the **asserted** state.

The likely reason a second run used to fail is visible in that line: the
bring-up powers the panel by driving PF6 high and pulsing PH16, so with the
panel still powered from the previous run that "power on" was a no-op and the
panel never re-ran its own init.

Two gaps remain, both deliberate and both commented in the source. The backlight
is not touched, because which PWM drives it is unresolved. The PLLs and mod
clocks are left running, because disabling a clock while something still reaches
for the block is the documented way to wedge this interconnect -- and the
bring-up rewrites that state absolutely, so the acceptance test passes without
it.

## Method notes that cost real time

- **Use chroma, never luminance.** The optical path normalises luminance away.
  Every solid black/white and greyscale test in the old log read blank regardless
  of what the link was doing, which invalidated years of results.
- **A pattern is only as good as the photograph it must survive.** Fine features
  photographed handheld alias into moire. Two numbers in this session came from
  moire and had to be withdrawn. Prefer few large features.
- **Never report a property the instrument cannot measure.** A column-only metric
  said "no row alternation" when the rows were fine. A row-luminance profile said
  the logo was correct when it was horizontally sheared. Uniform-width bands
  "proved" a framebuffer path that was 8% wrong.
- **State the premise as a number and check it before crediting the result.** The
  retune guard -- "the clock witness must move by X% or this run means nothing" --
  caught three false conclusions cheaply.
- **Prefer the photograph to the metric when they disagree.** The operator saw a
  checkerboard that the scoring metric ranked below a worse setting.
- **Two symptoms of one fault are still two measurements.** The band and the
  stripes were both called "the pitch", so a number from the band was used to aim
  a sweep at the stride. Six steps, a rebuild and a bench run all missed, and the
  answer was never inside the range. Before a sweep, say which quantity each
  observable measures, and check that the thing being swept is that quantity.
- **Design the sweep so a miss still measures.** Every step of that run was
  wrong, and the run still gave the answer to +-1 px, because the stripe count is
  a slope rather than a match. A sweep scored on "which step looks right" would
  have returned nothing at all.

## Superseded claims

Do not resurrect these; each cost bench time.

- `0x05880000` is **not** a raster position counter. It is one free-running
  10-bit counter presented twice with a fixed offset. Every "scan=... proves the
  raster is live" claim in the old log is void.
- The panel clock does **not** come from the CCU's `PLL_VIDEO2` at `0x02001050`.
  Retuning it moves nothing.
- The Saleae captures cannot decode this LVDS stream: 31.25 kS/s analog against
  434 Mbps, short by a factor of ~14000, with a front end that cannot see the
  signal at any rate.
- A static write map of the firmware is a **lower bound** on register access,
  never an inventory. It resolved 604 of 845 call sites and the answer to the
  contested-register question was among the rest.
- The pale edge band is **not** a panel or TCON artefact.
- The bootlogo was never "vertically collapsed" -- the BMP is a black frame with
  text only in rows 343..378, and it rendered faithfully once the PLL was fixed.
- **"The display fetches ~1187 pixels per line" conflated two numbers.** 1187 was
  a content width taken off the band and then used as though it were the source
  stride. The stride is 1237-1238; the width measures 1155 +- 5. Any
  reasoning that treats one figure as both is void, including the sweep ranges it
  produced -- 1180..1200 could not have contained the answer.
