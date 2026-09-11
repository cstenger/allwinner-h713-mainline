#!/usr/bin/env bash
# Does the TWO-AXIS scaler at 0x05180000 act on our raster? RUNS ON THE HOST.
#
# THE BLOCK. Four instances at 0x100 stride, the only block in this SoC with
# SEPARATE horizontal and vertical ratio registers. Composition (0x05000000) has
# no scaler at all; the panel down-scaler (0x051c0120) is vertical-only.
# Decoded from 0x8b1a66d0 in display.bin, which ProcWinNode::WriteReg calls, and
# confirmed field-for-field against two independent hardware reads before any
# experiment -- the 2026-08-31 MIPS-alive capture and our cold-booted board.
#
#   docs/reference/two-axis-scaler-found-2026-09-10.md
#
#   0x08[21:0]  H ratio    16.16, unity 0x10000, always <= unity
#   0x3c[21:0]  V ratio
#   0x00[15:0]  H phase  = (unity + ratio_h) >> 2
#   0x38[15:0]  V phase  = (unity + ratio_v) >> 1
#   0x14[27]    1 = both axes at unity -> no scaling.  A BYPASS.  CURRENTLY SET.
#   0x34        {in_win.w, in_win.h}   INPUT size
#   0x2c[15:0]  out_win.w              OUTPUT width
#   0x30[15:0]  out_win.h              OUTPUT height
#   0x40[15:0]  out_win.w
#
# THE TRAP THIS SCRIPT EXISTS TO AVOID. This project has twice written one
# register of a set and concluded "route closed" from the null: 0x05000174
# alone, and 0x051c0138 alone with 0x0124[26:25] left at BYPASS. Both were
# withdrawn. 0x05180014[27] is the same shape of bit and it is set right now.
# This script always clears it, and always writes the whole set, in the
# firmware's own order.
#
# WHY A SWEEP. There are four instances and we do not know which -- if any --
# carries our raster. The firmware's stage table names proc-vs_upscaler and
# proc-vde_upscaler, so at least two are real and distinct. Writing all four at
# once would answer "does any of them" but not "which", and a wedge would be
# four times as hard to unpick. So: one instance at a time.
#
# HOW THE OPERATOR TELLS THEM APART WITHOUT SEEING THIS OUTPUT. Instance n
# blinks n+1 times. Instance 0 blinks once, instance 3 blinks four times. Report
# the blink count and we know which instance responded. On --rgb the console is
# ALSO overprinted with the instance number, so there are two independent
# labels. This matters: the operator cannot see the terminal while watching the
# panel, and an earlier test was missed for exactly that reason.
#
# THE RATIO. Exactly 0x8000 -- one half, a power of two, so the arithmetic
# cannot be argued with afterwards. ratio = out * 0x10000 / in, which is
# CalcScalingRatio's own formula for the downscale direction. It also avoids the
# integer-phase carry: the firmware bumps 0x08[30:28] only when the H phase
# reaches 0x8000, and at ratio 0x8000 the phase is 0x6000, so the existing
# integer-phase bits are correct as they stand and are preserved.
#
# SAFETY. Writes nine registers per instance on live display hardware, including
# a bypass. Every register is saved as a whole word, restored in reverse order,
# and every instance is verified at the end; a failed restore aborts and is
# reported as the more serious result it is. Refuses to run with the MIPS alive.
#
# NEEDS AN OPERATOR WATCHING THE PANEL. Ask, end the turn, wait for "ready".
#
#   usage: tools/display/proc-scaler-sweep.sh                 # plan only
#          tools/display/proc-scaler-sweep.sh --engage        # video raster
#          tools/display/proc-scaler-sweep.sh --engage --rgb  # console raster
#          BOARD=192.168.4.1 OUT_DIV=2 SWEEPS=2 ... --engage
#          CLIP=/root/foo.mp4 SWEEPS=1 ... --engage
#
# CLIP LENGTH IS A CORRECTNESS CONSTRAINT, not a preference. The run must finish
# before the clip ends: at EOF --loop-file=inf restarts the decoder, and that
# restart is where VAAPI failed on 2026-09-10 ("Failed to create decode context:
# 1"), dropping mpv to software decode into the primary plane and silently
# moving the test onto the RGB raster. On this board the longest 720p clip is
# leota-av-720p.mp4 at 77 s, so SWEEPS=1 (about 58 s including the gate) fits
# and SWEEPS=2 (about 104 s) does not.
set -uo pipefail

