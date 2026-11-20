#!/usr/bin/env bash
# One DRAM-init check over FEL, for counting cold boots (Phase 2 of
# docs/lpddr3-bringup-plan.md). RAM only; nothing touches eMMC.
#
#   tools/fel-dram-check.sh IMAGE [LABEL]
#
# IMAGE is a u-boot-sunxi-with-spl image for the board. The board must be in a
# FRESH FEL session (one SPL per session). The script:
#   1. starts its own UART logger (a cold boot unplugs the adapter, which
#      kills a running one) into local/recovery/fel-dram-check/LABEL.log,
#   2. runs the SPL, which trains DRAM and returns to FEL,
#   3. requires "DRAM: <DRAM_MIB> MiB" on the console (DRAM_MIB, default 1024),
#   4. writes a 32 MiB random pattern at 0x42000000 and at 0x7c000000, reads
#      both back in 1 MiB pieces (larger FEL reads wedge libusb), compares.
# Prints PASS or FAIL and exits 0 or 1.
set -uo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
F="$ROOT/external/sunxi-tools/sunxi-fel"
img=${1:?IMAGE}; label=${2:-$(date +%Y%m%d-%H%M%S)}
want_mib=${DRAM_MIB:-1024}
tty=${TTY:-/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0}
dir="$ROOT/local/recovery/fel-dram-check"; mkdir -p "$dir"
log="$dir/$label.log"
say() { printf '[dram-check %s] %s\n' "$label" "$*"; }
fail() { say "FAIL: $*"; exit 1; }

[ -f "$img" ] || fail "missing $img"
timeout 10 "$F" version >/dev/null || fail "no FEL device"
[ -e "$tty" ] || fail "no UART at $tty"

python3 "$ROOT/tools/serial/soak-capture.py" --port "$tty" --out "$log" \
	--minutes 3 --grace 5 --quiet & logger=$!
tmp=$(mktemp -d); trap 'kill $logger 2>/dev/null; rm -rf "$tmp"' EXIT
sleep 2
n0=$(stat -c %s "$log" 2>/dev/null || echo 0)

say "SPL: $(basename "$img") ($(sha256sum "$img" | cut -c1-12))"
timeout 30 "$F" spl "$img" || fail "sunxi-fel spl failed"
for _ in $(seq 1 20); do
	tail -c +"$((n0 + 1))" "$log" 2>/dev/null | grep -aq 'DRAM:' && break; sleep 0.5
done
dram=$(tail -c +"$((n0 + 1))" "$log" | tr '\r' '\n' | grep -a -m1 -o 'DRAM: .*' | tr -d '\r')
say "console: ${dram:-<no DRAM line>}"
[ "$dram" = "DRAM: $want_mib MiB" ] || fail "expected 'DRAM: $want_mib MiB'"

head -c 33554432 /dev/urandom > "$tmp/pat"
for addr in 0x42000000 0x7c000000; do
	"$F" write "$addr" "$tmp/pat" || fail "write at $addr"
	: > "$tmp/back"
	for ((off = 0; off < 33554432; off += 1048576)); do
		"$F" read $((addr + off)) 1048576 "$tmp/piece" || fail "read at $addr+$off"
		cat "$tmp/piece" >> "$tmp/back"
	done
	cmp -s "$tmp/pat" "$tmp/back" || fail "32 MiB pattern at $addr read back DIFFERENT"
	say "32 MiB random pattern at $addr read back identical"
done
say "PASS: DRAM trained ($dram), 64 MiB of pattern verified; log $log"
