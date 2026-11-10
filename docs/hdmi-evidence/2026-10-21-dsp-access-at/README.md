# DSP access AudioTop stage — offline preparation, October 21, 2026

**Offline only. No board staging, module load or live step.** Implements the
[AudioTop stage design](../../hdmi-dsp-audiotop-stage-design-2026-10-21.md)
on top of the [extension that passed live](../2026-10-21-dsp-access-ext-live/README.md).

- **Module** `26faf61f…`: steps 1–82 unchanged in operation and order. Step 82
  is now a stage boundary rather than the end. New steps 83–96: map AudioTop;
  read `ctl`, then `cfg`, as separate steps, refusing an inherited setup at
  85; read-only TVFE control word `0x06e00000`; AudioTop `ctl | 0x700`, cfg
  `0x001a5e00`, then the bit-24 latch, each with readback; MIPS/SCP recheck;
  plain DSP status and lock peer/own samples (refusing busy bits or `0x55`);
  final recheck. No DSP request and no lock write. The extension-complete
  parameter is now `stage_complete` (`complete` collided with the kernel's
  `complete()`). W=1 build against the exact 6.18.38 tree; only the known
  compiler-version warning (`module-build.txt`). Vermagic
  `6.18.38 SMP mod_unload aarch64`. **Imports are identical to the
  extension's** (`module-imports.txt`): the new steps use only ioremap,
  readl and writel.
- **Helper** `3e14a860…`, schema `h713-dsp-access-at-v1`: the 96-step table;
  new boundaries after 82 (`extension`), 86 (`audiotop-read`) and 90
  (`audiotop-init`), and an end-of-run snapshot at 96 (`dsp-sampled`).
  Samples are reported in the step results at 85, 86, 92, 94 and 95.
  Release is still refused after step 40.
- **Guard** `96f37655…` unchanged (already installed). **boot-v4** reused
  unchanged; its commands, manifest and reference DTB hashes were rechecked
  against the extension preparation (`preparation.json`).

Checks: `at-tests.txt` (18 pass); guard (3), legacy observe (5) and boot-prep
(3) still pass. Mutation checks: dropping any of the three new boundaries,
dropping a sample, adding a request step to the helper, swapping the C
AudioTop read order, renaming a C lock step to a write, or ignoring
`stage_complete`. Each failed the suite. Dropped boundaries were initially
missed because the boundary test iterated the helper's own table. A pinned
boundary-set test was added, and all three then failed. Offline consistency
only: nothing here shows AudioTop, the DSP port or the lock window is
readable on hardware.
