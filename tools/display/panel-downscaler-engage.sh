#!/usr/bin/env bash
# Does the PANEL down-scaler act on our raster -- with the stage actually ON?
# RUNS ON THE HOST.
#
# WHY THIS EXISTS AND panel-downscaler-probe.sh DOES NOT SUPERSEDE IT.
# That script's 2026-09-04 negative is WITHDRAWN. It wrote 0x051c0138 alone and
# left 0x051c0124[26:25] = 3 -- which the corrected branch decode shows is the
# BYPASSED state, not the enabled one. It tested a stage that was switched off,
# on both sides of the mux. It also wrote 0x018000, which is ABOVE unity: a
# value this firmware can never emit, in the direction the hardware does not go.
#
#   docs/reference/composition-ratio-registers-are-line-buffers-2026-09-10.md
#
# THE CORRECTED DECODE, read out of both branches of
# PanelWinNode::WriteDownScalerRatio (0x8b1a58c0..0x8b1a5a34) in display.bin,
# with win_a = the OUTPUT window and win_b = the INPUT window:
#
#                       ratio == unity ("bypass")   ratio != unity (ACTIVE)
#   0x051c0124[26:25]   3                           0        <- the missed step
#   0x051c0120[26:24]   --                          2
#   0x051c0128[15:0]    out_w                       in_w - 6
#   0x051c012c[15:0]    out_h                       out_h
#   0x051c0130          {out_w, out_h}              {in_w, in_h}
#   0x051c0134          --                          {in_w + in_x + 2, 0}
#   0x051c0138[21:0]    ratio                       ratio
#
# THE RATIO, traced to its producer -- CalcScalingRatio_2 (0x8b19fb50,
# ./windows_manager_util.c), called from PanelWinNode::CalcWindow with
# &this[8]:
#
#   ratio = (out_vSize << 16) / in_vSize,  clamped to unity when out >= in
#
# dst/src, 16.16, ALWAYS <= 0x10000. The stage shrinks and never enlarges.
#
# THE BLOCK IS VERTICAL ONLY. One ratio register, one ratio computation, and the
# active path is given input geometry + output HEIGHT + a vertical ratio. There
# is no output width and no horizontal ratio anywhere in it. CalcScalingRatio_1
# (both axes) is called only from CapWinNode. So this block can do 1080 -> 720;
# it CANNOT do 1920 -> 1280, and this script does not pretend to test that.
#
# WHAT THIS TEST IS. Liveness, on the 1280x720 raster we already scan out --
# not a 1080p test, which would depend on plumbing this block cannot finish.
# Squeeze the raster we have to OUT_H lines using the firmware's own arithmetic.
# Default OUT_H=480, i.e. ratio = (480 << 16) / 720 = 0xAAAA -- the same 2/3 as
# 1080 -> 720, so a positive here transfers directly.
#
# WHAT EACH OUTCOME MEANS, stated before the run so it cannot be reinterpreted:
#   * the picture squeezes vertically -> the block IS on our raster, the 09-04
#     negative was an artefact of writing the ratio alone, and we have a real
#     vertical down-scaler.
#   * no change, writes stick        -> the negative stands for a sound reason
#     and this route is genuinely closed. Record it and stop.
#   * writes do not stick            -> the field is gated with the MIPS parked,
#     same wall as 0x05000000. Also an answer.
#
# SAFETY, AND HOW THIS DIFFERS FROM THE ONE-REGISTER TEST. This writes SEVEN
# registers on live display hardware, including an enable. Every one is saved as
# a whole word first and restored as a whole word, in reverse order, and the
# restore of every register is verified; a failed restore aborts and is reported
# as the more serious result it is. There is no commit latch anywhere in
# PanelWinNode's slot 4, so writes take effect as written -- which cuts both
# ways: nothing needs a flip, and nothing can be staged and abandoned.
#
# It refuses to run with the display MIPS alive: live MIPS plus our traffic is a
# reproducible whole-SoC hard lock with no watchdog.
#
# NEEDS AN OPERATOR WATCHING THE PANEL. Only eyes decide this one. Ask, end the
# turn, wait for "ready", then run.
#
#   usage: tools/display/panel-downscaler-engage.sh            # plan only, no writes
#          tools/display/panel-downscaler-engage.sh --engage   # WATCH THE PANEL
#          tools/display/panel-downscaler-engage.sh --engage --rgb
#          BOARD=192.168.4.1 OUT_H=360 HOLD=8 CYCLES=4 ... --engage
set -uo pipefail

