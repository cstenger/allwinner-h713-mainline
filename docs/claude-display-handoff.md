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

**Two faults remained in the framebuffer path. One is now fixed.**

> **Fixed 2026-08-04.** The left band was `0x0528008c`, the layer's pixel X
> origin, coming up at 123. It is 1:1 with nothing else in it: zeroed, content
> starts at column 0 and fills all 1280. Now written to 0 after the DE replay,
> so every mode gets it.

> **Open.** The source pointer advances **~1238 words per display row where we
> write 1280**, and **`0x05600170` controls it**, with unit slope: `S = V - 42`.
> `fb-fix` sweeps for the value that makes it 1280; predicted 1322 (`0x14a8`).

Measured twice, by unrelated routes, on 2026-08-03:

- **test_30**, `fb-edge`: five photographed steps, stripe counts 34.1/31.9/29.9/
  25.3/22.9. A search over every stride from 2 to 4000 leaves one solution.
  Robust to the step-to-pitch mapping (only five of six steps were photographed):
  re-solving under all six possible mappings gives 1236..1240, best fit 1237.
- **test_31**, `fb-stride`: sweeping the register and fitting `S(V)` puts the
  default `V = 1280` at `S = 1238`.

Those two share no assumption beyond the stripe model itself, so the value is
**1237-1238** and the *sign and scale* are not in doubt. That matters, because

**this is two numbers, and the old log had them as one.**

| | what it is | what measures it | value |
| --- | --- | --- | --- |
| stride `S` | how far the source pointer advances per display row | the stripes | **1237** |
| width `W` | how much of the display line receives content | the pale band | **1155 +- 5**, all of the shortfall at the **left** |

The old "~1187 px/line" was `W`, inferred from the band, and then used to predict
`S`. They are different quantities and neither equals the other, which is why the
`fb-edge` sweep was aimed at 1180..1200 and every one of its six steps missed --
the answer was 37 to 57 px outside the range, in the direction nobody swept.

Consequences of what is left: horizontal variation in a framebuffer image
becomes vertical stripes, and the vendor bootlogo arrives as a sheared streak. The TCON pattern generator bypasses this
path entirely, which is why its output is perfect.

## What is proven, and how

| fact | evidence |
| --- | --- |
| display PLL is `0x058c0014` | `clkfind 0`: N+1 43->42 moved the clock witness -2.28% against -2.326% predicted |
| the PLL runs at 24 MHz x (N+1) | same, plus the counter tracking N to 0.1% across a six-step sweep |
| DCLK = PLL/14 | the panel decodes at 864 MHz and 864/14 = 61.71 vs the 62.00 requested |
| the free-running counter is PLL/56 | 18432 kHz measured against 18428.6 computed |
| the framebuffer conversion is correct | `fbcheck` reads the framebuffer back: bootlogo content in rows 343..378, columns 368..912, exactly matching the file |
| the stride is 1237-1238 px/row | test_30: five `fb-edge` steps give 34.1/31.9/29.9/25.3/22.9 stripes; `S mod P` from five pitches leaves one candidate in 2..4000. test_31 gets 1238 from the register fit, sharing no assumption with it |
| `0x05600170` controls the stride | test_31: counts track the register 2.96/5.24/7.58/10.01 against 2.3/4.7/7.0/9.3 predicted, and the below-default step leans the other way |
| `0x0528008c` is the layer X origin | test_32: 123 -> band 119.4, **0 -> 0.0**, 400 -> 406.2. Four other candidates screened in the same run moved it by 1 px |
| the band was never framebuffer content | test_32 step 1: it stays pale against a saturated red fill, so a geometry fault, not addressing |
| the slope is unity, `S = V - 42` | same run, fitting the four well-determined steps: rms 0.04 stripes |
| stride and width are different numbers | test_31 sweeps the stride 1230..1254 and the band holds at 1158 +- 4; test_30 sweeps the pattern and it holds at 1152 +- 2. Neither knob touches it |
| the band was at the **head** of the line, not the tail | ~120 px blank on the left, content running to the right edge, in all eleven photographs before the fix |
| the photographs are not mirrored | the stripe lean matches the model in absolute sign across five steps of test_31, including the flip at the one step below default; so left is left |
| the band belongs to the framebuffer path | operator observation: TCON generator patterns fill the whole screen, framebuffer patterns are truncated |

