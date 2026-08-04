# H713 display handoff

Last updated 2026-08-03. Operational companion to `docs/mips-display-recovery.md`
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

**One bug remains**, and it is in the framebuffer path only:

> The source pointer advances **1237 words per display row where we write 1280**.

Measured 2026-08-03 from test_30, five photographed steps of `fb-edge`. A search
over every stride from 2 to 4000 has exactly one solution. The runner-up is 1238
at 0.15 stripes worse, and since only five of the six steps were photographed the
step-to-pitch mapping is inferred -- but re-solving under all six possible
mappings gives 1236..1240, and the best-fitting one (step 1192 unphotographed,
rms 0.471 against 0.90..1.13 for the rest) gives 1237. So read this as **1237
+- 2**, which `fb-edge-fine` is sized to cover, until it closes the value; the
*sign and scale* are not in doubt, and that is what matters, because

**this is two numbers, and the old log had them as one.**

| | what it is | what measures it | value |
| --- | --- | --- | --- |
| stride `S` | how far the source pointer advances per display row | the stripes | **1237** |
| width `W` | how much of the display line receives content | the pale band | **1133 +- 8** |

The old "~1187 px/line" was `W`, inferred from the band, and then used to predict
`S`. They are different quantities and neither equals the other, which is why the
`fb-edge` sweep was aimed at 1180..1200 and every one of its six steps missed --
the answer was 37 to 57 px outside the range, in the direction nobody swept.

Consequences: horizontal variation in a framebuffer image becomes vertical
stripes; a pale band sits at one side where the fetch runs out; the vendor
bootlogo arrives as a sheared streak. The TCON pattern generator bypasses this
path entirely, which is why its output is perfect.

## What is proven, and how

| fact | evidence |
| --- | --- |
| display PLL is `0x058c0014` | `clkfind 0`: N+1 43->42 moved the clock witness -2.28% against -2.326% predicted |
| the PLL runs at 24 MHz x (N+1) | same, plus the counter tracking N to 0.1% across a six-step sweep |
| DCLK = PLL/14 | the panel decodes at 864 MHz and 864/14 = 61.71 vs the 62.00 requested |
| the free-running counter is PLL/56 | 18432 kHz measured against 18428.6 computed |
| the framebuffer conversion is correct | `fbcheck` reads the framebuffer back: bootlogo content in rows 343..378, columns 368..912, exactly matching the file |
| the stride is 1237 px/row | test_30: five `fb-edge` steps give 34.1/31.9/29.9/25.3/22.9 stripes; `S mod P` from five pitches leaves one candidate in 2..4000 |
| stride and width are different numbers | the same five photographs: stripe count varies 34->23 across the steps while the band holds at 1133 +- 8, exactly as a pattern-independent hardware property must |
| the band belongs to the framebuffer path | operator observation: TCON generator patterns fill the whole screen, framebuffer patterns are truncated |

## Ready to run

Artifact hashes move on every rebuild -- U-Boot embeds a build timestamp -- so
the commit is the source identity, not the hash. Rebuild with
`./build/build.sh uboot`.

```
h713_disp panel-test 0x33 fb-stride
```

**Is anything reading the stride register?** `0x05600170` holds `00001400` --
5120 bytes, 1280 px -- while the fetch measures 1237. So it is either not
consulted, or consulted through something that is not the identity. Only writing
it can tell those apart, and that is the difference between knowing the number
and being able to fix it.

Six steps hold the pattern at 1237 and move the register instead: 1280, 1284,
1288, 1292, 1296, 1272 px.

- **LIVE, unit slope** -> stripes appear as `720*k/1237`: **0, 2.3, 4.7, 7.0,
  9.3**, and step 6 matches step 3's count leaning the other way
- **INERT** -> six identical single vertical edges
- **anything else** -> the register is consulted through a transform; the counts
  give it directly

Step 6 is the control. It predicts the same count as step 3 with the opposite
lean, so a response that is real can be told from a count that merely grows.

Step 1 also re-measures the stride for free: it leaves the register alone, so a
truly vertical edge confirms 1237 and a visible lean says the fetch is `1237 +-
720/N`.

Then, to close the value to the pixel:

```
h713_disp panel-test 0x33 fb-edge-fine
```

Six steps at 1232/1234/1236/**1237**/1238/1240, predicting **2.9, 1.7, 0.58, 0,
0.58, 1.7** stripes. A V with one minimum; only the true stride shows a single
edge standing vertical, and +-1 px still slants across 58% of the width.

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
| `panel-test <id> fb-stride` | pattern fixed, AFBD `0x05600170` swept: is it consulted? |
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
  stride. The stride is 1237; the width measures 1133 +- 8 in test_30. Any
  reasoning that treats one figure as both is void, including the sweep ranges it
  produced -- 1180..1200 could not have contained the answer.