BOARD=${BOARD:-192.168.4.1}
SSH="ssh -o ConnectTimeout=20 root@$BOARD"
HOLD=${HOLD:-8}
CYCLES=${CYCLES:-4}
# The vertical size to squeeze our raster to. Must be < the raster height or the
# firmware's own formula clamps to unity and the test writes a no-op.
OUT_H=${OUT_H:-480}
# The input window's x origin. 0 for a full-raster source; only feeds 0x0134.
IN_X=${IN_X:-0}
DO_ENGAGE=0
DO_RGB=0
rc=0

for arg in "$@"; do
	case "$arg" in
	--engage) DO_ENGAGE=1 ;;
	--rgb)    DO_RGB=1 ;;
	*) echo "unknown argument: $arg" >&2; exit 2 ;;
	esac
done

# 0x013c is read and reported but never written -- it is in the control group
# on the stock capture and a change in it would be worth knowing about.
OFFS="0120 0124 0128 012c 0130 0134 0138 013c"

say()  { printf '%s\n' "$*"; }
rule() { printf '%s\n' "------------------------------------------------------------"; }
hex()  { printf '0x%08x' "$1"; }

rd() { $SSH "busybox devmem 0x051c$1 32" 2>/dev/null; }
wr() { $SSH "busybox devmem 0x051c$1 32 $2" >/dev/null 2>&1; }

# Insert VALUE into WORD at [pos+width-1 : pos], the `ins` the firmware uses.
ins() { local word=$1 val=$2 pos=$3 width=$4 mask
	mask=$(( ( (1 << width) - 1 ) << pos ))
	echo $(( ( word & ~mask ) | ( ( val << pos ) & mask ) ))
}

# ---------------------------------------------------------------- preflight
rule
say "PREFLIGHT"
if ! $SSH true 2>/dev/null; then
	say "  cannot reach root@$BOARD -- is the board up?"
	exit 1
fi
say "  kernel: $($SSH 'uname -r' 2>/dev/null)"

mips=$($SSH 'busybox devmem 0x0306101c 32' 2>/dev/null)
say "  MIPS reset status 0x0306101c: ${mips:-<unreadable>}"
case "$mips" in
"")           say "  REFUSING: could not read the MIPS state."; exit 1 ;;
*0x00000000)  say "  MIPS is parked -- safe to proceed." ;;
*)            say "  REFUSING: the MIPS is alive. Live MIPS + our traffic hard-locks the SoC."; exit 1 ;;
esac

# ------------------------------------------------ geometry, read not assumed
rule
say "GEOMETRY"
# 0x05880024 is the TCON active area: {[31:16] lines, [15:0] columns}.
act=$($SSH 'busybox devmem 0x05880024 32' 2>/dev/null)
if [ -z "$act" ]; then
	say "  REFUSING: could not read the TCON active area at 0x05880024."
	exit 1
fi
# {[31:16] active LINES, [15:0] active COLUMNS} -- this panel reads 0x02D00500,
# i.e. 0x2D0 = 720 lines in the high half and 0x500 = 1280 columns in the low.
IN_H=$(( ( $(( act )) >> 16 ) & 0xffff ))
IN_W=$(( $(( act )) & 0xffff ))
# Guard rather than trust: a garbage read must not be programmed into a live
# display block.
if [ "$IN_W" -lt 240 ] || [ "$IN_W" -gt 4096 ] || [ "$IN_H" -lt 240 ] || [ "$IN_H" -gt 4096 ]; then
	say "  REFUSING: 0x05880024 = $act gives an implausible ${IN_W}x${IN_H}."
	exit 1
fi
say "  TCON active 0x05880024 = $act  ->  raster ${IN_W}x${IN_H}"