## Ready to run

Artifact hashes move on every rebuild -- U-Boot embeds a build timestamp -- so
the commit is the source identity, not the hash. Rebuild with
`./build/build.sh uboot`.

```
h713_disp panel-test 0x33 fb-fix
```

The register is live, so this is the run that closes the framebuffer path
rather than measuring it again. The pattern is written at the **natural 1280**
-- what any real client will use -- and the register is swept for the value that
renders it with no shear at all. Predicted, from `S = V - 42`:

| register | 1300 | 1310 | 1320 | 1330 | 1340 | 1280 (control) |
| --- | --- | --- | --- | --- | --- | --- |
| stripes | 12.4 | 6.8 | **1.1** | 4.5 | 10.1 | 23.6 |

> **A step showing ONE vertical edge is the framebuffer path fixed.**

The control is the same pattern at today's register value, so the run carries
its own before-and-after in one strip of photographs.

Steps are a coarse 10 px because 1322 is extrapolated 42 px beyond anything yet
measured. A wide sweep still measures if the offset is off; a tight bracket
around 1322 would simply miss.

Then confirm it on real content, using the trailing-stride argument so no
rebuild is needed between:

```
h713_disp panel-test 0x33 vendor-logo 0x14a8
```

`0x14a8` is 5288 bytes, 1322 px -- substitute whatever `fb-fix` actually picks.
**The bootlogo arriving un-sheared is the end of this bug.**

The band is already gone -- the run applies `0x0528008c = 0` before the sweep --
so `fb-fix` reads against a full-width image. If a left band reappears, the
correction did not stick and that is a finding in itself.

### The band, for the record (fixed 2026-08-04)

Kept because the method transfers, not because the question is open.

Content used to start ~120 px into every display line -- left 119.4, right 0.9,
**top 0.0**, bottom 6. Horizontal only, at the *head* of the line.

The zero top pad is what cracked it. `0x05280088` and `0x0528008c` hold 22 and
123, which read like a `(y, x)` origin, and 123 was within a few px of the band
-- but a `y` of 22 would blank 22 rows at the top, and nothing was blank at the
top. That ruled out the pairing while leaving 123 the closest value in the dump,
which is why `0x0528008c` was screened both ways rather than swept alone.

`fb-band` runs six steps on a **solid red** fill -- immune to the stride bug, so
the band edge is the only thing in frame and each step scores as one number.

| step | written | left pad |
| --- | --- | --- |
| 1 | control | 119.4 |
| 2 | `0x0528008c` 123 -> 0 | **0.0** |
| 3 | `0x0528008c` 123 -> 400 | **406.2** |
| 4 | mixer `0x0525c01c`+`034` low 60 -> 0 | 120.6 |
| 5 | de `0x0524c004` low 22 -> 0 | 121.3 |
| 6 | vblender `0x0520000c`+`024` low 49 -> 0 | 105.6 |

Score with `tools/display/edge-measure.py --band IMG_*.jpeg`.

Three things about this run are worth reusing:

- **Two-sided perturbation.** Zero alone would have been weak evidence -- plenty
  of registers could blank a band by breaking something. 400 landing on 406 is
  what makes it a *measurement* of an origin rather than a knockout.
- **The control step earned its photograph.** The band stayed pale against a
  saturated fill, so it was never framebuffer content: a geometry fault, not
  addressing. Nothing else in the run separated those.
- **The noise floor was measured first**, by running the scorer over test_31
  where nothing could have moved: 8 px. Steps 4 and 5 came back at 1-2 px, so
  they are real nulls rather than hopeful ones.

Two loose ends, neither load-bearing:

- **Step 6 moved the band 14 px**, above that floor. Its pairing was also wrong:
  `0x05200024` holds `02d00016`, so the sibling of `0x0520000c` by value is
  `0x05200020`, not the register that was written. Since `0x0528008c` accounts
  for the band exactly, this is at most a small second contribution.
- **What writes 123 is still unknown.** It survives the DE replay, so it is
  LogoRegData or the firmware. The fix is a write afterwards, not a patched
  record, for exactly that reason.

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
