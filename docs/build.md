# Building the H713 firmware

The whole stack builds with **LLVM (clang / ld.lld)** — no aarch64 GCC needed.

**The fast path is the orchestrator:** `tools/build/build.sh [all|bl31|uboot|kernel|images]`
(board via `BOARD=ddr3|lpddr3`). It reads pinned versions from
`config/versions.env`, builds each stage from the `external/` submodules and
`patches/kernel/`, and drops artifacts in `build/out/`. The sections below
document the underlying recipes it runs (and the gotchas behind them).

`build/` holds generated output only — the scripts that produce it live in
`tools/build/`. The destination is resolved once in
[config/paths.sh](../config/paths.sh) and sourced by every script that writes or
reads build output; set `H713_BUILD_DIR` (absolute path) to build elsewhere.
**It needs pruning** — see [Build cache cleanup](#build-cache-cleanup), which is
not housekeeping advice but the difference between a 0.5 s and a 21 s
`git status`.

## Host prerequisites (Arch/CachyOS)

- `clang`, `lld`, `llvm` (llvm-* binutils)
- `dtc` (system, only as a fallback), `python-libfdt` (importable `libfdt`)
- **`swig`** — required. U-Boot builds its own dtc + pylibfdt, and pylibfdt
  needs swig. Without it the build fails at `scripts/dtc/pylibfdt`.
  `sudo pacman -S swig`
- Rootfs only: `mmdebstrap` (AUR), `apt`, `qemu-user-static-binfmt`,
  `e2fsprogs`, `kmod`, `android-tools`, `curl`, and `libarchive`. See
  [rootfs.md](rootfs.md); its QEMU registration is private and rootless.

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

Use `tools/build/uboot-build.sh <O-dir> <defconfig>`, or directly:

```
make -C external/u-boot O=<O> ARCH=arm HOSTCC=clang CC='clang -target aarch64-linux-gnu' \
  LD=ld.lld AR=llvm-ar NM=llvm-nm OBJCOPY=llvm-objcopy OBJDUMP=llvm-objdump \
  READELF=llvm-readelf STRIP=llvm-strip \
  KAFLAGS=-fintegrated-as \
  KCFLAGS='-fintegrated-as -Wno-error=deprecated-non-prototype -fno-stack-protector' \
  BL31=<path>/build/sun50i_h713/release/bl31.bin \
  hy200_qz713df_a1_defconfig            # then the same without the defconfig arg
```

**Recipe gotchas (each cost real time — do not drop):**
- **`-fintegrated-as`** (both KAFLAGS and KCFLAGS): without it clang shells out
  to the x86 `/usr/bin/as` for `.S` files, which fails with `unrecognized
  option '-EL'`.
- **No `DTC=` override, no `NO_PYTHON=1`.** With swig present, U-Boot builds its
  own dtc (which knows the `graph_child_address` check the system dtc lacks)
  and its own pylibfdt (binman needs it). The old `DTC=$O/scripts/dtc/dtc`
  recipe was for SPL-only and breaks the full image build.
- defconfigs: `hy200_qz713df_a1_defconfig` (DDR3 bench), `hy200_qz713_v2_defconfig`
  (LPDDR3 projector). Current images are about 845 KiB.

## 3. Kernel (arm64)

Carried as a **patch series on a pinned mainline tarball**, not a fork:
`tools/build/build.sh kernel` fetches `linux-$KERNEL_VERSION`, applies
`patches/kernel/series` (22 well0nez driver patches plus our arm64 board,
clock-transition, R-PWM clock, and voltage-scaling cpufreq patches) and the arm64 defconfig,
then builds `Image` with
`ARCH=arm64 LLVM=1`. See [../patches/kernel/README.md](../patches/kernel/README.md).

The series includes shared H713 arm64 hardware plus separate bench and
projector board DTS files, with `arm,armv8-timer` and a
`secure-bl31@40000000` reservation. The kernel stage emits `Image.gz`, both
DTBs, and a bench-only FIT with SHA-256 hashes (`arch=arm64`, load/entry
`0x48000000`).
Kernel preparation is keyed by a digest of the version, defconfig, series, and
patch contents, so editing the series cannot silently reuse a stale tree.

### Build cache cleanup

Each distinct digest is materialized as its own `build/linux-$KERNEL_VERSION-<digest>`
tree (~2 GiB once built), so editing the series, defconfig, or `versions.env`
leaves the previous tree behind rather than overwriting it. Only the newest
matches the current HEAD. Rerun `tools/build/build.sh kernel` — its make output
prints the tree path it uses
(`Entering directory build/linux-$KERNEL_VERSION-<digest>`), and it is fast
when that tree is warm — then `rm -rf` every other `build/linux-$KERNEL_VERSION-*`.

**A stale tree is dead weight, not a cache.** The tree name *is* the input
digest, so once the series changes, the old tree can never be reused — only
re-created. Nothing prunes them automatically.

**What happens if you skip this**, measured on 2026-09-12 after ~4 weeks of
iteration: 101 abandoned kernel trees, **208 GB**, **621,558 directories**.
`git status` took **21 s**, and git's fsmonitor daemon could not start at all —
it places one inotify watch per directory and does not skip ignored paths, so it
wanted ~644k watches against `fs.inotify.max_user_watches` = 524288 and aborted
the listener thread. Deleting every tree whose digest no longer matched took
`build/` to 7.3 GB, the worktree to 31k directories, and `git status` to
**0.5 s**. Prune with:

```
# every kernel tree except the one the current series builds
comm -23 <(ls -d build/linux-$KERNEL_VERSION-*/ | sort) \
         <(tools/build/build.sh kernel-tree | sed 's|$|/|')
```

Pruning also matters because the rootfs builder's kernel-tree auto-detect
requires **exactly one** built tree (see [rootfs.md](rootfs.md)); it aborts
otherwise — which, with 101 present, it had been doing.

## Local-only recovery tool

`local/0001-h713-emmc-recovery-tool-LOCAL-ONLY.patch` embeds the vendor boot0
blob. The entire `local/` directory is ignored and purged from repository
history; **never force-add or publish it**. Reapply into U-Boot with `git am`
only for hardware un-bricking.
