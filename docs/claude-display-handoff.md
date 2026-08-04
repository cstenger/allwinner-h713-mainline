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

**Not `vendor-logo`.** The stock `bootlogo.bmp` is 99% black and its lit pixels
are **pure grey -- chroma `|R-B|` is exactly 0 across the whole file, maximum
0**. This optical path normalises luminance away; that is the oldest and most
expensive rule in this bring-up. A blank result from `vendor-logo` carries no
information: it looks the same whether the path is perfect or the panel never
lit. One run was spent on exactly that.

`vendor-logo-chroma` keeps the same file, hash check, geometry and `fbcheck`
bounds, and swaps only the palette -- lit to red, unlit to blue.

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
| `tools/display/edge-measure.py` | host-side: stripe count -> stride, from the photographs |

**Power-cycle between every run.** Each mode ends holding the MIPS in reset;
running two in a row leaves the second starting from a torn-down state and the
panel dark. Two blank results in this session were that, not bugs.

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