if [ "$OUT_H" -ge "$IN_H" ]; then
	say "  REFUSING: OUT_H=$OUT_H is not less than the raster height $IN_H."
	say "  The firmware's own formula clamps to unity there, so this would"
	say "  write a no-op and prove nothing."
	exit 1
fi

# ratio = (out_vSize << 16) / in_vSize   -- CalcScalingRatio_2, 0x8b19fb50
RATIO=$(( ( OUT_H << 16 ) / IN_H ))
say "  ratio = ($OUT_H << 16) / $IN_H = $RATIO = $(printf '0x%06x' $RATIO)   (unity = 0x010000)"
if [ "$RATIO" -gt $(( 0x10000 )) ]; then
	say "  REFUSING: computed ratio is above unity. This block only shrinks."
	exit 1
fi

# ------------------------------------------------------- read the whole group
rule
say "CURRENT STATE -- the panel down-scaler control group"
declare -A ORIG
for off in $OFFS; do
	v=$(rd "$off")
	if [ -z "$v" ]; then
		say "  REFUSING: could not read 0x051c$off."
		exit 1
	fi
	ORIG[$off]=$v
	say "  051c$off  $v"
done
en=$(( ( $(( ${ORIG[0124]} )) >> 25 ) & 3 ))
say ""
say "  0x051c0124[26:25] = $en   (3 = BYPASSED, 0 = active)"
say "  0x051c0138[21:0]  = $(printf '0x%06x' $(( $(( ${ORIG[0138]} )) & 0x3fffff )))   (0x010000 = unity)"

# ---------------------------------------------------------------- the plan
rule
say "PLAN -- the firmware's active path, in the firmware's order"
w012c=$(ins $(( ${ORIG[012c]} )) "$OUT_H"                    0     16)
w0124=$(ins $(( ${ORIG[0124]} )) 0                           25     2)
w0120=$(ins $(( ${ORIG[0120]} )) 2                           24     3)
w0128=$(ins $(( ${ORIG[0128]} )) $(( IN_W - 6 ))             0     16)
w0130=$(ins $(( ${ORIG[0130]} )) "$IN_W"                    16     16)
w0130=$(ins "$w0130"             "$IN_H"                     0     16)
w0134=$(ins $(( ${ORIG[0134]} )) 0                           0     16)
w0134=$(ins "$w0134"             $(( IN_W + IN_X + 2 ))     16     16)
w0138=$(ins $(( ${ORIG[0138]} )) "$RATIO"                    0     22)

plan_row() { # off orig new note
	local mark="   "
	[ "$(( ${2} ))" -eq "$3" ] && mark="  ="
	printf '%s 0x051c%-6s %-12s -> %-12s  %s\n' "$mark" "$1" "$2" "$(hex $3)" "$4"
}
plan_row 012c "${ORIG[012c]}" "$w012c" "out_h = $OUT_H"
plan_row 0124 "${ORIG[0124]}" "$w0124" "[26:25] = 0  LEAVE BYPASS"
plan_row 0120 "${ORIG[0120]}" "$w0120" "[26:24] = 2"
plan_row 0128 "${ORIG[0128]}" "$w0128" "in_w - 6 = $(( IN_W - 6 ))"
plan_row 0130 "${ORIG[0130]}" "$w0130" "{in_w, in_h} = {$IN_W, $IN_H}"
plan_row 0134 "${ORIG[0134]}" "$w0134" "{in_w + in_x + 2, 0} = {$(( IN_W + IN_X + 2 )), 0}"
plan_row 0138 "${ORIG[0138]}" "$w0138" "ratio = $(printf '0x%06x' $RATIO)"
say ""
say "  '=' marks a register the active path wants to leave where it already is."
say "  On a 1280x720 raster that should be 0x0120 and 0x0130 -- the board's"
say "  inherited state already agrees with the decode there, which is a check"
say "  on the decode, not a coincidence to wave through."

if [ "$DO_ENGAGE" -eq 0 ]; then
	rule
	say "Plan only -- nothing was written. Re-run with --engage, operator"
	say "watching the panel. Expect the picture to squeeze vertically to"
	say "$OUT_H/$IN_H of its height."
	exit 0
