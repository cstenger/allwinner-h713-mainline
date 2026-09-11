#!/usr/bin/env bash
# Set ONE scaler ratio and hold it, with the static test card on the panel.
# RUNS ON THE HOST.
#
# WHY THIS EXISTS SEPARATELY FROM proc-scaler-ratio-ramp.sh. That script had to
# race a clock: mpv free-runs at ~2.5x, so a 77 s clip gave ~31 s of usable
# video path and every step had to be 2-3 s. That forced continuous filming, and
# forced me to reconstruct step boundaries afterwards from luminance traces and
# an ssh-latency model -- twice.
#
# `decd-client show CARD.nv12 <dwell-ms>` holds a STATIC frame with no decoder in
# the loop: no VAAPI, no loop point, no free-running playback, no time limit. So
# there is no reason to hurry, and no reason to film. One step, held; one
# photograph, at leisure, with exposure and focus settled; then the next.
#
#   docs/reference/scaler-testcard.md   how to read the card
#
# PROTOCOL
#   scaler-card-step.sh card                    put the card up and hold it
#   scaler-card-step.sh set 0x18000             set ratio_h, leave it set
#   scaler-card-step.sh show                    read back the whole block
#   scaler-card-step.sh restore                 ratio unity, bypass set
#   scaler-card-step.sh off                     stop the card, release DECD
#   scaler-card-step.sh seq [RATIOS...]         timed windows, one photo each
#
# `set` is untimed -- take the photo whenever. `seq` holds each ratio for HOLD
# seconds (default 12) so the operator can shoot on a rhythm without touching
# anything or watching this terminal.
#
# WHY THE TIMING BARELY MATTERS HERE, unlike every earlier run: each photograph
# is SELF-MEASURING. The card's circles give the scale factor directly from the
# ellipse axis ratio, so a photo does not need to be matched to a step by
# timestamp -- measure each one, then check the set of measured factors against
# the set of commanded ones. A shot that lands in a transition shows an
# unexpected factor and is simply discarded. The alignment reconstruction that
# was needed on 09-10 and 09-11 does not apply.
#
# GEOMETRY IS NEVER TOUCHED by this script -- not 0x2c/0x30/0x34/0x40, not
# ratio_v (0x3c), not the V phase (0x38). Only the bypass, ratio_h and the H
# phase, exactly as the 2026-09-11 ramp did, so the two are comparable.
set -uo pipefail

BOARD=${BOARD:-192.168.4.1}
SSH="ssh -o ConnectTimeout=20 root@$BOARD"
INST=${INST:-0}
CARD=${CARD:-/root/scaler-testcard-1280x720.nv12}
DWELL_S=${DWELL_S:-300}               # seconds. kms-nv12-plane-test rejects >300
                                      # (its own check: "invalid dwell"), so 300 is
                                      # the ceiling, not a preference.
UNITY=$(( 0x10000 ))
rc=0

# 2026-09-11: this script originally drove decd-client, which needs
# /dev/decd from sunxi-decd-budget.ko -- NOT LOADED on this board. decd-client
# printed "open /dev/decd: No such file or directory", the card never appeared,
# and a five-step ratio sequence ran against a console screen and measured
# nothing. The error was in my own output and I read past it.
#
# So: use kms-nv12-plane-test, which drives the DRM video plane -- the same
# mechanism as the mpv path that produced the 09-11 positive, and therefore the
# comparable one. And VERIFY THE GATES rather than printing them: nothing may
# proceed until the card is demonstrably on the panel.
PLANE_TEST=${PLANE_TEST:-/root/kmsnv12/kms-nv12-plane-test}
CUE=${CUE:-/root/scaler-cue-1280x720.nv12}
MARK_S=${MARK_S:-2}

