#!/usr/bin/env bash
# Sweep the unknown VE scale-down control word (VE+0x40) and report, for each
# candidate, whether the hardware wrote anything into a secondary output buffer.
# RUNS ON THE HOST, drives the board over ssh.
#
# Requires a kernel carrying patches/kernel/0097 (the cedrus scale-down harness).
#
# WHY THE BUFFER IS OVERSIZED. The patch programs the scaled output ADDRESSES
# but not the output GEOMETRY, which the vendor sets from registers we have not
# decoded. So the hardware decides how much to write. The buffer is declared at
# twice the source height, giving the luma plane a full frame of headroom, and
# the sweep stops if a write ever reaches the last page of the allocation.
#
# The buffer is poisoned with 0xa5 by the driver on every change of sd_ctrl, so
# "wrote nothing" is distinguishable from "wrote black" -- a flat fill is
# ambiguous on this hardware.
#
# Entirely headless: no display, no MIPS, no operator. Safe to re-run.
#
#   usage: tools/video/ve-scaledown-sweep.sh [ctrl-value ...]
#          CANDS="0x1 0x2" tools/video/ve-scaledown-sweep.sh
set -euo pipefail

BOARD=${BOARD:-192.168.4.1}
SSH="ssh -o ConnectTimeout=5 root@$BOARD"
CLIP=${CLIP:-/root/leota-1080p.mp4}
FRAMES=${FRAMES:-60}

# The driver lays the buffer out as luma at +0 and chroma at +(SD_W*SD_H), so
# declaring twice the source height gives a luma plane with a full frame of
# headroom after it. The "canary" is therefore everything past the luma
# capacity: the chroma plane lives there by construction, so a write there is
# only alarming if it runs past the end of the buffer.
SD_W=1920
SD_H=2176
LUMA_CAP=$(( SD_W * SD_H ))          # 4177920  luma plane capacity
TOTAL=$(( SD_W * SD_H * 3 / 2 ))     # 6266880  whole allocation

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
OUT=${OUT:-$ROOT/local/ve-sd-sweep-$(date +%Y%m%d-%H%M%S)}
mkdir -p "$OUT"

