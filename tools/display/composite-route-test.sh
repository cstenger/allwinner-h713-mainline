#!/usr/bin/env bash
# Validate the 1.333x half of the composite 1080p->720p route: does the proc
# upscaler at 0x05180000 magnify a 960x544 region to a full, unclipped
# 1280x720 when its GEOMETRY registers are set? RUNS ON THE HOST.
#
# WHY THIS TEST, AND WHY IT IS SHAPED THIS WAY.
#
# The composite route is: VE power-of-two scale-down to 960x544 (hardware
# confirmed, docs/reference/ve-scaledown-2026-09-11/RESULT.md), then this block
# magnifying by 1/ratio (hardware confirmed, two-axis-scaler-0x05180000). Both
# halves are proven INDIVIDUALLY. What has never been tested is this block with
# its geometry registers programmed -- every previous run deliberately left
# 0x2c/0x30/0x34 alone, and the magnified picture came back CLIPPED to a
# hard-edged rectangle.
#
# Reading those registers on the live raster sharpens that from a hunch into a
# prediction: 0x34 holds 0x050002D0 = {1280, 720} and 0x2c/0x30 hold 1280/720 in
# their low halves. So the block was being told "your input window is 1280x720"
# while the ratio said magnify -- which produces exactly a clipped, magnified
# view of a 1280x720 window. Setting 0x34 to the real input size is the fix this
# test checks.
#
# It deliberately does NOT need a 960x544 source. kms-nv12-plane-test hardcodes
# 1280x720 (WIDTH/HEIGHT in its .c), and the KMS driver's atomic_check rejects
# any other framebuffer size outright -- so a real 960x544 source needs driver
# work. But the question here is purely geometric: can this block take a
# 960x544 input window and magnify it to fill 1280x720 without clipping? Asking
# it to magnify a 960x544 REGION of the existing 1280x720 card is the same
# configuration, and it needs no new source and no kernel change.
#
# If this passes, the composite route is viable and the remaining work is
# plumbing. If it comes back clipped, the route is dead and so is the last
# no-GPU option.
#
# HAZARDS OBSERVED BEFORE, all still live:
#   * Nothing may be written to the scaler until the card is DEMONSTRABLY on the
#     panel. A five-step sequence once ran against a console login prompt.
#   * `pkill -f kms-nv12-plane-test` kills this script's own ssh session. Use
#     the pid file, or `pkill -x kms-nv12-plane-` (15-char comm).
#   * Read back every write. A silently-refused register makes a null result
#     mean nothing.
#   * Confirm the logo/card is visible before each visible step -- U-Boot prints
#     "logo published" on a black boot too.
#
#   composite-route-test.sh card       put the 1280x720 card up, verify gates
#   composite-route-test.sh set        program geometry + both ratios, hold
#   composite-route-test.sh show       read the whole block back
#   composite-route-test.sh restore    unity ratios, bypass set, geometry back
#   composite-route-test.sh off        release the plane
set -uo pipefail

BOARD=${BOARD:-192.168.4.1}
SSH="ssh -o ConnectTimeout=20 root@$BOARD"
INST=${INST:-0}
BASE=$(( 0x05180000 + INST * 0x100 ))
CARD=${CARD:-/root/scaler-testcard-1280x720.nv12}
PLANE_TEST=${PLANE_TEST:-/root/kmsnv12/kms-nv12-plane-test}
DWELL_S=${DWELL_S:-300}
UNITY=$(( 0x10000 ))

# The composite route's second stage. IN is what the VE hands us; OUT is the
# panel. ratio = unity * in/out, because this block magnifies by 1/ratio.
IN_W=${IN_W:-960}   ; IN_H=${IN_H:-544}
OUT_W=${OUT_W:-1280}; OUT_H=${OUT_H:-720}
# 0x34 packs the input size as (w << 16) | h. That is not a guess: on the live
# 1280x720 raster it reads 0x050002D0 = {1280, 720}. Kept selectable anyway.
PACK=${PACK:-wh}

say(){ printf '%s\n' "$*"; }
rd(){ $SSH "busybox devmem $(printf '0x%08x' $1) 32" 2>/dev/null; }
wr(){ $SSH "busybox devmem $(printf '0x%08x' $1) 32 $(printf '0x%08x' $2)" >/dev/null 2>&1; }