BOARD=${BOARD:-192.168.4.1}
SSH="ssh -o ConnectTimeout=20 root@$BOARD"
# Divide the raster by this to get the output size. 2 -> ratio exactly 0x8000.
OUT_DIV=${OUT_DIV:-2}
PULSE_ON=${PULSE_ON:-2}
PULSE_OFF=${PULSE_OFF:-1}
GAP=${GAP:-4}
SWEEPS=${SWEEPS:-2}
INSTANCES=${INSTANCES:-"0 1 2 3"}
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

UNITY=$(( 0x10000 ))
# Saved and restored. 0x04/0x20/0x44/0x50 are not written by this test but are
# part of the block's control group and are recorded so a surprise is visible.
OFFS="00 04 08 14 20 2c 30 34 38 3c 40 44 50"

say()  { printf '%s\n' "$*"; }
rule() { printf '%s\n' "------------------------------------------------------------"; }
hex()  { printf '0x%08x' "$1"; }
addr() { printf '0x%08x' $(( 0x05180000 + $1 * 0x100 + 0x$2 )); }

rd() { $SSH "busybox devmem $1 32" 2>/dev/null; }
wr() { $SSH "busybox devmem $1 32 $2" >/dev/null 2>&1; }

ins() { local word=$1 val=$2 pos=$3 width=$4 mask
	mask=$(( ( (1 << width) - 1 ) << pos ))
	echo $(( ( word & ~mask ) | ( ( val << pos ) & mask ) ))
}

declare -A ORIG NEW

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
"")          say "  REFUSING: could not read the MIPS state."; exit 1 ;;
*0x00000000) say "  MIPS is parked -- safe to proceed." ;;
*)           say "  REFUSING: the MIPS is alive. Live MIPS + our traffic hard-locks the SoC."; exit 1 ;;
esac

# ------------------------------------------------ geometry, read not assumed
rule
say "GEOMETRY"
act=$($SSH 'busybox devmem 0x05880024 32' 2>/dev/null)
[ -z "$act" ] && { say "  REFUSING: could not read the TCON active area."; exit 1; }
# {[31:16] active LINES, [15:0] active COLUMNS}
IN_H=$(( ( $(( act )) >> 16 ) & 0xffff ))
IN_W=$(( $(( act )) & 0xffff ))
if [ "$IN_W" -lt 240 ] || [ "$IN_W" -gt 4096 ] || [ "$IN_H" -lt 240 ] || [ "$IN_H" -gt 4096 ]; then
	say "  REFUSING: 0x05880024 = $act gives an implausible ${IN_W}x${IN_H}."
	exit 1
fi
OUT_W=$(( IN_W / OUT_DIV )); OUT_H=$(( IN_H / OUT_DIV ))
say "  TCON active 0x05880024 = $act  ->  raster ${IN_W}x${IN_H}"
say "  input  ${IN_W}x${IN_H}  (unchanged)"
say "  output ${OUT_W}x${OUT_H}  (raster / $OUT_DIV)"

# ratio = out * unity / in   -- CalcScalingRatio's downscale form. Always <= unity.
RH=$(( OUT_W * UNITY / IN_W ))
RV=$(( OUT_H * UNITY / IN_H ))
PH=$(( ( UNITY + RH ) >> 2 ))
PV=$(( ( UNITY + RV ) >> 1 ))
say "  ratio_h = $OUT_W * 0x10000 / $IN_W = $(printf '0x%06x' $RH)"
say "  ratio_v = $OUT_H * 0x10000 / $IN_H = $(printf '0x%06x' $RV)"
say "  H phase = (0x10000 + ratio_h) >> 2 = $(printf '0x%04x' $PH)"
say "  V phase = (0x10000 + ratio_v) >> 1 = $(printf '0x%04x' $PV)"
if [ "$RH" -gt "$UNITY" ] || [ "$RV" -gt "$UNITY" ]; then
	say "  REFUSING: a ratio came out above unity. This encoding is always <= unity."
	exit 1
