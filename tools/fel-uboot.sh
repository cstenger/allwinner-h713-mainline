#!/usr/bin/env bash
# Start U-Boot proper over FEL on H713, in RAM only -- the "sunxi-fel uboot"
# that never worked here (docs/flash.md, "Known gap").
#
#   tools/fel-uboot.sh RESCUE_IMAGE [UBOOT_BIN] [BL31]
#
# RESCUE_IMAGE is an SPL built with CONFIG_H713_SPL_FEL_REENTER (U-Boot 0009):
# it trains DRAM, sets both FEL flags and warm-resets the core, and the first
# stage on eMMC sends the board back into FEL at EL3 with DRAM still trained.
# That needs a first stage that honours a flag: ours (0008, RTC GP7) or the
# stock boot0 (GP2). This script then clears both flags, writes BL31 and U-Boot
# proper, reads them back, and starts BL31 with reset64. Nothing touches eMMC.
#
# The board must be in a FRESH FEL session (button or "reboot fel"): only one
# SPL can run per session.
#
# TTY (default: the CP2102 by-id path, if present) gets keystrokes for a few
# seconds after the start, to stop autoboot at the prompt. TTY= disables it.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
F="$ROOT/external/sunxi-tools/sunxi-fel"
rescue=${1:?RESCUE_IMAGE}
uboot=${2:-$ROOT/build/uboot-lpddr3-felrescue/u-boot.bin}
bl31=${3:-$ROOT/build/out/bl31.bin}
tty=${TTY-/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0}

BL31_ADDR=0x40000000
UBOOT_ADDR=0x4a000000	# CONFIG_TEXT_BASE, BL31's PRELOADED_BL33_BASE
RTC_GP2=0x07090108
RTC_GP7=0x0709011c

say() { printf '[fel-uboot] %s\n' "$*"; }
die() { say "FAIL: $*"; exit 1; }
# lsusb -d exits 1 while the device is gone (mid re-enumeration): not an error.
fel_dev() { { lsusb -d 1f3a:efe8 || true; } | awk '{print $2 ":" $4}' | head -1; }

for f in "$rescue" "$uboot" "$bl31"; do [ -f "$f" ] || die "missing $f"; done
grep -aq 'warm reset to re-enter FEL at EL3' "$rescue" ||
  die "$rescue is not a FEL-rescue SPL (CONFIG_H713_SPL_FEL_REENTER)"

timeout 10 "$F" version >/dev/null || die "no FEL device answering"
if [ "${SKIP_SPL:-0}" = 1 ]; then
  # The rescue SPL already ran and FEL came back (e.g. an earlier run of this
  # script stopped after the re-entry); continue from the trained DRAM.
  now=$(fel_dev)
  say "SKIP_SPL=1: continuing in the re-entered FEL at $now"
else
  before=$(fel_dev)
  say "FEL at $before; running the rescue SPL (USB will drop, that is expected)"
  timeout 30 "$F" spl "$rescue" || true

  say "waiting for FEL to come back at EL3"
  for _ in $(seq 1 40); do
    now=$(fel_dev)
    if [ -n "$now" ] && [ "$now" != "$before" ] && timeout 5 "$F" version >/dev/null 2>&1; then
      break
    fi
    now=; sleep 0.5
  done
  [ -n "$now" ] || die "FEL did not re-enumerate (device was $before); power-cycle into FEL"
  say "FEL back at $now"
fi

"$F" writel "$RTC_GP7" 0
"$F" writel "$RTC_GP2" 0

# U-Boot proper picks its environment from the boot device recorded in the
# first stage's header at SPL_ADDR (0x104000). Without a valid "eGON.BT0"
# there it decides "FEL boot", finds no environment driver (ENV_IS_IN_MMC
# only) and env_init() fails before the console exists (seen 2026-11-18).
# Mark it an eMMC (MMC2) boot, as the bench rescue SPL does: the stored
# environment is only read, and a bad CRC falls back to the default one.
SPL_ADDR=0x104000
say "SRAM header at $SPL_ADDR before:"
"$F" hexdump "$SPL_ADDR" 0x30
"$F" writel $(( SPL_ADDR + 0x04 )) 0x4e4f4765	# "eGON"
"$F" writel $(( SPL_ADDR + 0x08 )) 0x3054422e	# ".BT0"
"$F" writel $(( SPL_ADDR + 0x18 )) 0		# fel_script_address
"$F" writel $(( SPL_ADDR + 0x28 )) 2		# boot_media = SUNXI_BOOTED_FROM_MMC2

tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
load() {	# addr file: write, then read back in <= 1 MiB pieces and compare
  local addr=$1 file=$2 size off n
  size=$(stat -c %s "$file")
  "$F" write "$addr" "$file"
  : > "$tmp/back"
  for ((off = 0; off < size; off += 1048576)); do
    n=$(( size - off < 1048576 ? size - off : 1048576 ))
    "$F" read $(( addr + off )) "$n" "$tmp/piece"
    cat "$tmp/piece" >> "$tmp/back"
  done
  cmp -s "$file" "$tmp/back" || die "read-back mismatch at $addr ($file): DRAM did not survive"
  say "$(basename "$file") at $addr verified ($size bytes)"
}
load "$BL31_ADDR" "$bl31"
load "$UBOOT_ADDR" "$uboot"

say "starting BL31 at $BL31_ADDR (reset64)"
"$F" reset64 "$BL31_ADDR" || true

if [ -n "$tty" ] && [ -e "$tty" ]; then
  say "sending keystrokes on $tty to stop autoboot"
  for _ in $(seq 1 60); do printf '\n' > "$tty"; sleep 0.1; done
fi
say "done; check the console for the U-Boot prompt"
