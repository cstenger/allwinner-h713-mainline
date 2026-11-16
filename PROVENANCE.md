# Provenance & licensing

This project integrates several upstream components and third-party work.
Respect the boundaries below — especially the redistribution ones.

## Components (submodules, our GitHub forks)

| Component | Upstream | License | Our changes |
|-----------|----------|---------|-------------|
| u-boot | Denx U-Boot | GPL-2.0+ | H713/HY200 SoC + board support (curated series) |
| arm-trusted-firmware | TF-A | BSD-3-Clause | `sun50i_h713` platform + keyed-wdog reset + PSCI cpu_on/suspend |
| sunxi-tools | linux-sunxi | GPL-2.0+ | H713 FEL support + fel_lib 16 KiB chunk fix |

Each fork carries a clean H713 commit series on top of a pinned upstream base,
intended to be upstreamable (H713/HY200 support) once validated.

## Kernel patches (`patches/kernel/`)

The bulk of the H713 driver support (CCU, pinctrl, MMC, USB PHY, PPU, LRADC,
board-mgr, cpu-comm, tvtop, decd, cedrus, …) originates from **well0nez**
(`local/allwinner-h713-linux`), GPL-2.0. These patches are carried here
**with attribution to well0nez**. Our own additions (arm64 DTS, arm64
defconfig, the `SUN20I_D1_R_CCU` arm64 Kconfig enablement) are marked as such
in the series.

The November 14 follow-ups **0191–0194 and 0196–0197** come from well0nez's
tree at `149f51d0df24c45b12674c81aab128b1fc8f5d4b` (their 0317, 0005a,
0143/0144, 0309 and 0316). Each records the pinned source in `Link:`;
the PIO fix omits a comment already corrected here. **0195** is Pengpeng
Hou's upstream HEVC count validation (`afbe4bc252d9`), backported through
well0nez's 0330 and regenerated for our 6.18.38 context with upstream
authorship and trailers preserved. See the
[integration record](docs/reviews/well0nez-2026-11-14/integration.md).

The subsequent CPU_COMM **0198** adapts well0nez's 0024d stock-msgbox/watchdog
IRQ correction. **0199** adapts the bank-ownership reasoning from their
0014b/0014c to our existing single-bank, sleepable threaded callback, adds
IRQ-only operation and observable IRQ/poll counters, and retains polling as
an explicit opt-out or registration fallback. Pinned source links are in
both patches; the threaded-handler implementation is marked as our work.

**0200** is our follow-up ownership/bounds fix after the DDR3 IRQ trial:
serialized packed semaphore claims, bounded reference translation, correct
20-slot/21-entry distinction, session-bound ACK completion and ACK-before-wake
RETURN handling. The [handoff investigation](docs/reviews/well0nez-2026-11-14/cpu-comm-handoff.md)
records source regressions and hardware results separately from attribution.

## VA-API shim patches (`patches/libva-v4l2-request/`)

[bootlin/libva-v4l2-request](https://github.com/bootlin/libva-v4l2-request),
**MIT**, carried as a two-patch series on the pinned head of its unmerged
**PR #38** rather than vendored — see that directory's README for the base
commit and why `master` is the wrong starting point.

## DO NOT REDISTRIBUTE

- **Vendor boot0 / eGON blob** and the U-Boot `H713_EMMC_RECOVERY` tool that
  embeds it (`board/sunxi/h713_recovery.c`, `h713_vendor_boot0.h`). This is
  proprietary Allwinner code — it stays under the ignored `local/` directory,
  is excluded from repository history and the upstreamable series, and must
  not be pushed to public forks.
- **eMMC backups, BROM dumps, captures** (`local/h713-lab`, ~84 GB) —
  contain proprietary firmware; never commit or share.

## Toolchain

Built with LLVM (clang / ld.lld) — no aarch64 GCC required. Verified host-tool
versions are recorded in `config/toolchain.md`.

Patch **0201** is our CPU_COMM send-ownership guard, derived from inspection
of the existing driver and local DDR3 firmware logging/timeout captures.
It preserves an outstanding peer-owned publication after missing CALL_ACK
and refuses reuse. No firmware code or proprietary captures are included.

Patch **0202** is our shared-spinlock ABI reconstruction from the pinned
local firmware's `tridspinlock.c` code and the quiet DDR3 failure context.
It is not copied from well0nez's tree. Only the GPL driver fix and a host
regression are published; firmware bytes and raw context stay local.

After developing and testing 0202 against our pinned firmware, comparison
with well0nez's pinned tree found matching independent gate/owner analysis
in [0259](https://github.com/well0nez/allwinner-h713-linux/blob/149f51d0df24c45b12674c81aab128b1fc8f5d4b/mainline/patches/kernel/0259-soc-sunxi-cpu_comm-the-software-spinlocks-as-the-vendor-and-the-firmware-run-them.patch).
Their [0261](https://github.com/well0nez/allwinner-h713-linux/blob/149f51d0df24c45b12674c81aab128b1fc8f5d4b/mainline/patches/kernel/0261-soc-sunxi-cpu_comm-the-thread-word-of-a-held-lock-must-not-read-as-free.patch)
also documents the reserved low-byte thread sentinel. These are relevant
prior analyses; 0202 was not copied from their implementation. Our original
pid-based unlock avoids their whole-word-255 rejection, but further protocol
review should consider a separately encoded ARM thread token.

Patch **0203** is our arm64 fatal-fault reporting diagnostic, motivated by
DDR3 CPU_COMM captures that stop after the first fault-address record.
It adds no protocol behavior and is not a corruption fix.

Patch **0206** adapts well0nez's
[0313](https://github.com/well0nez/allwinner-h713-linux/blob/149f51d0df24c45b12674c81aab128b1fc8f5d4b/mainline/patches/kernel/0313-mmc-sunxi-the-emmc-host-starts-a-read-block-only-when-the-fifo-has-room-for-it.patch)
eMMC read-block threshold implementation. Original authorship and HY310
measurements remain attributed to well0nez. Our adaptation introduces an
explicit H713-eMMC-only configuration flag, excludes zero-sized blocks and
adds source-derived host tests and a read-only DDR3 load comparison. It does
not import their separate 0312 error-recovery reset.
