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

> The display fetches roughly **1187 pixels per line where we write 1280**.

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
| the fetch is ~1187 px/line | pale band is 7.2% and 7.3% of the projection in two independent captures; 1280 x 0.927 = 1187 |
| the band belongs to the framebuffer path | operator observation: TCON generator patterns fill the whole screen, framebuffer patterns are truncated |

## Ready to run

Artifact hashes move on every rebuild -- U-Boot embeds a build timestamp -- so
the commit is the source identity, not the hash. Rebuild with
`./build/build.sh uboot`.

```
h713_disp panel-test 0x33 fb-edge
```

Six steps, assumed pitch 1180/1184/1188/1192/1196/1200, each preceded by that
many chroma blinks.

**Count the diagonal red/blue stripes in each step.** Row Y starts at word
`Y*P_hw`, so the boundary slides `D = P_hw - P` pixels per row and wraps every
`P/|D|` rows. A 720-row frame therefore shows `N = 720*|D|/P` stripes, and

> `|P_hw - P| = N * P / 720` -- about **1.64 px per stripe** at these pitches.

So every step measures the pitch independently and the six must agree. That is
a far stronger result than picking the vertical one, and it survives a blurry
photograph: counting a few coarse diagonals is easy.

- **fewest stripes** -> closest step
- **two steps leaning opposite ways** -> the answer is bracketed between them
- **a single edge** -> only from a step within ~1.6 px of the truth. With 4 px
  steps at most one can be; expect 2, 3, 5, 8 stripes from the others.

Do **not** read a multi-stripe step as a failed step, or as moire. It is the
measurement. (An earlier version of this page promised "one boundary per step"
and would have made every step but one look broken.)

Do **not** score this on the pale band. The band is a hardware property and
cannot respond to the pattern; that criterion was wrong and wasted a run.

Then: find which register carries that width. `0x05600170` reads `00001400`
(5120 bytes = 1280 px) and `0x05600160` reads `02d00500` (720 x 1280), so
whatever is producing 1187 is not one of those two, or is not being consulted.

## Working tools in `h713_disp`

| command | purpose |
| --- | --- |
| `init <id> [quiesce\|noboot]` | bring-up only, no test phases; `quiesce` parks the MIPS, which is what the register diagnostics want |
| `scanrate` | measures the free-running counter; a clock witness, **not** a raster counter |
| `regscan [base] [words]` | finds which registers move and what they count |
| `clkfind [n]` | lists candidates, or perturbs one and watches the clock witness |
| `panel-test <id> tcon-chroma` | RGB solids and red/blue checkers -- the reference that must render correctly |
| `panel-test <id> fb-edge` | the pitch measurement above |
| `panel-test <id> fb-vprobe` / `fb-hprobe` / `fb-quad` / `fb-grid` | framebuffer geometry probes |
| `panel-test <id> vendor-logo` | the vendor bootlogo, with `fbcheck` verifying the conversion |

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