fi

# ------------------------------------------------------- gate: a live raster
rule
if [ "$DO_RGB" -eq 1 ]; then
	say "RASTER GATE (RGB/OSD side of the 0x051c006c mux)"
	stop_playback() { :; }

	sel=$($SSH 'busybox devmem 0x051c006c 32' 2>/dev/null)
	say "  selector 0x051c006c: ${sel:-<unreadable>}   (0x29000000 = RGB/OSD)"
	case "$sel" in
	*0x29000000) ;;
	*) say "  REFUSING: the selector is not on the RGB source, so this would not"
	   say "  be the RGB-path test it claims to be."; exit 1 ;;
	esac

	# The console issues no page flips, so prove the raster is live another
	# way: the TCON scan counter must be advancing.
	s1=$($SSH 'busybox devmem 0x05880000 32' 2>/dev/null); sleep 1
	s2=$($SSH 'busybox devmem 0x05880000 32' 2>/dev/null)
	say "  TCON scan counter 0x05880000: $s1 -> $s2"
	if [ "$s1" = "$s2" ] || [ -z "$s1" ]; then
		say "  REFUSING: the TCON scan counter is not advancing."
		exit 1
	fi
	say "  raster live."

	# A login prompt is a few characters top-left, where a vertical squeeze is
	# easy to miss. Fill the screen so the geometry change is unmistakable.
	$SSH "for i in \$(seq 1 40); do
	        printf 'DOWNSCALER ENGAGE %02d ##################################\n' \$i
	      done > /dev/tty1" >/dev/null 2>&1
	say "  console filled with a text pattern."
else
	say "RASTER GATE (DECD video side)"
	say "  Gated on the video plane cycling >= 2 distinct fb ids, because mpv"
	say "  logging its direct path proves selection, not display."

	play=$($SSH "
		for c in /root/leota-av-720p.mp4 /root/video-test/disp-720p.h265 \
		         /root/video-test/v02-1280x720-baseline.h264 \
		         /root/video-test/*.h264 /root/leota-720p.h264; do
			[ -f \"\$c\" ] && clip=\$c && break
		done
		[ -n \"\${clip:-}\" ] || { echo NOCLIP; exit 1; }
		echo \"clip \$clip\"
		cat > /tmp/pde-play.sh <<'PLAY'
export LIBVA_DRIVER_NAME=v4l2_request
exec mpv --no-config --no-audio --vo=drm --hwdec=vaapi --loop-file=inf \
    --msg-level=all=v CLIP
PLAY
		sed -i \"s|CLIP|\$clip|\" /tmp/pde-play.sh
		setsid bash /tmp/pde-play.sh </dev/null >/tmp/pde-play.log 2>&1 &
		sleep 10
		st=\$(ls /sys/kernel/debug/dri/*/state 2>/dev/null | head -1)
		pl=\$(sed -n 's/.*Using [a-z]* plane \([0-9]*\) as drmprime plane.*/\1/p' /tmp/pde-play.log | head -1)
		fbs=
		for i in 1 2 3 4 5 6; do
			fbs=\"\$fbs \$(grep -A2 \"^plane\[\${pl:-none}\]:\" \"\$st\" 2>/dev/null | sed -n 's/.*fb=//p' | head -1)\"
			sleep 0.3
		done
		echo \"plane \${pl:-none} fbs\$fbs distinct \$(echo \$fbs | tr ' ' '\n' | sort -u | grep -c .)\"
	" 2>&1)
	say "$play" | sed 's/^/  /'

	stop_playback() {
		# SIGTERM, not SIGKILL, so mpv releases DRM master and the console
		# comes back. A previous session left mpv holding it for three minutes.
		$SSH "pkill -TERM -f pde-play; pkill -TERM -x mpv; sleep 3; pkill -x mpv" >/dev/null 2>&1
	}

	if echo "$play" | grep -q NOCLIP; then
		say "  no 720p clip on the board -- cannot gate the test. Aborting."
		exit 1
	fi
	if ! echo "$play" | awk '/^plane /{for(i=1;i<=NF;i++) if($i=="distinct" && $(i+1)+0>=2) ok=1} END{exit !ok}'; then
		say "  the video plane cycled fewer than two framebuffers -- nothing new"
		say "  is being scanned out, so a null would say nothing. Aborting."
		stop_playback
		exit 1
	fi
	say "  scanout confirmed."
