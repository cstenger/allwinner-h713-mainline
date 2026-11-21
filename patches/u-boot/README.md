# H713 U-Boot build series

The normal build applies `series` to `UBOOT_SOURCE_COMMIT` from
`config/versions.env` (validated base `320a17f71d41...`). Source preparation
exports that commit from the submodule without modifying its checkout, applies
the patches, copies the prepared kernel's H713 DT/bindings and generates the
matching CCU table. Both the orchestrator and quick helper use this tree.

| Patch | Purpose |
| --- | --- |
| `0000-h713-shared-dt-panel-regulator-prerequisites.patch` | Tested DT/clock/PHY integration, DM panel supply/reset helpers, DDR3 lamp/fan policy |
| `0001-h713-establish-initial-panel-power-state.patch` | Verified reset/supply-off control state and explicit minimum 3 s hold before logo replay |
| `0003-env-mmc-preserve-configured-offset-width.patch` | Preserve configured 64-bit fallback and report the singular-load byte offset; cold/one ordinary warm boot verified, paired environment migration required |
| `0004-h713-single-display-firmware-launch.patch` | `h713_disp auto <id> logo comm-trace`: one firmware load and release instead of two; installed 2026-11-06, kernel starts 1.10 s earlier |
| `0005-h713-early-panel-off-interval.patch` | `h713_disp panel-off`: enter the verified panel off state before the FIT/blob loads; the logo step re-verifies it and waits only the rest of the same 3 s; installed 2026-11-09, kernel starts 0.80 s earlier |
| `0006-h713-comm-trace-markers-avoid-k0-k1.patch` | Comm-trace markers use t8/t9 instead of k0/k1 (the firmware's interrupt exit clobbers k0/k1, so a marker interrupted mid-sequence faulted and the firmware's dump recursion overwrote ARM DRAM); apply loop refuses k0/k1 in caves. Built 2026-11-15, **not yet installed** |
| `0007-h713-host-tools-without-openssl.patch` | Both H713 defconfigs turn off `TOOLS_LIBCRYPTO`/`TOOLS_KWBIMAGE`: mkimage no longer links host OpenSSL (OpenSSL 4 removed the ENGINE API it used). Host tools only; SPL+proper byte-identical to the libcrypto build (2026-11-17) |
| `0008-h713-spl-enter-fel-on-rtc-marker.patch` | `reboot fel` / `reboot efex` (RTC GP7 = `0x0fe1b007`, kernel 0029): the SPL's AArch32 boot0 hook clears the marker and enters the BROM's FEL loop at `0x20`, still at EL3, like stock boot0. FEL-tested on the projector 2026-11-18: marker set → SPL re-enters FEL (USB re-enumerates, GP7 cleared, no UART output); a second SPL in that session then trains DRAM, so the FEL is EL3. The Linux `reboot fel` → warm-reset path is **not yet tested** (needs our stack installed) |
| `0009-h713-spl-fel-reenter-at-el3.patch` | `CONFIG_H713_SPL_FEL_REENTER` (default n, FEL rescue builds only): after DRAM init, set both FEL flags and warm-reset the core into AArch32, so the first stage on eMMC sends the board back into FEL at **EL3** with DRAM trained. `tools/fel-uboot.sh` then loads BL31 + proper and starts them with `reset64`. Projector 2026-11-19: **U-Boot proper reaches the prompt from RAM over FEL** (first time on H713). The BROM zeroes the SPL header at 0x104000 on the way into FEL, so the script writes `eGON.BT0` + boot_media MMC2 before `reset64` (else `env_init()` fails pre-console). Never `saveenv` from it on V2 (env offset 0x400000) |
| `0010-h713-spl-restore-own-boot0-over-fel.patch` | `CONFIG_H713_SPL_RESTORE_BOOT0` (default n, recovery builds only): a FEL-started SPL writes the board's **own stock boot0** to LBA 16..79, reads it back and compares, and halts. It runs from the FEL load path, so unlike the bench `H713_SPL_FORCE_MMC` hook it needs nothing of ours on the eMMC. Payload generated at build time from the board's capture by `tools/build-v2-restore-spl.sh` (into the build dir, never the tree). Two DRAM-type guards, both checked 2026-11-19: the tool refuses a boot0 whose type/clock differ from the defconfig, and the SPL `#error`s on a mismatch. V2 build: `build/out/h713-v2-restore-spl.bin`, payload sha256 `f8ac16e4…`. **Proven on the projector 2026-11-19:** `before: already identical`, `RESTORED-OK`, then stock boot0 → Android `boot_completed=1` |
| `0011-h713-shared-board-config-base-v2-layout.patch` | Phase 0.2 de-drift. `configs/hy200_h713.config` holds everything the H713 boards share; `hy200_qz713df_a1_defconfig` and `hy200_qz713_v2_defconfig` `#include` it and add only the DT, DRAM words and DRAM type plus board-specific options. **A1's resolved `.config` is identical before and after** (2026-11-19). V2 gains the bench layout: environment at `0x93d80000` (was `0x400000`), proper at LBA `0x49ac00` (both in the GPT partition `empty`, all zeros on both boards), vendor chainload, the fastboot/bootloader-hold PREBOOT handshake, and poweroff. V2 deliberately keeps **no** `H713_MIPS_BOOT` and no `h713_disp` until Phase 4's display step. Note: a defconfig comment line starting `# include` is read by cpp as a directive |
| `0012-h713-v2-ab-boot-rauc.patch` | V2 only: A/B through Standard Boot's own `bootmeth_rauc` (slot A = `boot_a` p5 + `root_a` p9, slot B = `boot_b` p6 + `root_b` p16, 3 tries, refill all when none are left), `BOOTSTD_FULL`, redundant environment at `0x93d90000`. Declared, not scripted: the V2 `-u-boot.dtsi` bootstd node has `bootdev-order = "mmc1"` and a single `rauc` bootmeth node, and the boot command is Standard Boot's default `bootflow scan -lb`. V2 drops the deprecated `DISTRO_DEFAULTS`; `sunxi-common.h` now includes the `distro_bootcmd` environment only when `DISTRO_DEFAULTS` is set (its `boot_targets` would override the devicetree order). V2's PREBOOT drops `usb start` (no USB host in U-Boot here). A1's default environment is unchanged (checked 2026-11-20). A/B tested on the projector 2026-11-20; Linux side is Debian's RAUC (see `docs/lpddr3-bringup-plan.md`) |
| `0013-h713-v2-saved-bootdelay-cannot-stop-autoboot.patch` | V2 only: PREBOOT starts with `env default -f bootdelay`, so a `bootdelay=-1` left by `reboot bootloader` and then saved (by `saveenv` at the prompt, or by `bootmeth_rauc`'s save on every boot) cannot hold every later boot at the prompt. bootdelay is a build-time setting on V2. Tested on the projector 2026-11-20: `-1` saved at the held prompt, and the next boot still counted down 2 s and booted |

**Paired environment migration is required for the unmigrated split layout.**
The prior diagnostic image read saved environment at unintended LBA `0x32ec00`;
this correction uses intended LBA `0x49ec00`, which was zero-filled in the
audit. Do not install the new proper alone or flash the combined SPL image.
Use the reviewed migration with fresh device/storage/boot pins; the earlier
synthetic fixture package is not a deployment package.

The paired [migration was installed and storage-verified October 30](../../docs/hdmi-evidence/2026-10-30-uboot-migration-install/README.md).
The [October 31 cold boot](../../docs/hdmi-evidence/2026-10-31-uboot-first-boot/README.md)
confirms the expected new proper, intended-address environment load and Linux
startup. One [ordinary warm boot also passes](../../docs/hdmi-evidence/2026-10-31-uboot-warm-validation/README.md),
with normal desktop return confirmed. Repeated lifecycle, audio and save-path
qualification remain pending.

The focused `0001` patch remains incremental to `0000` plus the shared kernel
DT. Its resulting `h713_mips.c` SHA-256 is
`3c44fc5af23eaa55a698fbc1e5e509cb23cff76382c4d5425b1d178cc829b450`, identical
to the hardware-tested source. The original pre-fix snapshot hash is
`ea1b0f259ead56c1f60da1f37ebc5a443a4dc51cdc3bf95dd5a2d634d5ef9041`.
Do not apply patches again inside an already prepared source tree.

```sh
JOBS=8 tools/build/build.sh uboot
UBOOT_TREE=$(tools/build/build.sh uboot-tree)
python3 patches/u-boot/tests/test-panel-initial-state.py \
  "$UBOOT_TREE/arch/arm/mach-sunxi/h713_mips.c" \
  build/panel-initial-state-review/normal-tests
```

The source cache digest includes the commit, ordered patch list and contents,
preparation/sync/generator tools, and actual shared kernel inputs. Builds save
source/config/BL31/image provenance to `build/out/u-boot-<board>.inputs`.
The prepared DDR3 configuration matches the validated image; LPDDR3 compiles
but has no hardware validation here. No build command installs firmware.

Hardware validation passed three independent cold/first-warm pairs, one extra
warm boot, sampled live 720p video, bounded stereo digital audio at three input
rates, one clean cold-start speaker listening test, and one immediate SysRq
reset with HDMI live. Three seconds is conservative, not a measured rail
minimum; full-rate video, long-term reliability and autonomous watchdog expiry
are unproven. Earlier transient audio silence remains unexplained.

See [the build/results/rollback runbook](../../docs/uboot-panel-initial-state.md)
and [raw trial evidence](../../docs/hdmi-evidence/2026-10-18-panel-initial-state-trial/README.md).
The installed trial proper remains unchanged by this source integration.

### 0006 checks

`tests/t8t9-liveness.py` proves t8/t9 are dead at all 61 comm-trace hook
sites in the pinned `display.bin` (SHA-256 `4380f1b3…`). It reads the patch
table, follows both branch paths, and treats calls and `jr $ra` as kills. It
reports 18, 35 and 38 unsafe sites when watching v0, a0 and s0, so it can
fail. `tests/test-comm-trace-no-kregs.py OLD NEW` checks that exactly the 155
cave words changed and only k0→t8 / k1→t9, that no k0/k1 is left, and that
relocation stays at 61/80. It fails on the pre-0006 table. Production uses
only the comm-trace table (`trace` and `stability` are mutually exclusive
with it), so the remaining k0 caves in the bench-only `mips-trace` and
`mips-stability` tables are unchanged.

```sh
python3 patches/u-boot/tests/t8t9-liveness.py local/mips-display/board-b-mips/display.bin \
  "$(tools/build/build.sh uboot-tree)/arch/arm/mach-sunxi/h713_mips.c"
```