# Put one NV12 on the video plane for `dwell` seconds. The plane test arms in
# 0.13 s (measured), so relaunching per frame is cheap -- which is how the cue
# frame gets shown without any framebuffer poking. The plane buffer is an IOVA
# behind the IOMMU (0xFFA00000) and CMA-backed, so mem-write cannot reach it.
show_frame() {
	# The plane test refuses to start unless the NV12 plane is DISABLED ("no
	# disabled NV12 plane for CRTC 36"), so a relaunch must wait for the previous
	# instance to actually release it -- killing is not the same as released.
	$SSH "p=\$(cat /tmp/kms.pid 2>/dev/null); [ -n \"\$p\" ] && kill -TERM \"\$p\" 2>/dev/null
	      pkill -x kms-nv12-plane- >/dev/null 2>&1
	      for i in \$(seq 1 40); do
	        [ \"\$(busybox devmem 0x05600010 32)\" != 0x03000013 ] && break
	        sleep 0.1
	      done
	      : > /tmp/kms.log; rm -f /tmp/kms.pid
	      setsid env ARMED=yes $PLANE_TEST $1 $2 >/tmp/kms.log 2>&1 &
	      echo \$! > /tmp/kms.pid" >/dev/null 2>&1
}

# Every condition that must hold for a ratio measurement to mean anything.
# Returns non-zero with a reason if any fails.
check_gates() {
	local src ybase sel plane bad=0
	src=$(rd 0x05600010); ybase=$(rd 0x05600070); sel=$(rd 0x051c006c)
	plane=$($SSH 'grep -A2 "^plane\[38\]" /sys/kernel/debug/dri/0/state 2>/dev/null | tr -d " \t" | tr "\n" " "' 2>/dev/null)
	[ "$src" = "0x03000013" ] || { say "  GATE FAIL video source $src (want 0x03000013)"; bad=1; }
	[ "$ybase" != "0x00000000" ] || { say "  GATE FAIL Y base is zero -- no frame behind the source"; bad=1; }
	[ "$sel" = "0x39000000" ] || { say "  GATE FAIL selector $sel (want 0x39000000 = video)"; bad=1; }
	case "$plane" in
	*crtc=crtc-0*) ;;
	*) say "  GATE FAIL plane 38 not on a crtc: $plane"; bad=1 ;;
	esac
	case "$plane" in
	*fb=0\ *|*fb=0) say "  GATE FAIL plane 38 has fb=0"; bad=1 ;;
	esac
	return $bad
}

bring_card_up() {
	local sz
	sz=$($SSH "stat -c %s $CARD 2>/dev/null")
	[ -n "$sz" ] || { say "card not on the board: $CARD"; return 1; }
	[ "$DWELL_S" -le 300 ] || { say "DWELL_S=$DWELL_S exceeds the tool's 300 s limit"; return 1; }
	[ -n "$($SSH "test -x $PLANE_TEST && echo y")" ] || { say "missing $PLANE_TEST"; return 1; }
	# NOT `pkill -f kms-nv12-plane-test`: the remote command string below
	# contains that very text, so pkill -f matches the shell running it and
	# kills itself before the launch. Third occurrence of this bug class in one
	# session -- kill the recorded pid, and fall back to the 15-char comm that
	# pkill -x actually sees ("kms-nv12-plane-").
	#
	# And TRUNCATE THE LOG. Reading a stale /tmp/kms.log reported a previous
	# run's "WATCH THE PANEL ... 120s" as if it were this one's, which is how a
	# launch that never happened looked like a success.
	$SSH "p=\$(cat /tmp/kms.pid 2>/dev/null); [ -n \"\$p\" ] && kill -TERM \"\$p\" 2>/dev/null
	      pkill -x kms-nv12-plane- >/dev/null 2>&1
	      sleep 1; : > /tmp/kms.log; rm -f /tmp/kms.pid
	      setsid env ARMED=yes $PLANE_TEST $CARD $DWELL_S >/tmp/kms.log 2>&1 &
	      echo \$! > /tmp/kms.pid" >/dev/null 2>&1
	sleep 2
	local alive
	alive=$($SSH 'p=$(cat /tmp/kms.pid 2>/dev/null); [ -n "$p" ] && kill -0 "$p" 2>/dev/null && echo yes')
	say "  launched: ${alive:-NO -- the process is not running}"
	say "  log: $($SSH 'head -2 /tmp/kms.log 2>/dev/null' | tr '\n' ' ')"
	say "  card $CARD ($sz bytes), dwell ${DWELL_S}s"
	[ "$alive" = "yes" ] || { say "REFUSING: plane test did not start."; return 1; }
	if ! check_gates; then
		say ""
		say "REFUSING: the card is not demonstrably on the panel. Nothing was"
		say "written to the scaler. This is the check that was missing when a"
		say "whole sequence ran against a console screen."
		return 1
	fi
	say "  all gates pass -- the card is on the video plane."
	return 0
}

