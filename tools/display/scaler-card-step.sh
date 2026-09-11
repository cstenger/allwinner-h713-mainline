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
DWELL_MS=${DWELL_MS:-900000}          # 15 minutes; re-issue `card` if it lapses
UNITY=$(( 0x10000 ))

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
	sz=$($SSH "stat -c %s $CARD 2>/dev/null")
	[ -n "$sz" ] || { say "card not on the board: $CARD"; exit 1; }
	say "card $CARD ($sz bytes), holding ${DWELL_MS}ms"
	# background it: decd-client blocks for the dwell
	$SSH "setsid /root/decd-client show $CARD $DWELL_MS >/tmp/card.log 2>&1 &
	      echo \$! > /tmp/card.pid" >/dev/null 2>&1
	sleep 3
	say "decd-client: $($SSH 'tail -2 /tmp/card.log 2>/dev/null' | tr '\n' ' ')"
	say "video source 0x05600010: $(rd 0x05600010)"
	say ""
	say "Look at the panel. The card should be up and STILL before any ratio is"
	say "set -- if it is not, stop here; a ratio measured against a card that is"
	say "not actually displayed is the same mistake as the 09-10 stills."
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
	$SSH '/root/decd-client stop >/dev/null 2>&1; p=$(cat /tmp/card.pid 2>/dev/null); [ -n "$p" ] && kill -TERM "$p" 2>/dev/null; true' >/dev/null 2>&1
	say "card stopped. video source 0x05600010: $(rd 0x05600010)"
	;;
seq)
	shift
	HOLD=${HOLD:-12}
	RATIOS=${*:-"0x10000 0x14000 0x18000 0x20000 0x8000"}
	set -- $RATIOS
	n=$#
	say "SCHEDULE -- $n windows of ${HOLD}s, about $(( n * HOLD + 8 ))s total"
	say ""
	i=0; t=8
	for r in $RATIOS; do
		i=$(( i + 1 ))
		f=$(awk -v r=$(( r )) -v u="$UNITY" 'BEGIN{printf "%.3f", u/r}')
		printf '  photo %d   t+%3ds..%3ds   ratio %-9s  %sx  %s\n' \
			"$i" "$t" "$(( t + HOLD ))" "$(printf '0x%x' $(( r )))" "$f" \
			"$(awk -v r=$(( r )) -v u="$UNITY" 'BEGIN{print (r<u)?"magnify":(r>u)?"COMPRESS":"baseline"}')"
		t=$(( t + HOLD ))
	done
	say ""
	say "  Shoot once in the MIDDLE of each window -- roughly every ${HOLD}s."
	say "  A shot that lands in a transition will read an unexpected factor and"
	say "  gets discarded; it does not spoil the run."
	say ""
	# card first; the baseline photo doubles as proof it was actually displayed,
	# so no separate confirmation step is needed
	sz=$($SSH "stat -c %s $CARD 2>/dev/null")
	[ -n "$sz" ] || { say "card not on the board: $CARD"; exit 1; }
	$SSH "setsid /root/decd-client show $CARD $DWELL_MS >/tmp/card.log 2>&1 &
	      echo \$! > /tmp/card.pid" >/dev/null 2>&1
	sleep 4
	say "card up: source 0x05600010 = $(rd 0x05600010)   $($SSH 'tail -1 /tmp/card.log 2>/dev/null')"
	o08=$(rd $A08); o00=$(rd $A00); o14=$(rd $A14)
	say "saved: 0x14 $o14  0x08 $o08  0x00 $o00"
	say ""
	say "STARTING. First window opens in 4s."
	sleep 4
	T0=$(date +%s)
	i=0
	for r in $RATIOS; do
		i=$(( i + 1 )); rv=$(( r )); ph=$(( ( UNITY + rv ) >> 2 ))
		w08=$(ins $(( o08 )) "$rv" 0 22)
		w00=$(ins $(( o00 )) "$ph" 0 16)
		if [ "$rv" -eq "$UNITY" ]; then
			w14=$(ins $(( o14 )) 1 27 1)      # baseline: bypass SET, true cold state
		else
			w14=$(ins $(( o14 )) 0 27 1)
		fi
		$SSH "busybox devmem $A14 32 $(hex $w14); busybox devmem $A08 32 $(hex $w08); busybox devmem $A00 32 $(hex $w00)" >/dev/null 2>&1
		g=$(rd $A08)
		printf '  [t+%3ds] photo %d  ratio %-9s  readback %s  %s\n' \
			"$(( $(date +%s) - T0 ))" "$i" "$(printf '0x%x' $rv)" "$g" \
			"$([ "$(( g & 0x3fffff ))" -eq "$rv" ] && echo ok || echo MISMATCH)"
		sleep "$HOLD"
	done
	# restore
	$SSH "busybox devmem $A00 32 $o00; busybox devmem $A08 32 $o08; busybox devmem $A14 32 $o14" >/dev/null 2>&1
	say ""
	say "restored: 0x14 $(rd $A14)  0x08 $(rd $A08)  0x00 $(rd $A00)"
	if [ "$(rd $A14)" = "$o14" ] && [ "$(rd $A08)" = "$o08" ] && [ "$(rd $A00)" = "$o00" ]; then
		say "  matches the pre-run values."
	else
		say "  RESTORE MISMATCH -- record this before power-cycling."
		exit 2
	fi
	say "card left up; run 'off' to release DECD."
	;;
*) usage ;;
esac
