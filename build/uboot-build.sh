#!/bin/bash
# H713 u-boot build (clang/lld). Usage: ubmake.sh <O-dir> <defconfig> [target...]
# Needs: swig (in-tree dtc+pylibfdt). -fintegrated-as = use clang's assembler.
O="$1"; DEF="$2"; shift 2
BL31=~/Projects/arm-trusted-firmware/build/sun50i_h713/release/bl31.bin
F=(ARCH=arm HOSTCC=clang CC='clang -target aarch64-linux-gnu'
  LD=ld.lld AR=llvm-ar NM=llvm-nm OBJCOPY=llvm-objcopy OBJDUMP=llvm-objdump
  READELF=llvm-readelf STRIP=llvm-strip
  KAFLAGS=-fintegrated-as
  KCFLAGS='-fintegrated-as -Wno-error=deprecated-non-prototype -fno-stack-protector'
  BL31="$BL31")
make -C ~/Projects/u-boot O="$O" "${F[@]}" "$DEF" >/dev/null 2>&1 || { echo DEFCONFIG_FAIL; exit 1; }
make -C ~/Projects/u-boot O="$O" "${F[@]}" -j"$(nproc)" "$@"
