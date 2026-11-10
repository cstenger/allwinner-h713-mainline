# M4: post-release init failures undone from proven states, 2026-10-15

**Result: PASS.**

**Policy (approved 2026-10-15):** a signal init failure after SCP release is
undone (SCP reset, SRAM and vectors restored byte-exactly, every hold
released) only from states the payload's own SRAM words prove:

| State | Code | Proof |
|---|---|---|
| Late ready (in the wait loop after the init poll gave up) | 1 | The normal cooperative stop, with readback == originals |
| EDID mismatch, then the payload's own full restore | 2 | Readback == originals |
| EDID header check failed before any receiver write (`data_failed`) | 3 | Readback area still the launch poison |

Traps, a failed restore and a payload that never started stay terminal, with
every hold. Once an attempt begins acting, any failure is terminal.

**Deploy** (boot `595ea002…`, `update.log`): the production module, which has
the `recovery` parameter and no `fault` parameter, and the wrapper were
installed with `update-signal-owner.sh`.

**Bench** (same boot, `bench.log`, `run.log`, `fault{1,2}-*.log`):
`run-signal-fault.sh` used a BENCH BUILD (`-DH713_SIGNAL_FAULT_INJECTION`)
through a runtime drop-in, after stopping the installed owner cleanly.
- **`fault=1`** (EDID header corrupted after ARM verified it): the payload
  reported `error=3 done ready=0`, with the readback poison intact. Undone
  from state 3.
- **`fault=2`** (the payload's first EDID verify reads the wrong word): the
  payload reported `error=1 done ready=0` and ran **its own full restore on
  hardware**. Its readback equals the originals (`1014=7 1b00=00a0a0a0
  1b04=07000000 1b08=00606060`, IO 0). Undone from state 2.

After each fault, the wrapper unit failed with "undone from proven state N,
nothing retained". Neither module was loaded, the receiver had `clients=1`,
the DDC register read `0xFFFFFF3F`, the per-boot latch was kept, and dmesg
had no warnings. Three SCP launches ran on that boot: the installed owner and
two bench faults.

**Shutdown** (`bench-boot-shutdown.log`): with the signal unit `failed` but
nothing held, the backend restored 22 DSP and 15 TVFE words, parked MIPS,
removed the receiver and powered off. Before M4, such a failure ended in the
H2 guarded unparked poweroff.

**Next cold boot** (`618c61bc…`): `check-startup.sh` PASS. The production
owner is loaded (`recovery=0`, no `fault` parameter, no bench string), and
the DDC claim reads `222222` from `ffffff`.

**Not exercised on hardware:** state 1 (late ready). It uses the same
cooperative stop as every normal shutdown.
