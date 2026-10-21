# DSP access TVTOP stage — offline preparation, October 21, 2026

**Offline only. No board staging, module load or live step.** Implements the
[TVTOP stage design](../../hdmi-dsp-tvtop-stage-design-2026-10-21.md), which
follows the [lock-window prerequisite note](../../hdmi-dsp-lock-window-prerequisite-2026-10-21.md).

- **Module** `ba785734…`: steps 1–92 are unchanged in operation and order:
  prefix, census, extension, AudioTop read/init and the DSP status sample.
  New steps 93–104: map TVTOP `0x05700000` (unclaimed); read the
  SPL-proven `+0x40`, `+0x44`, `+0x80`; then `h713_display_prepare()`'s seven
  routing writes, verbatim and in order, one per step with exact readback;
  12 ms settle after the last; MIPS/SCP recheck. Steps 105–108: lock window
  map, peer, own, and a final recheck that now also requires TVTOP `+0x00`
  `fff11111`. No DSP request, lock write or mixer write. W=1 build, only the
  known compiler-version warning; vermagic `6.18.38 SMP mod_unload aarch64`;
  **imports unchanged** from the AudioTop stage.
- **Helper** `326740fb…`, schema `h713-dsp-access-tvtop-v1`:
  108 steps; new boundaries after 92 (`dsp-status`), 96 (`tvtop-census`),
  104 (`tvtop-routing`), end snapshot 108 (`lock-sampled`). `tvtop_cold` and
  `tvtop_set` are reported as text arrays at steps 96 and 103.
- **Guard** `96f37655…` unchanged (installed). **boot-v4** reused; its hashes
  were rechecked against the extension preparation.

Checks: `tvtop-tests.txt` (19 pass). This includes a test that pins the C
routing table to the U-Boot values and order independently, that ties the
step names to the table, and that limits the cold census to `+0x40`/`+0x44`/
`+0x80`. Another test enforces TVTOP routing before any lock access and the
DSP status sample before TVTOP. Guard (3), legacy observe (5) and boot-prep
(3) still pass. Mutation checks, each of which failed the suite:
- changing a routing value;
- swapping the routing order;
- a cold read of `+0x00`;
- mapping the lock window before TVTOP;
- dropping the `tvtop-routing` or `dsp-status` boundary;
- parsing an array sample as an integer;
- not reporting `tvtop_cold`.

Offline consistency only.