BASE=$(( 0x05180000 + INST * 0x100 ))
A00=$(printf '0x%08x' $(( BASE + 0x00 )))
A08=$(printf '0x%08x' $(( BASE + 0x08 )))
A14=$(printf '0x%08x' $(( BASE + 0x14 )))

say()  { printf '%s\n' "$*"; }
hex()  { printf '0x%08x' "$1"; }
rd()   { $SSH "busybox devmem $1 32" 2>/dev/null; }
ins()  { local w=$1 v=$2 p=$3 n=$4 m; m=$(( ((1<<n)-1) << p )); echo $(( (w & ~m) | ((v<<p) & m) )); }

# The firmware's own derivation. Kept here so the phase can never drift out of
# step with the ratio -- they are written together or not at all.
phase_for() { echo $(( ( UNITY + $1 ) >> 2 )); }

usage() { sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
[ $# -ge 1 ] || usage

mips=$($SSH 'busybox devmem 0x0306101c 32' 2>/dev/null)
case "$mips" in
*0x00000000) ;;
"") say "REFUSING: cannot read MIPS state"; exit 1 ;;
*) say "REFUSING: MIPS is alive ($mips)"; exit 1 ;;
esac

case "$1" in
card)
	bring_card_up || exit 1
	;;
set)
	[ $# -eq 2 ] || usage
	rv=$(( $2 ))
	o08=$(rd $A08); o14=$(rd $A14); o00=$(rd $A00)
	[ -n "$o08" ] || { say "cannot read the block"; exit 1; }
	ph=$(phase_for "$rv")
	w08=$(ins $(( o08 )) "$rv" 0 22)
	w00=$(ins $(( o00 )) "$ph" 0 16)
	w14=$(ins $(( o14 )) 0 27 1)
	# one ssh: bypass clear, ratio and phase land together
	$SSH "busybox devmem $A14 32 $(hex $w14); busybox devmem $A08 32 $(hex $w08); busybox devmem $A00 32 $(hex $w00)" >/dev/null 2>&1
	g08=$(rd $A08); g00=$(rd $A00); g14=$(rd $A14)
	f=$(awk -v r="$rv" -v u="$UNITY" 'BEGIN{printf "%.3f", u/r}')
	say "instance $INST  ratio_h $(printf '0x%06x' $rv)  phase $(printf '0x%04x' $ph)"
	say "  0x14 $g14   0x08 $g08   0x00 $g00"
	[ "$(( g08 & 0x3fffff ))" -eq "$rv" ] && say "  readback OK" || say "  READBACK MISMATCH"
	say ""
	say "  under the current model this is ${f}x horizontal scale"
	if [ "$rv" -lt "$UNITY" ]; then
		say "  expect: circles WIDER than tall, ticks spread, right border/columns clipped away"
	elif [ "$rv" -gt "$UNITY" ]; then
		say "  expect: circles TALLER than wide, ticks compressed, ALL FOUR BORDER EDGES PRESENT"
		say "  (a compressed image cannot overflow the clip window -- that is the positive)"
	else
		say "  unity: expect no change from baseline"
	fi
	say ""
	say "Take the photograph now. No hurry -- the card is static and held."
	;;
show)
	say "instance $INST, base $(hex $BASE)"
	for o in 0x00 0x04 0x08 0x14 0x20 0x2c 0x30 0x34 0x38 0x3c 0x40 0x44 0x50; do
		printf '  +%-6s %s\n' "$o" "$(rd $(printf '0x%08x' $(( BASE + o ))))"
	done
	;;
restore)
	o08=$(rd $A08); o00=$(rd $A00); o14=$(rd $A14)
	w08=$(ins $(( o08 )) "$UNITY" 0 22)
	w00=$(ins $(( o00 )) "$(phase_for $UNITY)" 0 16)
	w14=$(ins $(( o14 )) 1 27 1)
	$SSH "busybox devmem $A00 32 $(hex $w00); busybox devmem $A08 32 $(hex $w08); busybox devmem $A14 32 $(hex $w14)" >/dev/null 2>&1
	say "restored: 0x14 $(rd $A14)  0x08 $(rd $A08)  0x00 $(rd $A00)"
	say "(expected 0x08000000 / 0x43010000 / 0x0F008000 on a cold-boot board)"
	;;
