# Building the H713 firmware

The whole stack builds with **LLVM (clang / ld.lld)** — no aarch64 GCC needed.

**The fast path is the orchestrator:** `build/build.sh [all|bl31|uboot|kernel|images]`
(board via `BOARD=ddr3|lpddr3`). It reads pinned versions from
`config/versions.env`, builds each stage from the `external/` submodules and
`patches/kernel/`, and drops artifacts in `build/out/`. The sections below
document the underlying recipes it runs (and the gotchas behind them).

## Host prerequisites (Arch/CachyOS)

- `clang`, `lld`, `llvm` (llvm-* binutils)
- `dtc` (system, only as a fallback), `python-libfdt` (importable `libfdt`)
- **`swig`** — required. U-Boot builds its own dtc + pylibfdt, and pylibfdt
  needs swig. Without it the build fails at `scripts/dtc/pylibfdt`.
  `sudo pacman -S swig`
- `mmdebstrap` (AUR) — only for the arm64 rootfs.

## 1. TF-A BL31 (build first — U-Boot embeds it)

```
cd external/arm-trusted-firmware   # submodule, branch sun50i-h713
make -j PLAT=sun50i_h713 DEBUG=0 BL31_IN_DRAM=1 \
  CC=clang LD=ld.lld AR=llvm-ar OC=llvm-objcopy OD=llvm-objdump \
  NM=llvm-nm READELF=llvm-readelf \
  CFLAGS='-Wno-error=deprecated-non-prototype -fno-stack-protector' bl31
# -> build/sun50i_h713/release/bl31.bin  (~45 KiB)
```

## 2. U-Boot (SPL + BL31 + proper -> u-boot-sunxi-with-spl.bin)

Use `build/uboot-build.sh <O-dir> <defconfig>`, or directly:

```
make -C external/u-boot O=<O> ARCH=arm HOSTCC=clang CC='clang -target aarch64-linux-gnu' \
  LD=ld.lld AR=llvm-ar NM=llvm-nm OBJCOPY=llvm-objcopy OBJDUMP=llvm-objdump \
  READELF=llvm-readelf STRIP=llvm-strip \
  KAFLAGS=-fintegrated-as \
  KCFLAGS='-fintegrated-as -Wno-error=deprecated-non-prototype -fno-stack-protector' \
  BL31=<path>/build/sun50i_h713/release/bl31.bin \
  hy200_h713_ddr3_defconfig            # then the same without the defconfig arg
```

**Recipe gotchas (each cost real time — do not drop):**
- **`-fintegrated-as`** (both KAFLAGS and KCFLAGS): without it clang shells out
  to the x86 `/usr/bin/as` for `.S` files, which fails with `unrecognized
  option '-EL'`.
- **No `DTC=` override, no `NO_PYTHON=1`.** With swig present, U-Boot builds its
  own dtc (which knows the `graph_child_address` check the system dtc lacks)
  and its own pylibfdt (binman needs it). The old `DTC=$O/scripts/dtc/dtc`
  recipe was for SPL-only and breaks the full image build.
- defconfigs: `hy200_h713_ddr3_defconfig` (DDR3 bench), `hy310_h713_defconfig`
  (LPDDR3 projector). Working image is ~844377 bytes.

## 3. Kernel (arm64)

Carried as a **patch series on a pinned mainline tarball**, not a fork:
`build/build.sh kernel` fetches `linux-$KERNEL_VERSION`, applies
`patches/kernel/series` (the 22 well0nez drivers) plus our arm64 defconfig and
the `SUN20I_D1_R_CCU` `|| ARM64` Kconfig enable, then builds `Image` with
`ARCH=arm64 LLVM=1`. See [../patches/kernel/README.md](../patches/kernel/README.md).

**Known gap:** the arm64 board **DTS** (`sun50i-h713-hy310` with
`arm,armv8-timer` and a `secure-bl31@40000000 reg=<0x40000000 0x100000> no-map`
reservation) is not yet in the series, so the kernel stage builds a bootable
`Image` but not a DTB / FIT. Boot is via FIT `arch=arm64`, Image at load/entry
`0x48000000`. Landing the DTS is the first task of the 6.18.38 rebase —
[kernel-bump.md](kernel-bump.md).

## Local-only recovery tool

`local/0001-h713-emmc-recovery-tool-LOCAL-ONLY.patch` embeds the vendor boot0
blob — **never commit or push it**. Reapply into u-boot with `git am` only for
hardware un-bricking.
