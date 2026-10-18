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
