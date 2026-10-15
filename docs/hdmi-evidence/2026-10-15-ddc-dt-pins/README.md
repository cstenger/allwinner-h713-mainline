# DDC pins in the device tree with an exact io_disabled release, 2026-10-15

**Result: PASS.** The pins now return bit-for-bit to their pre-claim state.

**Kernel FIT `68c0b730…`** (7,789,772 bytes; series through 0179, tree
`0b40c553…`; host copy of the previous FIT in
`build/out/known-good-2a2ced73/`):
- `0178` adds `io_disabled` (mux 0xF, the reset state) to every R_PIO pin.
- `0179` adds the `h713-lab,ddc-pins` node. Its `default` state is
  `s_twi0/1/2` and its `sleep` state is `io_disabled`.
- The FIT also carries `b27e345`'s audio-bridge IRQ order. That has no effect
  in Linux, because the board DTS disables that node.

## Deploy (boot `015ba0b6…`)
- **`install-kernel-fit.log`:** the new FIT was installed on the FAT and
  md5-verified. The outgoing FIT `a298eeb8…` is kept as
  `/mnt/media-data/h713-kernel-fits/replaced-20261015-033917.fit`.
- **`rebaseline.log`:** the startup kernel pin moved to `68c0b730…`, with the
  old pin kept.
- **`update.log`:** `update-signal-owner.sh` installed the DT-bound
  `h713-ddc-pins.ko` and the new `install-startup.sh`.

## Miss and recovery
I had updated the FIT/FDT size pins in the Linux-side tools but not in the
guarded U-Boot script. On the first cold boot, the script's first guard
correctly refused the new FIT (`stopped-prompt-serial.log`):
- `filesize = 76dccc` against the pinned `76daa0`;
- `hdmi_fdt_size` never set;
- MIPS status 0, GP6 and GP7 0: a clean cold prompt.

The recovery followed the 2026-10-14 resume precedent:
1. `build-startup.py` now derives all three U-Boot guards from single
   `FIT_SIZE`/`FDT_SIZE` constants, and **refuses to build** if
   `build/out`'s FIT or DTB does not match them (new regression test). The
   script differs from the installed generation only in those three tokens.
2. The fixed `h713-hdmi.scr` (`f317cd4e…`, crc32 `9dc73b5c`) was sent by
   YMODEM to `0x52000000` and verified, then sourced (`loady.log`,
   `source-fixed-script-serial.log`). Result: "H713 HDMI cold startup handoff
   verified", and the new kernel booted.
3. `update-startup-script.sh` installed the fixed script persistently
   (`update-script.log`). The previous generation is kept, and the kernel pin
   and installed tree verify.

## Verification on the new kernel (boot `6195b935…`)
- **`check-startup.log`:** PASS.
- **`claim.log`:**
  - The helper is bound to `/sys/devices/platform/h713-ddc-pins`
    (`h713-lab,ddc-pins`).
  - It recorded the original as `ffffff` and claimed `222222`.
  - debugfs `pinmux-pins` shows PL10–15 owned by `h713-ddc-pins` with
    functions `s_twi0/1/2`.
  - The host reads the fixture EDID.
- **`release.log`:** `systemctl stop h713-hdmi-signal` ended
  `inactive success`.
  - The signal readback equals the originals.
  - The helper logged "returned to io_disabled (mux ffffff, original ffffff)".
  - **The live register reads `0xFFFFFF3F`**, identical to the pre-claim
    value; PL9 (IR) is unchanged.
  - The pins show `UNCLAIMED` and the receiver has `clients=1`.

**Pending:** an unattended cold boot through the persisted fixed script.