fi

# --------------------------------------------------------------- engage
# Whole-word writes computed from a fresh read, which reproduces the firmware's
# read-modify-write exactly while keeping the restore trivially correct. If the
# hardware moved a bit in another field between the read above and now we would
# clobber it -- phase 2 of panel-downscaler-probe.sh established that nothing in
# this group moves at idle, and the restore puts every word back verbatim.
engage() {
	wr 012c "$(hex $w012c)"
	wr 0124 "$(hex $w0124)"
	wr 0120 "$(hex $w0120)"
	wr 0128 "$(hex $w0128)"
	wr 0130 "$(hex $w0130)"
	wr 0134 "$(hex $w0134)"
	wr 0138 "$(hex $w0138)"
}
# Reverse order, so the enable goes back to BYPASS before the geometry it was
# reading is taken out from under it.
restore() {
	wr 0138 "${ORIG[0138]}"
	wr 0134 "${ORIG[0134]}"
	wr 0130 "${ORIG[0130]}"
	wr 0128 "${ORIG[0128]}"
	wr 0120 "${ORIG[0120]}"
	wr 0124 "${ORIG[0124]}"
	wr 012c "${ORIG[012c]}"
}

rule
say "ENGAGING. WATCH THE PANEL."
say "  Expect the picture to squeeze vertically to $OUT_H/$IN_H of its height."
say "  No change is also a result and closes this block."
say ""
# PULSE, don't step. The operator cannot see this output as it runs, so a single
# timed change has to be caught blind -- and an earlier RGB run was missed
# exactly that way. Alternating makes the test self-announcing.
say "  pulsing $CYCLES times: ${HOLD}s engaged, 3s bypassed. Total $(( CYCLES * (HOLD + 3) ))s."

for cycle in $(seq 1 "$CYCLES"); do
	engage
	if [ "$cycle" -eq 1 ]; then
		bad=0
		for pair in "012c $w012c" "0124 $w0124" "0120 $w0120" "0128 $w0128" \
		            "0130 $w0130" "0134 $w0134" "0138 $w0138"; do
			set -- $pair
			got=$(rd "$1")
			if [ "$(( ${got:-0} ))" -ne "$2" ]; then
				say "  READBACK MISMATCH 0x051c$1: got ${got:-<unreadable>}, wanted $(hex $2)"
				bad=1
			fi
		done
		if [ "$bad" -eq 1 ]; then
			say "  WRITES DID NOT STICK -- the block is gated with the MIPS parked."
			say "  That is itself the answer. Restoring and stopping rather than"
			say "  pulsing a field that is not taking writes."
			rc=1
			gated=1
		else
			say "  all seven readbacks match."
		fi
	fi
	say "  cycle $cycle/$CYCLES: engaged"
	sleep "$HOLD"
	restore
	say "  cycle $cycle/$CYCLES: bypassed"
	[ "${gated:-0}" -eq 1 ] && break
	sleep 3
done

# ------------------------------------------------------------- final restore
restore
rule
say "RESTORE"
fail=0
for off in $OFFS; do
	got=$(rd "$off")
	say "  051c$off  ${got:-<unreadable>}   (was ${ORIG[$off]})"
	[ "$got" != "${ORIG[$off]}" ] && fail=1
done
if [ "$fail" -eq 1 ]; then
	say ""
	say "  RESTORE FAILED. Do not power-cycle before recording this: a failed"
	say "  restore on live display hardware is a more important result than the"
	say "  squeeze test."
	stop_playback
	exit 2
fi
say "  every register back to its original value."

stop_playback
say "  playback stopped; console should be back."
rule
say "Done. Record what the operator saw, INCLUDING 'no change'."
say "  squeezed -> the block is on our raster; the 09-04 negative was an"
say "              artefact and we have a vertical down-scaler."
say "  unchanged -> the negative stands for a sound reason. Route closed."
exit $rc