fi
if [ "$RH" -eq "$UNITY" ] && [ "$RV" -eq "$UNITY" ]; then
	say "  REFUSING: both ratios are unity, so this would write a no-op."
	exit 1
fi
if [ "$PH" -ge $(( 0x8000 )) ]; then
	say "  NOTE: H phase >= 0x8000, where the firmware bumps the integer phase"
	say "  0x08[30:28]. This script preserves those bits, so pick OUT_DIV to"
	say "  keep the phase below 0x8000 (OUT_DIV=2 gives 0x6000) if that matters."
fi

# ------------------------------------------------- read and plan, all instances
rule
say "CURRENT STATE AND PLAN"
for n in $INSTANCES; do
	for o in $OFFS; do
		v=$(rd "$(addr "$n" "$o")")
		[ -z "$v" ] && { say "  REFUSING: could not read $(addr "$n" "$o")."; exit 1; }
		ORIG[$n.$o]=$v
	done
	# The firmware's order in 0x8b1a66d0: 14, 08, 3c, 00, 38, 34, 2c, 30, 40.
	NEW[$n.14]=$(ins $(( ${ORIG[$n.14]} )) 0      27  1)
	NEW[$n.08]=$(ins $(( ${ORIG[$n.08]} )) "$RH"   0 22)
	NEW[$n.3c]=$(ins $(( ${ORIG[$n.3c]} )) "$RV"   0 22)
	NEW[$n.00]=$(ins $(( ${ORIG[$n.00]} )) "$PH"   0 16)
	NEW[$n.38]=$(ins $(( ${ORIG[$n.38]} )) "$PV"   0 16)
	t=$(ins $(( ${ORIG[$n.34]} )) "$IN_W" 16 16)
	NEW[$n.34]=$(ins "$t" "$IN_H" 0 16)
	NEW[$n.2c]=$(ins $(( ${ORIG[$n.2c]} )) "$OUT_W" 0 16)
	NEW[$n.30]=$(ins $(( ${ORIG[$n.30]} )) "$OUT_H" 0 16)
	NEW[$n.40]=$(ins $(( ${ORIG[$n.40]} )) "$OUT_W" 0 16)

	say ""
	say "  --- instance $n  (base $(addr "$n" 00)) ---"
	bypass=$(( ( $(( ${ORIG[$n.14]} )) >> 27 ) & 1 ))
	say "      bypass 0x14[27] = $bypass   (1 = no scaling; this test clears it)"
	for o in 14 08 3c 00 38 34 2c 30 40; do
		mark="   "
		[ "$(( ${ORIG[$n.$o]} ))" -eq "${NEW[$n.$o]}" ] && mark="  ="
		printf '%s   +0x%-4s %-12s -> %s\n' "$mark" "$o" "${ORIG[$n.$o]}" "$(hex ${NEW[$n.$o]})"
	done
done