# Write, then read back, and refuse to continue silently if it did not stick.
wrv(){
	local a=$1 v=$2 got
	wr "$a" "$v"
	got=$(rd "$a")
	printf '    %#010x <- %#010x   reads %s%s\n' "$a" "$v" "$got" \
	       "$( [ "$got" = "$(printf '0x%08x' $v)" ] || echo '   *** DID NOT STICK')"
	[ "$got" = "$(printf '0x%08x' $v)" ]
}

check_gates(){
	local src ybase sel plane bad=0
	src=$(rd 0x05600010); ybase=$(rd 0x05600070); sel=$(rd 0x051c006c)
	plane=$($SSH 'grep -A2 "^plane\[38\]" /sys/kernel/debug/dri/0/state 2>/dev/null | tr -d " \t" | tr "\n" " "' 2>/dev/null)
	[ "$src" = "0x03000013" ] || { say "  GATE FAIL video source $src (want 0x03000013)"; bad=1; }
	[ "$ybase" != "0x00000000" ] || { say "  GATE FAIL Y base is zero -- no frame behind the source"; bad=1; }
	[ "$sel" = "0x39000000" ] || { say "  GATE FAIL selector $sel (want 0x39000000 = video)"; bad=1; }
	case "$plane" in *crtc=crtc-0*) ;; *) say "  GATE FAIL plane 38 not on a crtc: $plane"; bad=1;; esac
	case "$plane" in *fb=0\ *|*fb=0) say "  GATE FAIL plane 38 has fb=0"; bad=1;; esac
	return $bad
}

bring_card_up(){
	local sz alive
	sz=$($SSH "stat -c %s $CARD 2>/dev/null")
	[ -n "$sz" ] || { say "card not on the board: $CARD"; return 1; }
	[ -n "$($SSH "test -x $PLANE_TEST && echo y")" ] || { say "missing $PLANE_TEST"; return 1; }
	# NOT pkill -f: the remote command string contains the pattern and pkill -f
	# would match the shell running it.
	$SSH "p=\$(cat /tmp/kms.pid 2>/dev/null); [ -n \"\$p\" ] && kill -TERM \"\$p\" 2>/dev/null
	      pkill -x kms-nv12-plane- >/dev/null 2>&1
	      sleep 1; : > /tmp/kms.log; rm -f /tmp/kms.pid
	      setsid env ARMED=yes $PLANE_TEST $CARD $DWELL_S >/tmp/kms.log 2>&1 &
	      echo \$! > /tmp/kms.pid" >/dev/null 2>&1
	sleep 2
	alive=$($SSH 'p=$(cat /tmp/kms.pid 2>/dev/null); [ -n "$p" ] && kill -0 "$p" 2>/dev/null && echo yes')
	say "  launched: ${alive:-NO -- process not running}"
	say "  card $CARD ($sz bytes), dwell ${DWELL_S}s"
	[ "$alive" = "yes" ] || { say "REFUSING: plane test did not start."; return 1; }
	check_gates || { say ""; say "REFUSING: the card is not demonstrably on the panel."; \
	                 say "Nothing was written to the scaler."; return 1; }
	say "  gates OK -- the card is on the glass"
}

save_block(){
	$SSH "for o in 0x00 0x08 0x14 0x2c 0x30 0x34 0x38 0x3c 0x40; do \
	        printf '%s ' \$(busybox devmem \$(printf '0x%08x' \$(( $BASE + o ))) 32); done"
}

case "${1:-}" in
card)
	say "== card up =="
	bring_card_up || exit 1
	say "  pre-run block: $(save_block)"
	;;