if [ $# -gt 0 ]; then
	CANDS="$*"
else
	# bits[2:0] are the mode per the vendor's bfi; 0xf is what the register
	# reads on a live decode; the 0x1xx values probe the second 4-bit field.
	CANDS=${CANDS:-"0x0 0x1 0x2 0x3 0x4 0x5 0x6 0x7 0xf \
	                0x100 0x101 0x102 0x10f \
	                0x10000 0x10001 0x80000001"}
fi

log() { printf '\n\033[1;34m==>\033[0m \033[1m%s\033[0m\n' "$*"; }
note(){ printf '    \033[33m%s\033[0m\n' "$*"; }

# ---------------------------------------------------------------- preflight
log "preflight"

$SSH true || { echo "error: board $BOARD unreachable" >&2; exit 1; }

if ! $SSH '[ -e /sys/module/sunxi_cedrus/parameters/sd_ctrl ]'; then
	echo "error: sunxi_cedrus has no sd_ctrl parameter -- the running module" >&2
	echo "       predates patch 0097. Install it with:" >&2
	echo "       tools/install-kernel-module.sh <tree> sunxi-cedrus" >&2
	exit 1
fi
if ! $SSH "[ -e /sys/kernel/debug/cedrus_sd_buf ]"; then
	echo "error: /sys/kernel/debug/cedrus_sd_buf missing -- is debugfs mounted?" >&2
	exit 1
fi
$SSH "[ -r '$CLIP' ]" || { echo "error: clip $CLIP not on the board" >&2; exit 1; }

# Nothing else may hold the decoder: another decode would allocate the context
# whose buffer we are about to read, and we would sample its frames, not ours.
if $SSH 'pgrep -x ffmpeg >/dev/null 2>&1'; then
	echo "error: an ffmpeg is already running on the board; stop it first" >&2
	exit 1
fi

note "clip      $CLIP  ($FRAMES frames per candidate)"
note "buffer    ${SD_W}x${SD_H} = $TOTAL bytes (luma cap $LUMA_CAP)"
note "results   $OUT"

# Poison reference, built once, for a byte-difference count on the board.
$SSH "head -c $TOTAL /dev/zero | tr '\\000' '\\245' > /tmp/sd-poison.bin && \
      [ \$(wc -c < /tmp/sd-poison.bin) -eq $TOTAL ]" \
	|| { echo "error: could not build the poison reference" >&2; exit 1; }

# Arm the harness. Verify the readback: a module parameter that silently
# refused the value would make every candidate look like a null result.
set_param() {
	local name=$1 val=$2 got
	$SSH "echo '$val' > /sys/module/sunxi_cedrus/parameters/$name"
	got=$($SSH "cat /sys/module/sunxi_cedrus/parameters/$name")
	if [ "$got" != "$((val))" ]; then
		echo "error: $name readback '$got' != '$((val))'" >&2
		exit 1
	fi
}

set_param sd_w "$SD_W"
set_param sd_h "$SD_H"
set_param sd_stage "${SD_STAGE:-1}"   # after the codec setup: engine enabled
set_param sd_shift "${SD_SHIFT:-0}"   # raw addresses; confirmed by readback
set_param sd_fmt   "${SD_FMT:-1}"     # linear NV12; 0 leaves the tiled default
note "armed: sd_w=$SD_W sd_h=$SD_H stage=${SD_STAGE:-1} shift=${SD_SHIFT:-0} fmt=${SD_FMT:-1}"

# The registers must actually hold what we write, or every candidate below is a
# null that means nothing. This cost one full sweep: the first run programmed
# VE+0x40/0x44/0x48 (top-level) instead of the H.264 engine's 0x240/0x244/0x248,
# and the address registers silently read back zero -- the scaler had nowhere to
# write, and 16 uniform nulls looked like "no such hardware".
$SSH 'dmesg -C' >/dev/null 2>&1 || true

disarm() {
	$SSH "echo 0 > /sys/module/sunxi_cedrus/parameters/sd_w;
	      echo 0 > /sys/module/sunxi_cedrus/parameters/sd_h;
	      echo 0 > /sys/module/sunxi_cedrus/parameters/sd_ctrl;
	      echo 0 > /sys/module/sunxi_cedrus/parameters/sd_fmt" 2>/dev/null || true
}
trap disarm EXIT

SUMMARY=$OUT/SUMMARY.txt
printf '%-12s %10s %12s %12s  %s\n' ctrl frames luma-diff chroma-diff verdict > "$SUMMARY"

# ------------------------------------------------------------------- sweep
for ctrl in $CANDS; do
	log "sd_ctrl = $ctrl"
	set_param sd_ctrl "$ctrl"

	# Decode. The driver re-poisons on the change of sd_ctrl above, so this
	# buffer starts clean. ffmpeg exiting releases the context, which is what
	# snapshots the buffer into the shadow the debugfs node serves.
	dec=$($SSH "export LIBVA_DRIVER_NAME=v4l2_request; \
	            ffmpeg -hide_banner -loglevel error -stats \
	              -hwaccel vaapi -hwaccel_output_format vaapi \
	              -i '$CLIP' -frames:v $FRAMES -f null - 2>&1 | tail -5" || true)
	# Write the log BEFORE parsing it: a parse that fails must still leave the
	# evidence behind, or the failure is undiagnosable.
	printf '%s\n' "$dec" > "$OUT/ffmpeg-$ctrl.log"
	frames=$(printf '%s' "$dec" | grep -o 'frame=[ ]*[0-9]*' | tail -1 \
	         | tr -dc '0-9' || true)
	frames=${frames:-0}

	# Record the driver's readback for this candidate. A null result is only
	# interpretable next to proof that the write landed.
	$SSH "dmesg | grep 'sd:' | tail -3" > "$OUT/regs-$ctrl.txt" 2>/dev/null || true
	if grep -q 'luma=0x00000000' "$OUT/regs-$ctrl.txt" 2>/dev/null; then
		note "WRITE DID NOT LAND (luma reads back 0) -- aborting, results would be meaningless"
		cat "$OUT/regs-$ctrl.txt"
		exit 1
	fi

	if [ "$frames" -eq 0 ]; then
		note "DECODE FAILED -- no frames; see $OUT/ffmpeg-$ctrl.log"
		printf '%-12s %10s %12s %12s  %s\n' \
			"$ctrl" 0 - - "decode-failed" >> "$SUMMARY"
		continue
	fi

	# Dump and count differing bytes, live area and canary separately.
	read -r dlive dcan < <($SSH "
		dd if=/sys/kernel/debug/cedrus_sd_buf of=/tmp/sd.bin bs=1M 2>/dev/null
		sz=\$(wc -c < /tmp/sd.bin)
		if [ \"\$sz\" -eq 0 ]; then echo 'EMPTY EMPTY'; exit 0; fi
		head -c $LUMA_CAP /tmp/sd.bin > /tmp/sd-live.bin
		tail -c +$((LUMA_CAP + 1)) /tmp/sd.bin > /tmp/sd-can.bin
		head -c $LUMA_CAP /tmp/sd-poison.bin > /tmp/p-live.bin
		a=\$(cmp -l /tmp/sd-live.bin /tmp/p-live.bin 2>/dev/null | wc -l)
		b=\$(cmp -l /tmp/sd-can.bin  /tmp/p-live.bin 2>/dev/null | wc -l)
		echo \"\$a \$b\"")

	if [ "$dlive" = "EMPTY" ]; then
		note "frames=$frames  buffer EMPTY (no shadow captured)"
		printf '%-12s %10s %12s %12s  %s\n' \
			"$ctrl" "$frames" - - "no-buffer" >> "$SUMMARY"
		continue
	fi

	verdict="NULL (buffer untouched)"
	if [ "$dlive" -gt 0 ]; then
		verdict="WROTE $dlive bytes"
		note "HIT -- pulling the full dump"
		$SSH "cat /tmp/sd.bin" > "$OUT/dump-$ctrl.bin"
	fi

	note "frames=$frames  live-diff=$dlive  canary-diff=$dcan"
	printf '%-12s %10s %12s %12s  %s\n' \
		"$ctrl" "$frames" "$dlive" "$dcan" "$verdict" >> "$SUMMARY"

	# The chroma plane legitimately lives past the luma capacity. Only a write
	# that reaches the last page of the whole allocation suggests the hardware
	# is running past anything we sized for.
	if [ "$dcan" -gt 0 ]; then
		tail_touched=$($SSH "tail -c 4096 /tmp/sd.bin | cmp -l - <(tail -c 4096 /tmp/sd-poison.bin) 2>/dev/null | wc -l" || echo 0)
		if [ "${tail_touched:-0}" -gt 0 ]; then
			note "LAST PAGE TOUCHED -- the hardware wrote to the end of the allocation."
			note "Stopping: the next candidate could write past it."
			printf '\nSTOPPED: allocation tail touched at ctrl=%s\n' "$ctrl" >> "$SUMMARY"
			break
		fi
	fi
done

log "done"
cat "$SUMMARY"
note "results in $OUT"