if [ "$DO_ENGAGE" -eq 0 ]; then
	rule
	say "Plan only -- nothing was written. Re-run with --engage, operator"
	say "watching the panel. Expect the picture to shrink to ${OUT_W}x${OUT_H}"
	say "on whichever instance carries our raster."
	say ""
	say "Instance n blinks n+1 times: 1 blink = instance 0, 4 = instance 3."
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
	*) say "  REFUSING: the selector is not on the RGB source."; exit 1 ;;
	esac
	s1=$($SSH 'busybox devmem 0x05880000 32' 2>/dev/null); sleep 1
	s2=$($SSH 'busybox devmem 0x05880000 32' 2>/dev/null)
	say "  TCON scan counter 0x05880000: $s1 -> $s2"
	[ "$s1" = "$s2" ] || [ -z "$s1" ] && { say "  REFUSING: scan counter not advancing."; exit 1; }
	say "  raster live."
	banner() { # instance
		$SSH "for i in \$(seq 1 40); do
		        printf 'INSTANCE %s  ####  INSTANCE %s  ####  INSTANCE %s\n' $1 $1 $1
		      done > /dev/tty1" >/dev/null 2>&1
	}
	# ProcWinNode is the video/proc stage -- proc-vs_* and proc-vde_* -- so the
	# RGB/OSD raster may not pass through it at all. That makes --rgb the weaker
	# of the two gates here, and a null on it correspondingly weaker evidence.
	say "  NOTE: this block sits on the proc/video stage. A null on the RGB"
	say "  raster is weak evidence; run the video path too before concluding."
else
	say "RASTER GATE (DECD video side)"
	say "  Gated on the video plane cycling >= 2 distinct fb ids."
	banner() { :; }
	play=$($SSH "
		for c in ${CLIP:-} /root/leota-av-720p.mp4 /root/video-test/disp-720p.h265 \
		         /root/video-test/v02-1280x720-baseline.h264 \
		         /root/video-test/*.h264 /root/leota-720p.h264; do
			[ -f \"\$c\" ] && clip=\$c && break
		done
		[ -n \"\${clip:-}\" ] || { echo NOCLIP; exit 1; }
		echo \"clip \$clip\"
		cat > /tmp/pss-play.sh <<'PLAY'
export LIBVA_DRIVER_NAME=v4l2_request
exec mpv --no-config --no-audio --vo=drm --hwdec=vaapi --loop-file=inf \
    --msg-level=all=v CLIP
PLAY
		sed -i \"s|CLIP|\$clip|\" /tmp/pss-play.sh
		setsid bash /tmp/pss-play.sh </dev/null >/tmp/pss-play.log 2>&1 &
		sleep 10
		st=\$(ls /sys/kernel/debug/dri/*/state 2>/dev/null | head -1)
		pl=\$(sed -n 's/.*Using [a-z]* plane \([0-9]*\) as drmprime plane.*/\1/p' /tmp/pss-play.log | head -1)
		fbs=
		for i in 1 2 3 4 5 6; do
			fbs=\"\$fbs \$(grep -A2 \"^plane\[\${pl:-none}\]:\" \"\$st\" 2>/dev/null | sed -n 's/.*fb=//p' | head -1)\"
			sleep 0.3
		done
		echo \"plane \${pl:-none} fbs\$fbs distinct \$(echo \$fbs | tr ' ' '\n' | sort -u | grep -c .)\"
	" 2>&1)
	say "$play" | sed 's/^/  /'
	stop_playback() {
		$SSH "pkill -TERM -f pss-play; pkill -TERM -x mpv; sleep 3; pkill -x mpv" >/dev/null 2>&1
	}
	if echo "$play" | grep -q NOCLIP; then
		say "  no 720p clip on the board -- cannot gate the test. Aborting."; exit 1
	fi
	if ! echo "$play" | awk '/^plane /{for(i=1;i<=NF;i++) if($i=="distinct" && $(i+1)+0>=2) ok=1} END{exit !ok}'; then
		say "  the video plane cycled fewer than two framebuffers. Aborting."
		stop_playback; exit 1
	fi
	say "  scanout confirmed."

	# 2026-09-10: THE GATE ABOVE IS NOT ENOUGH ON ITS OWN, and a whole run was
	# mis-read because of it. It proves the video plane was cycling ONCE, at
	# t~10s. In that run the 77 s clip hit EOF, --loop-file=inf restarted it,
	# VAAPI failed to re-initialise ("Failed to create decode context: 1") and
	# mpv silently fell back to SOFTWARE decode into the primary XR24 plane.
	# Everything after that was the RGB/OSD raster wearing a video costume, and
	# the photographs taken at the end were read as video-path evidence.
	#
	# So: refuse a clip shorter than the planned run, and re-check the raster
	# between instances rather than trusting a single sample.
	# Take the path from the gate's own "clip <path>" line, not by re-parsing
	# pss-play.sh: the exec there is split over a line continuation, so an
	# anchored sed silently matches nothing and the guard skips itself.
	clip=$(printf '%s\n' "$play" | sed -n 's/^ *clip //p' | head -1)
	dur=$($SSH "ffprobe -v error -show_entries format=duration -of csv=p=0 '$clip'" 2>/dev/null)
	# Raw elementary streams carry no container duration. Fall back to counting
	# packets -- leota-720p.h264 is 5 s and would otherwise pass unchecked.
	if [ -z "$dur" ]; then
		dur=$($SSH "
			n=\$(ffprobe -v error -select_streams v:0 -count_packets \
			     -show_entries stream=nb_read_packets -of csv=p=0 '$clip' 2>/dev/null)
			r=\$(ffprobe -v error -select_streams v:0 \
			     -show_entries stream=r_frame_rate -of csv=p=0 '$clip' 2>/dev/null)
			awk -v n=\"\$n\" -v r=\"\$r\" 'BEGIN{split(r,a,\"/\"); if(a[2]==\"\")a[2]=1;
			     if(a[1]>0 && n>0) printf \"%.1f\", n*a[2]/a[1]}'" 2>/dev/null)
	fi
	planned=$(awk -v on="$PULSE_ON" -v off="$PULSE_OFF" -v gap="$GAP" -v sw="$SWEEPS" \
		-v inst="$INSTANCES" 'BEGIN{n=split(inst,a," ");t=0;
		for(i=1;i<=n;i++) t+=(a[i]+1)*(on+off)+gap; printf "%.0f", t*sw}')
	say "  clip duration ${dur:-unknown}s, planned run ${planned}s"
	if [ -n "$dur" ] && awk -v d="$dur" -v p="$planned" 'BEGIN{exit !(d < p+15)}'; then
		say "  REFUSING: the clip is shorter than the run. It will loop, and a"
		say "  loop restart is where VAAPI dropped to software decode last time,"
		say "  silently moving the test onto the RGB raster. Use a longer clip"
		say "  (CLIP=/path) or fewer sweeps."
		stop_playback
		exit 1
	fi
