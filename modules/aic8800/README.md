# AIC8800D80 WiFi + BT driver (out-of-tree)

Out-of-tree kernel modules for the **AIC8800D80** combo chip fitted on the HY200
boards: **WiFi over SDIO** (`mmc1@0x04021000`) and **Bluetooth over UART HCI**
(`uart1@2500400`). This is the correct-transport **SDIO** driver, not the USB
dongle variant.

## Modules (load order)

| Module | Role | Depends on |
|--------|------|------------|
| `aic8800_bsp`   | chip bring-up, SDIO glue, firmware download, H713 power/GPIO (`4021000.mmc`, PM1 `wlan_regon`, `mmc_detect_change`) | — |
| `aic8800_fdrv`  | fullmac WiFi driver (cfg80211/mac80211) | `aic8800_bsp` |
| `aic8800_btlpm` | BT rfkill + low-power management (HCI data rides mainline `hci_uart` on `ttyS1`) | `aic8800_bsp` |

All three declare `MODULE_LICENSE("GPL")`.

## Provenance

Source is the GPL SDIO driver carried in `local/allwinner-h713-linux/drivers/
wifi/` (well0nez H713 port of the Aicsemi/Radxa V5 driver). A prior effort took
it to **Linux 6.16.7 / ARM32** (build-only — see that tree's `PORT_REPORT.md`).
Copied here **source-only** (no firmware, no build artifacts) and re-ported to
the project's pinned **6.18.38 / arm64 / LLVM** kernel.

### 6.16 → 6.18 port delta (this tree)

cfg80211 gained multi-radio / per-link parameters; five call sites updated to the
6.18 signatures:

- `rwnx_main.c` — `set_wiphy_params`, `set_tx_power`, `get_tx_power` ops gained an
  `int radio_idx` argument.
- `rwnx_rx.c` — `cfg80211_rx_spurious_frame` / `cfg80211_rx_unexpected_4addr_frame`
  gained an `int link_id` argument (passed `-1` = not applicable).

The 6.16-era fixes (timer API, `MODULE_IMPORT_NS`, `set_monitor_channel`) were
already present from the earlier port.

`aic_bsp_driver.c` — guarded the `#include "aicwf_firmware_array.h"` with
`#ifdef CONFIG_FIRMWARE_ARRAY` to match its only (already-guarded) caller, so the
firmware-as-C-array files (a proprietary blob) are not needed to build and are
kept out of the tree. See "Firmware" below.

## Build

Orchestrated: `build/build.sh aic8800` builds all three against the pinned kernel
tree and stages the `.ko` to `build/out/modules/`. `build/build.sh all` includes
it after the kernel stage. `tools/rootfs/build.sh` then installs the modules
(into `/lib/modules/$KREL/updates/aic8800/`) and the pinned firmware into the
rootfs, and adds `/etc/modules-load.d/aic8800.conf` for boot autoload.

Manual equivalent — same `ARCH=arm64 LLVM=1` toolchain as the kernel, `bsp`
first, then `fdrv`/`btlpm` with its `Module.symvers`:

```sh
KDIR=$(ls -d "$PWD"/../../build/linux-6.18.38-*/ | head -1)
make -C "$KDIR" M="$PWD/aic8800_bsp"  ARCH=arm64 LLVM=1 CONFIG_PLATFORM_MAINLINE_SUNXI=y modules
make -C "$KDIR" M="$PWD/aic8800_fdrv" ARCH=arm64 LLVM=1 CONFIG_PLATFORM_MAINLINE_SUNXI=y \
     KBUILD_EXTRA_SYMBOLS="$PWD/aic8800_bsp/Module.symvers" modules
make -C "$KDIR" M="$PWD/aic8800_btlpm" ARCH=arm64 LLVM=1 CONFIG_PLATFORM_MAINLINE_SUNXI=y \
     KBUILD_EXTRA_SYMBOLS="$PWD/aic8800_bsp/Module.symvers" modules
```

`CONFIG_PLATFORM_MAINLINE_SUNXI=y` selects the H713 platform glue.

## Firmware (pinned, NOT committed)

The chip needs proprietary Aicsemi firmware blobs — there is no open firmware for
the AIC8800D80. The source of record is `local/allwinner-h713-linux/drivers/wifi/
firmware/aic8800_sdio/aic8800D80/` (local-only). It is **pinned by SHA-256** in
[`firmware.sha256sums`](firmware.sha256sums) and referenced from
`config/versions.env` (`AIC8800_FW_*`). `tools/rootfs/build.sh` verifies the
blobs against the manifest and installs them into the rootfs at
`AIC8800_FW_DEST` (`/usr/lib/firmware/aic8800_sdio/aic8800`, the driver's
compiled `CONFIG_AIC_FW_PATH`). The blobs themselves are never committed.

If the driver's `request_firmware()` fallback path is needed at bring-up instead
of the explicit `aic_fw_path`, set the `aic_fw_path` module parameter or add
symlinks — the install layout is the compiled default.

## Known runtime items (verify on hardware)

- **SDIO speed — reconciled to 25 MHz.** The DTS `mmc1` node now uses
  `max-frequency = <25000000>` (was 50 MHz) because the V1 sunxi-mmc glue hits
  CMD53 DMA errors on large transfers at 50 MHz. Revisit if the V5 `aicsdio.c`
  SDIO-stability hunks are later imported.
- **Bluetooth** is on UART1 (`ttyS1`), H4, 1.5 Mbaud. Attach with **`noflow`**,
  not `flow`: mainline's dw-apb-uart RTS/CTS handshake blocks the controller
  (HCI command timeout `-110`), whereas `hciattach /dev/ttyS1 any 1500000 noflow`
  brings up `hci0` (HCI/LMP 5.4, BD = WiFi MAC + 1). `hciattach` returns 0 even
  when the controller is mute, so verify with `hciconfig hci0 up`. The rootfs
  ships `/usr/local/sbin/h713-bt-attach` + `h713-bt-attach.service` to do this
  (with retry) automatically on boot. Hardware-verified: bluez discovers BLE
  devices over the air.
