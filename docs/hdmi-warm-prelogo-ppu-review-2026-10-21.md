# Warm pre-logo PPU observation — October 21, 2026

Status: reviewed offline and runner tested; subsequently
[run on hardware](hdmi-evidence/2026-10-21-warm-prelogo-ppu/README.md).
Both domains were ON before and after the single logo invocation; TVFE was
OFF in Linux. The design below precedes that run; see its recording caveats.
Continuation of the [A–C results](hdmi-evidence/2026-10-21-warm-retention/README.md).
The operator confirmed the board was made unpowered during this continuation.

## Review of Claude's handoff

All 41 curated evidence hashes match. Both warm censuses show TVFE OFF,
TVCAP ON, MIPS parked and lock own/peer zero. Both preboot censuses show
bus-r-ppu closed, so neither measured TVFE before the logo. Neither measured
DSP versions. SysRq-b excludes a requirement for orderly Linux teardown;
it does not establish what happened during reset or subsequent boot.

`pd_ignore_unused` only suppresses `genpd_power_off_unused()` in the exact
kernel's `drivers/pmdomain/core.c`. It does not suppress ordinary runtime-PM
power-off callbacks. The absence of HDMI owners in the warm census is useful
evidence, but the cmdline alone is insufficient to exclude all Linux power
transitions. Observe before Linux to remove that uncertainty.

## Offline warm-path audit

Reviewed both `external/u-boot/arch/arm/mach-sunxi/h713_mips.c` and the actual
instrumented build source at
`build/hdmi-reset-controls-2026-10-20/src/arch/arm/mach-sunxi/h713_mips.c`
(SHA-256 `66968dda29377b6285e34eafa1ae95a4ed885e72a6d444097d743dd3252471b7`).
The trees differ; the installed-build source takes precedence.

- `tools/hdmi/build-startup.py`'s warm branch checks GP6, calls
  `h713_disp auto 0x34 logo` if MIPS is parked, then boots the FIT without
  the cold capture handoff. There is no PPU command in that branch.
- `h713_disp_auto_logo_mode()` loads the display assets, calls
  `h713_disp_run()` with MIPS release enabled, quiesces the core, re-latches
  panel timing, replays the DE table and publishes the logo.
- `h713_logo_reg_sane()` only allows `0x02000000..0x030fffff` and
  `0x04000000..0x06ffffff`. Therefore the ARM table walker cannot write PPU
  (`0x07001xxx`) or R_CCU (`0x07010xxx`) addresses, regardless of table data.
- `h713_mips_stop()` only asserts the MIPS reset and disables its clock.
  The successful logo path uses `h713_disp_quiesce_mips_owner()`, which
  asserts the core reset and samples display scan registers. Neither has
  a domain power-off operation.
- The installed build adds panel initial-off handling and post-logo reset
  tracing. The panel operation controls the panel supply and reset; it is
  not a TVFE PPU operation. No literal PPU references occur in this MIPS C
  file. This is not a complete proof against computed addresses elsewhere.

**Finding:** no direct ARM PPU power-off operation was identified in the
warm logo path. **MIPS firmware does execute**, and its indirect accesses
have not been comprehensively audited for this question. The offline review
cannot separate reset/early boot from firmware activity. Proceed to a
measurement before the logo rather than infer patch erasure.

## Narrow diagnostic and run sequence

The runner `tools/serial/warm-retention-uboot.py` now has an opt-in
`--open-ppu-bus` mode. Its default census remains read-only. The new mode:

1. Requires `--expected-bootcmd` and rejects `--boot` before opening UART.
2. Runs the existing read-only census and compares bootcmd before mutation.
3. Requires R_CCU PPU exactly zero, GP6 exactly `48444d49`, and MIPS status
   exactly zero. This excludes using the write on a cold or live-MIPS boot.
4. Saves write intent to JSON, sends only
   `mw.l 0x070101ac 0x00010001 1`, and reads that word back.
5. Requires exact `00010001` before either PPU read. Records TVFE and TVCAP
   status one at a time and stops at the U-Boot prompt. Does not boot.

This is a bus gate/reset-release change, **not a TV-domain power command**.
Linux has repeatedly opened this same bus. U-Boot execution of this combined
write has not been qualified live. Opening/reset-releasing the controller is
an intervention; do not equate its resulting state with an untouched sample.
Do not restore zero afterward: asserting the controller reset adds another
unnecessary intervention. Preserve UART, inspect the result, then decide the
next single action. A failed operation/readback stops without retry or boot.

Use a new output tree, `build/hdmi-warm-prelogo-ppu-2026-10-21/`:

1. Arm the cold catcher before reconnecting after at least a minute fully
   unpowered. Capture one SPL and GP6 zero. Run the unchanged cold preboot
   census with `--record-bootcmd`, then boot production.
2. Collect a fresh boot ID, production health and read-only census. Require
   cold versions `0/0` followed by verified patch `1/1`, both domains ON,
   and normal HDMI ownership. No remedial relaunch on failure.
3. Arm a new catcher before an orderly production reboot. Correlate shutdown
   and one warm SPL. At the prompt, run the diagnostic with the recorded
   bootcmd, label `warm-prelogo`, and **without `--boot`**.
4. Inspect the two PPU statuses before further action. On success, normal
   `boot` and another warm-parked census can compare before/after the logo
   and Linux. The bus-opening intervention means this is a diagnostic cycle,
   separate from the unmodified A–C controls. End with orderly poweroff.

| Warm pre-logo result | Interpretation |
| --- | --- |
| TVFE already OFF | Warm logo and Linux are not required for the observed OFF state. Reset, SPL, BL31 or earlier proper initialization remain candidates. |
| TVFE ON, later OFF | Transition occurs after this observation; add a post-logo, pre-Linux sample to separate firmware/logo from Linux. |
| Unknown state, gate mismatch, repeated SPL or lost UART | Stop; no version request, power toggle, automatic boot or retry. |

No GP6/GP7 write, saved environment change, firmware replacement, SCP launch,
DSP request, lock write or TV-domain transition is included.

## Phase D boundary

Phase D remains unimplemented. Powering TVFE ON before a version read changes
the state under study; document that intervention and obtain a census before
and after it. Use a dedicated warm-mode helper/module: the existing cold
audit requires maintenance DT markers and is not authorized unchanged on
production warm Linux. Require parked MIPS, no handoff/owners, exact domain,
clock/reset and routing checks, and a verified stock lock claim/release before
a single version pair. Readable zero lock words do not yet prove writability.
Never reinterpret a lock failure or version timeout as `0/0`. Even observed
`0/0` after power-on is insufficient by itself to authorize a source3 relaunch.

Validation: `python3 tools/hdmi/test-warm-retention.py` passes 19 tests,
including exact opt-in write allowlisting, checkpoint ordering, rejection
of cold/live/unexpected states, and refusal to read PPU after bad gate
readback. These are offline protocol checks, not a hardware pass.
