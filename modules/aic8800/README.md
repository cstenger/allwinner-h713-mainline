# AIC8800D80 WiFi + BT driver

Out-of-tree kernel modules for the **AIC8800D80** combo chip fitted on the HY200
boards: **WiFi over SDIO** (`mmc1@0x04021000`) and **Bluetooth over UART HCI**
(`uart1@2500400`). SDIO transport, not the USB dongle variant.

## Where the source comes from

**Not here.** The source is the `external/aic8800` submodule, patched by
`build/build.sh aic8800` the same way the kernel is:

    external/aic8800 @ AIC8800_COMMIT (submodule, HEAD asserted at build time)
      -> apply the repo's own debian/patches/series   (vendor kernel-compat)
      -> extract src/SDIO/driver_fw/driver/aic8800
      -> apply patches/aic8800/series                 (our H713 series)
      -> build against the pinned kernel, arm64 / LLVM

Pins live in `config/versions.env`; the series and its rationale are in
[../../patches/aic8800/README.md](../../patches/aic8800/README.md).

**This directory carries only `firmware.sha256sums`** (the firmware pin) and
this file.

### The stale copy, and what it cost (removed 2026-08-24)

`aic8800_bsp/`, `aic8800_fdrv/` and `aic8800_btlpm/` used to sit here holding
the **superseded 2024_0109 driver**. Nothing had built from them since
2026-08-17, and this file said so — but a full, plausible-looking driver tree at
an obvious path outranks a paragraph of prose. On 2026-08-24 it was read as the
real source while diagnosing a WiFi logging bug, and the two trees had diverged
enough to matter: the stale copy is missing the
`rwnx_dbgfs_unregister_rc_stat()` call the shipping driver makes on station
delete, which produced a confident diagnosis of a bug that does not exist in the
driver actually running. They were deleted the same day, and the upstream became
a submodule so there is exactly one readable tree.

For the record, that copy was the GPL SDIO driver from
`local/allwinner-h713-linux/drivers/wifi/` (well0nez H713 port of the
Aicsemi/Radxa V5 driver), release `2024_0109_ec460377`, re-ported by hand to
6.18/arm64. The 2026-08-17 rebase replaced it with vendor release
`2026_0123_5f7be68d` — a two-year jump — and folded the hand port into
`patches/aic8800/`. Git history has it if it is ever needed again.

## Modules (load order)

| Module | Role | Depends on |
|--------|------|------------|
| `aic8800_bsp`   | chip bring-up, SDIO glue, firmware download, H713 power/GPIO (`4021000.mmc`, PM1 `wlan_regon`, `mmc_detect_change`) | — |
| `aic8800_fdrv`  | fullmac WiFi driver (cfg80211) | `aic8800_bsp` |
| `aic8800_btlpm` | BT rfkill + low-power management (HCI data rides mainline `hci_uart` on `ttyS1`) | `aic8800_bsp` |

All three declare `MODULE_LICENSE("GPL")`.

## Firmware

Proprietary Aicsemi blobs with no open equivalent (see
`docs/wifi-failure-2026-08-17.md` for why an open one does not exist). **Not
committed** — pinned by SHA-256 in `firmware.sha256sums` and copied into the
rootfs at build time from `AIC8800_FW_SRC`.

Two things about firmware are easy to get wrong and both stop `wlan0` appearing:

1. **The path must match the driver's `CONFIG_AIC_FW_PATH`.** The rebase moved
   it to `/lib/firmware/aic8800_fw/SDIO/aic8800D80` (radxa's
   `fix-sdio-firmware-path.patch`). `AIC8800_FW_DEST` tracks it.
2. **This board needs the `_h_` variant.** The chip reports `is_chip_id_h` from
   register `0x40500000`, so the 2026 driver loads `fmacfw_8800d80_h_u02.bin`.
   The 2024 driver had no `_h_` list for D80 and silently used the non-`_h_`
   file, i.e. the board ran a mismatched firmware variant for its whole life
   before this. Both are pinned; `tools/rootfs/build.sh` asserts the `_h_` one.

## Build

`build/build.sh aic8800` builds all three against the pinned kernel and stages
the `.ko` to `build/out/modules/`. `build/build.sh all` includes it after the
kernel stage. `tools/rootfs/build.sh` installs the modules (into
`/lib/modules/$KREL/updates/aic8800/`, with a vermagic check) and the pinned
firmware, and adds `/etc/modules-load.d/aic8800.conf` for boot autoload.
