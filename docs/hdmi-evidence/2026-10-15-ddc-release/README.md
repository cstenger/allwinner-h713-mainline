# M3: verified, fallible DDC pin release on hardware, 2026-10-15

**Result: PASS.** The original-mux gap is now measured and documented.

1. **Deploy** (boot `b048eab0…`, `update.log`): the new `h713-ddc-pins.ko`
   and wrapper were installed with `update-signal-owner.sh`. Just before the
   update, the live register read `0x07022004 = 0x2222223F`: PL10–15 = 2
   (DDC), PL9 = 3 (IR), PL8 = F. This confirms the module's field layout. The
   following poweroff removed the **old** helper through the wrapper's
   fallback (direct `rmmod`). The operator confirmed lamp and fan off.
2. **Cold boot** (`015ba0b6…`, untouched): `check-startup.sh` PASS
   (`check-startup.log`). The new helper logged `claimed … (mux 222222,
   original ffffff)` (`claim.log`), so **all six pins were 0xF, "disabled",
   before the claim**. A bare `rmmod h713_ddc_pins` was refused ("in use"):
   the helper is pinned until a verified release.
3. **Release** through `systemctl stop h713-hdmi-signal` (`release.log`):
   - The signal readback again equalled the originals. This is the first stop
     of the H1 module through the installed unit.
   - The helper selected idle and read back `mux 000000`, logging "original
     ffffff, differs: pinctrl has no disabled function". It then dropped its
     pin and was removed.
   - The live register read `0x0000003F`: PL10–15 are `gpio_in`, and PL9's IR
     function is unchanged.
   - The unit ended `inactive success`, the receiver has `clients=1`, and both
     latches were cleared. dmesg shows no warnings.

**Remaining deviation:** the pins return to `gpio_in` (high-impedance input)
rather than to their pre-claim "disabled" state. The H713 R_PIO driver, like
every mainline sunxi table, exposes no function for mux value 0xF, so pinctrl
cannot select it. Exact restoration would need a project pinctrl patch that
adds such a function for PL10–15, plus a kernel rebuild and reflash.