fi

# Returns 0 while the DECD video plane is still scanning out. On --rgb the
# TCON scan counter stands in for it.
raster_ok() {
	if [ "$DO_RGB" -eq 1 ]; then
		local a b
		a=$($SSH 'busybox devmem 0x05880000 32' 2>/dev/null); sleep 0.5
		b=$($SSH 'busybox devmem 0x05880000 32' 2>/dev/null)
		[ -n "$a" ] && [ "$a" != "$b" ]
	else
		$SSH '
			st=$(ls /sys/kernel/debug/dri/*/state 2>/dev/null | head -1)
			sw=$(grep -c "Using software decoding" /tmp/pss-play.log 2>/dev/null)
			fb=$(grep -A2 "^plane\[38\]:" "$st" 2>/dev/null | sed -n "s/.*fb=//p" | head -1)
			[ "${sw:-0}" -eq 0 ] && [ -n "$fb" ] && [ "$fb" != "0" ]
		' >/dev/null 2>&1
	fi
}

# ----------------------------------------------------------------- the sweep
engage()  { local n=$1; for o in 14 08 3c 00 38 34 2c 30 40; do wr "$(addr "$n" "$o")" "$(hex ${NEW[$n.$o]})"; done; }
restore() { local n=$1; for o in 40 30 2c 34 38 00 3c 08 14; do wr "$(addr "$n" "$o")" "${ORIG[$n.$o]}"; done; }

verify_engaged() { local n=$1 bad=0 got
	for o in 14 08 3c 00 38 34 2c 30 40; do
		got=$(rd "$(addr "$n" "$o")")
		if [ "$(( ${got:-0} ))" -ne "${NEW[$n.$o]}" ]; then
			say "    READBACK MISMATCH $(addr "$n" "$o"): got ${got:-<unreadable>}, wanted $(hex ${NEW[$n.$o]})"
			bad=1
		fi
	done
	return $bad
}

rule
say "SWEEPING. WATCH THE PANEL."
say "  Expect the picture to shrink to ${OUT_W}x${OUT_H} on whichever instance"
say "  carries our raster. No change on any of them is also a result."
say ""
say "  INSTANCE n BLINKS n+1 TIMES -- count the blinks and that is the answer."
say "     1 blink = instance 0      3 blinks = instance 2"
say "     2 blinks = instance 1     4 blinks = instance 3"
# awk, not shell arithmetic: PULSE_ON may be fractional when someone is
# shortening the run to smoke-test the script.
say "  $SWEEPS sweep(s), about $(awk -v on="$PULSE_ON" -v off="$PULSE_OFF" -v gap="$GAP" \
	-v sw="$SWEEPS" -v inst="$INSTANCES" 'BEGIN{n=split(inst,a," ");t=0;
	for(i=1;i<=n;i++) t+=(a[i]+1)*(on+off)+gap; printf "%.0f", t*sw}')s total."

declare -A STUCK
for sweep in $(seq 1 "$SWEEPS"); do
	say ""
	say "  === sweep $sweep/$SWEEPS ==="
	for n in $INSTANCES; do
		# Re-verify BEFORE each instance. A run that changes decode path
		# halfway produces evidence about a raster nobody chose to test.
		if ! raster_ok; then
			say ""
			say "    RASTER LOST before instance $n -- the video plane stopped"
			say "    scanning out, or mpv fell back to software decoding."
			say "    ABORTING rather than collecting evidence about the wrong"
			say "    raster. Everything already shown was on the good raster;"
			say "    anything after this point would not have been."
			rc=1
			break 2
		fi
		banner "$n"
		say "    instance $n: $(( n + 1 )) blink(s)"
		for p in $(seq 1 $(( n + 1 ))); do
			engage "$n"
			if [ "$sweep" -eq 1 ] && [ "$p" -eq 1 ]; then
				if verify_engaged "$n"; then
					say "    instance $n: all nine readbacks match."
					STUCK[$n]=1
				else
					say "    instance $n: WRITES DID NOT STICK -- gated. That is itself an answer."
					STUCK[$n]=0
					rc=1
				fi
			fi
			sleep "$PULSE_ON"
			restore "$n"
			sleep "$PULSE_OFF"
		done
		sleep "$GAP"
	done
done

# ------------------------------------------------------------- final restore
for n in $INSTANCES; do restore "$n"; done
rule
say "RESTORE"
fail=0
for n in $INSTANCES; do
	for o in $OFFS; do
		got=$(rd "$(addr "$n" "$o")")
		if [ "$got" != "${ORIG[$n.$o]}" ]; then
			say "  MISMATCH $(addr "$n" "$o"): ${got:-<unreadable>} (was ${ORIG[$n.$o]})"
			fail=1
		fi
	done
done
if [ "$fail" -eq 1 ]; then
	say ""
	say "  RESTORE FAILED. Do not power-cycle before recording this: a failed"
	say "  restore on live display hardware matters more than the sweep result."
	stop_playback
	exit 2
fi
say "  all $(echo $INSTANCES | wc -w) instances, $(echo $OFFS | wc -w) registers each, back to their original values."

stop_playback
rule
say "Done. Record what the operator saw, INCLUDING 'no change'."
say "  a shrink -> COUNT THE BLINKS; that names the instance, and we have a"
say "              two-axis scaler on our raster."
say "  no change on any -> the block is not on this raster. Run the other path"
say "              before concluding; this one sits on the proc/video stage."
for n in $INSTANCES; do
	[ "${STUCK[$n]:-1}" -eq 0 ] && say "  instance $n did not accept writes -- gated, independent of what was seen."
done
exit $rc
