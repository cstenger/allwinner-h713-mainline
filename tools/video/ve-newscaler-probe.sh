#!/usr/bin/env bash
# Probe the VE's arbitrary-ratio ("new scaler") path. RUNS ON THE HOST.
#
# The power-of-two path is settled (VE_H264_SDROT_CTRL[9:8]/[11:10]; see
# docs/reference/ve-scaledown-2026-09-11/RESULT.md). This probes the second,
# richer path that H264ConfigNewScaler drives, which computes its ratio with a
# floating-point divide and a 12-bit fixed-point conversion -- so it is not
# restricted to powers of two, and it is the only candidate for a true
# 1920x1080 -> 1280x720.
#
# Disassembly (libawh264.so, .text Addr 0x7558 vs Off 0x6558, so
# file_offset = vaddr - 0x1000 -- getting this skew wrong reads a bitstream
# reader instead of the scaler) says the new scaler writes:
#
#   top-level 0xcc        { size_b << 16, size_a }   two 16-bit fields
#   top-level 0xe8[27:0]  SDRT chroma buffer length  (mainline names this)
#   top-level 0xe8[31:30] secondary format table
#   top-level 0xec[2:0]   secondary format
#   engine    0x244/0x248 output addresses
#   engine    0x220 bit 9 cleared with `bic r1, r1, #0x200`
#
# 0xcc is unnamed in mainline and sits immediately after
# VE_PRIMARY_FB_LINE_STRIDE (0xc8), which is the shape a SECONDARY geometry
# register would have. It reads 0 while the power-of-two path produces correct
# output, so the hardware derives a default -- the question this script asks is
# whether writing it overrides that.
#
# Each case decodes, dumps the secondary buffer, and reports the extent of what
# was written. Extent is the measure, not a byte-difference count: real video
# contains bytes equal to the 0xa5 poison, so counts understate.
#
# Headless. No display, no MIPS, no operator.
#
#   usage: tools/video/ve-newscaler-probe.sh
set -euo pipefail

BOARD=${BOARD:-192.168.4.1}
SSH="ssh -o ConnectTimeout=5 root@$BOARD"
CLIP=${CLIP:-/root/leota-1080p.mp4}
FRAMES=${FRAMES:-30}
SD_W=1920
SD_H=2176
TOTAL=$(( SD_W * SD_H * 3 / 2 ))

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
OUT=${OUT:-$ROOT/local/ve-newscaler-$(date +%Y%m%d-%H%M%S)}
mkdir -p "$OUT"

log() { printf '\n\033[1;34m==>\033[0m \033[1m%s\033[0m\n' "$*"; }
note(){ printf '    \033[33m%s\033[0m\n' "$*"; }

$SSH '[ -e /sys/module/sunxi_cedrus/parameters/sd_poke ]' || {
	echo "error: running sunxi_cedrus has no sd_poke parameter" >&2; exit 1; }
$SSH 'pgrep -x ffmpeg >/dev/null 2>&1' && {
	echo "error: an ffmpeg is already running on the board" >&2; exit 1; }

set_param() {
	$SSH "printf '%s' '$2' > /sys/module/sunxi_cedrus/parameters/$1"
}

disarm() {
	$SSH "echo 0 > /sys/module/sunxi_cedrus/parameters/sd_w;
	      echo 0 > /sys/module/sunxi_cedrus/parameters/sd_h;
	      echo 0 > /sys/module/sunxi_cedrus/parameters/sd_ctrl;
	      echo 0 > /sys/module/sunxi_cedrus/parameters/sd_fmt;
	      printf '' > /sys/module/sunxi_cedrus/parameters/sd_poke" 2>/dev/null || true
}
trap disarm EXIT

set_param sd_w "$SD_W"
set_param sd_h "$SD_H"
set_param sd_fmt 1
set_param sd_stage 1
set_param sd_shift 0

$SSH "head -c $TOTAL /dev/zero | tr '\\000' '\\245' > /tmp/sd-poison.bin"

SUMMARY=$OUT/SUMMARY.txt
: > "$SUMMARY"

# name | sd_ctrl | poke list
CASES=(
  "baseline-0x500|0x500|"
  "cc-matches-960x544|0x500|0xcc=0x022003c0"
  "cc-asks-1280x720|0x500|0xcc=0x02d00500"
  "cc-swapped-1280x720|0x500|0xcc=0x050002d0"
  "cc-only-no-sdrot|0x0|0xcc=0x02d00500"
  "cc-1280x720-ctrl-h-only|0x100|0xcc=0x02d00500"
  "ctrl220-bit9-set|0x500|0x220=0x207"
  "ctrl220-bit9-clear|0x500|0x220=0x7"
)

for c in "${CASES[@]}"; do
	IFS='|' read -r name ctrl poke <<< "$c"
	log "$name   sd_ctrl=$ctrl   poke='${poke:-none}'"

	set_param sd_poke "$poke"
	set_param sd_ctrl "$ctrl"
	$SSH 'dmesg -C' >/dev/null 2>&1 || true

	frames=$($SSH "export LIBVA_DRIVER_NAME=v4l2_request; \
	    ffmpeg -hide_banner -loglevel error -stats -hwaccel vaapi \
	      -hwaccel_output_format vaapi -i '$CLIP' -frames:v $FRAMES -f null - 2>&1 \
	    | grep -o 'frame=[ ]*[0-9]*' | tail -1 | tr -dc '0-9'" || true)
	frames=${frames:-0}

	$SSH "dmesg | grep 'sd:'" > "$OUT/regs-$name.txt" 2>/dev/null || true

	# Extent of the write, computed on the board.
	read -r first last < <($SSH "
	    dd if=/sys/kernel/debug/cedrus_sd_buf of=/tmp/sd.bin bs=1M 2>/dev/null
	    cmp -l /tmp/sd.bin /tmp/sd-poison.bin 2>/dev/null \
	      | awk 'NR==1{f=\$1} {l=\$1} END{if(NR==0) print \"none none\"; else print f, l}'")

	if [ "$first" = "none" ]; then
		note "frames=$frames  NOTHING WRITTEN"
		printf '%-26s ctrl=%-8s poke=%-22s frames=%-4s nothing written\n' \
			"$name" "$ctrl" "${poke:-none}" "$frames" >> "$SUMMARY"
		continue
	fi

	# cmp -l is 1-based; convert to a 0-based extent.
	note "frames=$frames  written bytes $((first-1)) .. $((last-1))"
	$SSH "cat /tmp/sd.bin" > "$OUT/dump-$name.bin"
	printf '%-26s ctrl=%-8s poke=%-22s frames=%-4s extent %s..%s\n' \
		"$name" "$ctrl" "${poke:-none}" "$frames" "$((first-1))" "$((last-1))" >> "$SUMMARY"
done

log "done"
cat "$SUMMARY"
note "results in $OUT"
