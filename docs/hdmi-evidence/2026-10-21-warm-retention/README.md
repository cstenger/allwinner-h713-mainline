# Warm-retention test, phases A–C — live runs, October 21, 2026

**Result: identical for an orderly reboot and a SysRq-b abrupt reset.** Both
return the R_CCU PPU bus gate/reset to its cold default. In the warm-parked
Linux that follows, **TVFE is OFF, TVCAP is ON, and the ARM lock word is
cleared** (`0xaa` → `0`). TVFE being off is not caused by production
teardown (the abrupt reset has none) or by Linux genpd (`pd_ignore_unused`).
It comes from the reset itself or U-Boot's warm branch. **DSP patch
retention is still unmeasured:** no DSP command was sent in A–C. All reads
were read-only, and production boot policy was unchanged.

Design: [warm-retention test](../../hdmi-warm-retention-test-design-2026-10-21.md).
Tools: `tools/serial/warm-retention-uboot.py` (set U),
`tools/hdmi/warm-retention-census.py` (set L).

## Results

| Point | R_CCU `0x070101ac` | PPU TVFE | PPU TVCAP | Lock peer/own | Other |
| --- | --- | --- | --- | --- | --- |
| Cold preboot (both cycles) | `00000000` | not read (bus closed) | not read | — | GP6 `0`; one SPL |
| Cold-live production (both cycles) | `00010001` | `00010000` ON | `00010000` ON | `0` / `0xaa` | journal `DSP versions 0000/0000` → `pinned 724-pair DSP patch verified versions 1/1`; MIPS 1; TVTOP routed; AudioTop `700`/`011a5e00`; DSP status `0x120` |
| Warm preboot after orderly reboot | **`00000000`** | not read | not read | — | GP6 `48444d49`; `bootcmd` identical |
| Warm preboot after SysRq-b | **`00000000`** | not read | not read | — | GP6 `48444d49`; `bootcmd` identical |
| Warm-parked Linux after orderly | `00010001` | **`00020000` OFF** | `00010000` ON | `0` / **`0`** | MIPS 0, no handoff, HDMI units skipped, no h713 modules; TVTOP routed |
| Warm-parked Linux after SysRq-b | `00010001` | **`00020000` OFF** | `00010000` ON | `0` / **`0`** | same |

## Cycle 1 — orderly reboot (`cycle1/`)

- **Aborted first attempt** (`cold-catch/`, `passive-after-abort.log`). The
  board was already booting when the catcher opened, and GP6 was still
  `48444d49`, so this was not a cold start. No command was sent. The operator
  cut power.
- **A1** (`cold-catch-2/`, `A1-cold-preboot/`): cold catch, set U; `bootcmd`
  recorded (`bootcmd.txt`, sha256 `b88572b5…`); `boot`.
- **A2**, boot `f5c76641-c095-4f6f-ac7b-03f92ddb493b` (`A2-health.txt`,
  `A2-census.json`, `A2-production-uart.log`): handoff present, all units
  active, DSP `0/0` → `1/1`. The first census attempt failed before any read,
  because it decoded a binary DT property as text
  (`A2-census-attempt1-unicode-error.txt`). The tool was fixed (presence
  check plus a regression test) and rerun.
- **B1** (`B1-reboot-request.txt`): `systemctl reboot` with units active; UART
  `reboot: Restarting system` at 124.5 s (`B2-warm-catch/`).
- **B2** (`B2-warm-preboot/`): warm set U, then `boot`.
- **B3**, boot `4062c792-2301-44df-84c7-22235e7b9162` (`B3-census.json`).
  The teardown journal for `f5c76641` is not in the board's boot list
  (`B3-journal-boot-check.txt`; the board's clock resets). `B3-teardown.txt`
  and `B3-teardown-and-id.txt` are therefore *not* teardown records: `-b -1`
  returned the warm boot itself. Teardown evidence is limited to the reboot
  request and the UART restart line.
- **End:** orderly poweroff (`end-poweroff-*`, `reboot: Power down`).

## Cycle 2 — abrupt reset (`cycle2/`)

- **A1** (`cold-catch/`, `A1-cold-preboot/`): cold catch, `bootcmd` identical
  to cycle 1 (`bootcmd.txt` = `bootcmd-cycle1.txt`).
- **A2**, boot `63bb0271-b454-494e-818e-a5cee4d56822`: identical to cycle 1 A2.
- **C1** (`C1-abrupt-reset-trigger.py`, `C1-trigger-output.txt`): the
  October 20 guarded trigger with this boot ID. Guards: boot ID, all units
  active, both PCMs RUNNING, DSP not failed; sync; recheck. UART marker
  `H713_WARM_RETENTION_ABRUPT_SYNC_DONE` at 88.95 s, then `sysrq: Resetting`
  (`C2-warm-catch/`). No teardown. SysRq-b is an emergency reset, not a
  watchdog expiry.
- **C2** (`C2-warm-preboot/`): warm set U, then `boot`.
- **C3**, boot `4f760916-de5d-48e5-89db-d3281518da36` (`C3-census.json`).
- **End:** orderly poweroff; the production cmdline was confirmed to carry
  `clk_ignore_unused pd_ignore_unused` (`end-poweroff-request.txt`).

## What this establishes and what it does not

Established:
- Orderly and abrupt warm resets both reset the R_CCU PPU bus gate/reset.
- After either, the warm-parked state has TVFE off, TVCAP on, TVTOP routed,
  MIPS parked, and the lock words `0`/`0`.

Not established:
- **Whether the DSP patch survives** (no version read; AudioTop and DSP
  status were gated off with TVFE down).
- Whether TVFE is powered off by the reset itself or by U-Boot's warm branch,
  because the PPU bus is closed at preboot.
- Watchdog-expiry behaviour.

**Next:** an offline check of whether the warm `h713-hdmi.scr` / U-Boot MIPS
path touches the PPU/TVFE, then phase D (a gated warm version read, which
needs TVFE powered).

`sha256.json` covers every file in `cycle1/`, `cycle2/` and this README.