off)
	$SSH 'p=$(cat /tmp/kms.pid 2>/dev/null); [ -n "$p" ] && kill -TERM "$p" 2>/dev/null
	      pkill -x kms-nv12-plane- >/dev/null 2>&1; true' >/dev/null 2>&1
	say "card stopped. video source 0x05600010: $(rd 0x05600010)"
	;;
seq)
	shift
	HOLD=${HOLD:-10}
	RATIOS=${*:-"0x10000 0x14000 0x18000 0x20000 0x8000"}
	say "PLAN -- $(echo $RATIOS | wc -w) measurements"
	say ""
	for r in $RATIOS; do
		f=$(awk -v r=$(( r )) -v u="$UNITY" 'BEGIN{printf "%.3f", u/r}')
		printf '  ratio %-9s %sx  %s\n' "$(printf '0x%x' $(( r )))" "$f" \
			"$(awk -v r=$(( r )) -v u="$UNITY" 'BEGIN{print (r<u)?"magnify":(r>u)?"COMPRESS":"baseline"}')"
	done
	say ""
	say "  Each measurement is: ${MARK_S}s FLAT BLUE cue, then ${HOLD}s of card."
	say "  SHOOT WHEN THE BLUE CLEARS. Do not shoot on a clock -- the cue is the"
	say "  signal, and it is authoritative even if this run is slower than planned."
	say "  (A printed schedule drifted ~8 s out of step last time; that is why.)"
	say ""
	say "  LOCK EXPOSURE AND FOCUS on your camera first. The cue is luma-matched"
	say "  to the card so it will not move the metering, but the scaled states"
	say "  themselves differ in brightness and auto-exposure will chase them --"
	say "  which is what made the last three photographs unusable."
	say ""
	# bring the card up once and prove it is on the panel before any ratio write
	bring_card_up || exit 1
	o08=$(rd $A08); o00=$(rd $A00); o14=$(rd $A14)
	say "saved: 0x14 $o14  0x08 $o08  0x00 $o00"
	say ""
	i=0
	for r in $RATIOS; do
		i=$(( i + 1 )); rv=$(( r )); ph=$(( ( UNITY + rv ) >> 2 ))
		# cue first, and set the ratio WHILE the cue is up so the card appears
		# already at the new value -- no transition visible on the card itself
		show_frame "$CUE" "$(( MARK_S + 2 ))"
		sleep 1
		w08=$(ins $(( o08 )) "$rv" 0 22)
		w00=$(ins $(( o00 )) "$ph" 0 16)
		if [ "$rv" -eq "$UNITY" ]; then w14=$(ins $(( o14 )) 1 27 1)
		else w14=$(ins $(( o14 )) 0 27 1); fi
		$SSH "busybox devmem $A14 32 $(hex $w14); busybox devmem $A08 32 $(hex $w08); busybox devmem $A00 32 $(hex $w00)" >/dev/null 2>&1
		sleep "$MARK_S"
		show_frame "$CARD" "$(( HOLD + 3 ))"
		sleep 1
		g=$(rd $A08)
		f=$(awk -v r="$rv" -v u="$UNITY" 'BEGIN{printf "%.3f", u/r}')
		if ! check_gates >/dev/null 2>&1; then
			say "  measurement $i: GATES FAILED after the cue -- card not on the panel."
			say "  Aborting; measurements 1..$(( i - 1 )) stand."
			rc=1; break
		fi
		printf '  measurement %d/%s  ratio %-9s %sx  readback %s  %s  << SHOOT NOW\n' \
			"$i" "$(echo $RATIOS | wc -w)" "$(printf '0x%x' $rv)" "$f" "$g" \
			"$([ "$(( g & 0x3fffff ))" -eq "$rv" ] && echo ok || echo MISMATCH)"
		sleep "$HOLD"
	done
	$SSH "busybox devmem $A00 32 $o00; busybox devmem $A08 32 $o08; busybox devmem $A14 32 $o14" >/dev/null 2>&1
	say ""
	say "restored: 0x14 $(rd $A14)  0x08 $(rd $A08)  0x00 $(rd $A00)"
	[ "$(rd $A14)" = "$o14" ] && [ "$(rd $A08)" = "$o08" ] && [ "$(rd $A00)" = "$o00" ] \
		&& say "  matches the pre-run values." \
		|| { say "  RESTORE MISMATCH -- record before power-cycling."; exit 2; }
	;;
*) usage ;;
esac