set)
	say "== program the composite route's upscale stage =="
	check_gates || { say "REFUSING: gates are not satisfied. Run 'card' first."; exit 1; }

	rh=$(( UNITY * IN_W / OUT_W ))
	rv=$(( UNITY * IN_H / OUT_H ))
	ph=$(( (UNITY + rh) >> 2 ))
	pv=$(( (UNITY + rv) >> 1 ))
	case "$PACK" in
	wh) insz=$(( (IN_W << 16) | IN_H ));;
	hw) insz=$(( (IN_H << 16) | IN_W ));;
	*)  say "PACK must be wh or hw"; exit 2;;
	esac
	say "  in ${IN_W}x${IN_H} -> out ${OUT_W}x${OUT_H}"
	say "  ratio_h $(printf '%#x' $rh) (magnify $(python3 -c "print(f'{$OUT_W/$IN_W:.4f}')")x)"
	say "  ratio_v $(printf '%#x' $rv) (magnify $(python3 -c "print(f'{$OUT_H/$IN_H:.4f}')")x)"
	say "  0x34 packing: $PACK -> $(printf '%#010x' $insz)"
	say "  saved: $(save_block)"

	# Geometry first, then ratios, then release the bypass -- so the block is
	# never live with a half-written configuration.
	# 0x2c and 0x30 carry non-zero UPPER halves on the live raster
	# (0x0035xxxx and 0x0001xxxx observed), so touch only [15:0].
	o=$(rd $(( BASE + 0x2c ))); wrv $(( BASE + 0x2c )) $(( (o & ~0xffff) | OUT_W )) || exit 1
	o=$(rd $(( BASE + 0x30 ))); wrv $(( BASE + 0x30 )) $(( (o & ~0xffff) | OUT_H )) || exit 1
	wrv $(( BASE + 0x34 )) "$insz"   || exit 1
	# The ratio registers are 22-bit fields and the phase registers 16-bit, and
	# BOTH carry live upper bits on this board (0x08 reads 0x43010000, 0x00
	# reads 0x0F008000). Writing the bare value would clobber them.
	o=$(rd $(( BASE + 0x08 ))); wrv $(( BASE + 0x08 )) $(( (o & ~0x3fffff) | rh )) || exit 1
	o=$(rd $(( BASE + 0x3c ))); wrv $(( BASE + 0x3c )) $(( (o & ~0x3fffff) | rv )) || exit 1
	o=$(rd $(( BASE + 0x00 ))); wrv $(( BASE + 0x00 )) $(( (o & ~0xffff)   | ph )) || exit 1
	o=$(rd $(( BASE + 0x38 ))); wrv $(( BASE + 0x38 )) $(( (o & ~0xffff)   | pv )) || exit 1
	b=$(rd $(( BASE + 0x14 )))
	wrv $(( BASE + 0x14 )) $(( b & ~(1 << 27) )) || exit 1

	say ""
	say "  HELD. Photograph the panel at leisure. What to look for:"
	say "    * all FOUR borders present  -> no clipping, the geometry fixed it"
	say "    * circles round, not oval   -> both axes magnified correctly"
	say "    * the card's own ruler reads the factor directly"
	say "  Then: composite-route-test.sh restore"
	;;

show)
	say "== block $(printf '%#x' $BASE) =="
	for o in 0x00 0x08 0x14 0x2c 0x30 0x34 0x38 0x3c 0x40; do
		printf '  +%s  %s\n' "$o" "$(rd $(( BASE + o )))"
	done
	;;

restore)
	say "== restore: unity ratios, bypass set =="
	o=$(rd $(( BASE + 0x08 ))); wrv $(( BASE + 0x08 )) $(( (o & ~0x3fffff) | UNITY ))
	o=$(rd $(( BASE + 0x3c ))); wrv $(( BASE + 0x3c )) $(( (o & ~0x3fffff) | UNITY ))
	o=$(rd $(( BASE + 0x00 ))); wrv $(( BASE + 0x00 )) $(( (o & ~0xffff) | ((UNITY+UNITY)>>2) ))
	o=$(rd $(( BASE + 0x38 ))); wrv $(( BASE + 0x38 )) $(( (o & ~0xffff) | ((UNITY+UNITY)>>1) ))
	o=$(rd $(( BASE + 0x2c ))); wrv $(( BASE + 0x2c )) $(( (o & ~0xffff) | OUT_W ))
	o=$(rd $(( BASE + 0x30 ))); wrv $(( BASE + 0x30 )) $(( (o & ~0xffff) | OUT_H ))
	wrv $(( BASE + 0x34 )) $(( (OUT_W << 16) | OUT_H ))
	b=$(rd $(( BASE + 0x14 )))
	wrv $(( BASE + 0x14 )) $(( b | (1 << 27) ))
	say "  block now: $(save_block)"
	;;

off)
	$SSH "p=\$(cat /tmp/kms.pid 2>/dev/null); [ -n \"\$p\" ] && kill -TERM \"\$p\" 2>/dev/null
	      pkill -x kms-nv12-plane- >/dev/null 2>&1; rm -f /tmp/kms.pid" >/dev/null 2>&1
	say "plane released"
	;;

*)
	sed -n '1,45p' "$0" | sed 's/^# \{0,1\}//'
	exit 2
	;;
esac
