# H713 mainline bring-up

Mainline firmware and Linux for the **Allwinner H713 (sun50iw12)** SoC — a
fully open boot chain (U-Boot SPL → TF-A BL31 → U-Boot → Linux) with a
64-bit Debian userland, replacing the vendor Android stack.

> **Status (2026-07-17):** arm64 Debian 13 boots from eMMC to a root login,
> 4-core SMP, HS400 eMMC. 32-bit Linux also boots (single-core). See
> [docs/status.md](docs/status.md).

## Hardware

Two physically different H713 boards exist — **know which one you have**:

| Board | Silkscreen | DRAM | Notes |
|-------|-----------|------|-------|
| **Bench** | HY200 | **DDR3** (Samsung K4B2G, 1 GiB) | All FEL/bring-up runs on this one |
| **Projector** | HY310 | **LPDDR3** (1 GiB) | Inside a projector; do not risk it |

Feeding the wrong DRAM parameters trains "OK" but reads hang. Always name the
board a test ran on. Neither board has an SD slot — boot media is **eMMC or
FEL only**. There is a hardware **FEL button** (recovery vector).

## Boot chain

```
BROM → U-Boot SPL (DRAM init) → TF-A BL31 (EL3, @0x40000000 in DRAM)
     → U-Boot proper (AArch64 EL2) → FIT (bootm):
         arch=arm64  → EL1 AArch64  (native; SMP works, 4 cores)
         arch=arm    → EL1 AArch32  (via el2_to_aarch32; single-core)
```

## Layout

- `external/` — the three firmware components as git submodules pinned to our
  GitHub forks (curated H713 commit series on top of upstream):
  `external/u-boot/`, `external/arm-trusted-firmware/`, `external/sunxi-tools/`.
  Fetch them with `git submodule update --init`.
- `patches/kernel/` — kernel patch series (well0nez H713 drivers + our arm64
  additions), applied to a pinned mainline tag. See
  [patches/kernel/README.md](patches/kernel/README.md).
- `tools/` — hardware test/flash tooling (`serial/` console + FIT loaders,
  `rootfs/` Debian build helpers).
- `docs/` — project documentation (build, flash, status, gotchas). Docs live
  here, **not** in the submodules.
- `build/` — reproducible build orchestrator (TODO).
- `config/` — defconfigs and pinned toolchain/version manifest (TODO).

## Quick start

TODO: `build/` orchestrator (clean checkout → SPL+ATF+U-Boot+kernel → images).
Until then see [docs/build.md](docs/build.md) and [docs/flash.md](docs/flash.md).

## Gotchas (read before touching hardware)

- **Transfers:** the USB-CDC gadget (`ttyACM*`, resolve by USB VID `1f3a`) is
  ~15× faster than the UART for bulk loads; the hardwired UART (`ttyUSB0`) is
  the only console that survives kernel handoffs but is **intermittently flaky**
  — use it only when you must watch a boot. Best: stash images on eMMC.
- **fastboot/ums vs console:** the ACM console holds the USB device controller;
  `fastboot usb 0` fails `g_dnl -22` until you release it. Issue
  `setenv stdout serial;setenv stderr serial;setenv stdin serial;fastboot usb 0`
  as **one line over CDC** (U-Boot buffers the whole line before releasing the
  console). The change is RAM-only — a `reset` restores the ACM console.
- **fastboot buffer is 32 MiB** → large images must be Android-sparse
  (`img2simg`); the host tool chunks them.

See [docs/status.md](docs/status.md) for what works and what's next.
