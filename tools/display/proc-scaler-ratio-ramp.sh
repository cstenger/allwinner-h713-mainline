#!/usr/bin/env bash
# Isolate ratio_h on the two-axis scaler at 0x05180000. RUNS ON THE HOST.
#
# WHY THIS AND NOT proc-scaler-sweep.sh AGAIN. That script established the
# block is live on our DECD video raster (instances 0 and 1) --
# docs/reference/proc-scaler-video-2026-09-11/RESULT.md -- but it changed the
# ratio AND the output geometry together, and the result was a gross collapse:
# a flat light field with the picture crushed into a sliver at the right edge.
# So we know the block acts; we do not know which of the two things did it.
#
# This changes ONE thing. Geometry is left exactly as the firmware left it
# (in 1280x720, out 1280x720), ratio_v stays at unity, and only
#
#   0x14[27]   bypass          cleared once, at the start, and left clear
#   0x08[21:0] ratio_h         ramped
#   0x00[15:0] H phase         = (unity + ratio_h) >> 2, as the firmware derives it
#
# are touched. 0x2c / 0x30 / 0x34 / 0x40 (geometry), 0x3c (ratio_v) and 0x38
# (V phase) are NOT written.
#
# THE CONTROL STEP MATTERS. Step 0 clears the bypass with ratio_h still at unity.
# If the picture changes there, the bypass bit alone is doing it and the ramp
# below means nothing. That distinction was not available in the previous run.
#
# TWO DESIGN CHANGES THAT MAKE THE FILM READABLE
#
#   1. BATCHED WRITES. The previous run issued nine separate ssh calls per
#      engage at 0.62 s each, so every transition was smeared over 5.6 s and the
#      instance attribution had to be recovered by modelling the latency. Each
#      step here is ONE ssh call, so transitions are sub-second.
#   2. A MONOTONIC RAMP. Steps get progressively more aggressive, so the film
#      labels itself -- no blink-counting. If the picture compresses in
#      proportion, that is visible as a staircase.
#
# THE TIME BUDGET IS REAL. With --no-audio and PRIME scanout mpv free-runs at
# ~2.5x, so the 77 s clip yields only ~31 s of wall time before it loops and
# VAAPI dies (see the 09-11 result). Defaults are sized to finish inside that:
# 6 steps x ~3.2 s plus ~6 s of startup is about 25 s. The raster is re-checked
# after every step and the run aborts the moment it is lost, so a step that
# lands on the wrong raster is reported rather than believed.
#
# Every step is logged with its offset from mpv start, so the film can be
# aligned exactly instead of modelled.
#
#   usage: tools/display/proc-scaler-ratio-ramp.sh              # plan only
#          tools/display/proc-scaler-ratio-ramp.sh --engage     # WATCH/FILM
#          INST=1 DWELL=3 RATIOS="0xC000 0x8000" ... --engage
set -uo pipefail

BOARD=${BOARD:-192.168.4.1}
SSH="ssh -o ConnectTimeout=20 root@$BOARD"
INST=${INST:-0}                  # instances 0 and 1 are the live ones
DWELL=${DWELL:-2}
GATE_WAIT=${GATE_WAIT:-4}
# Descending, so the picture should compress progressively if the ratio drives it.
RATIOS=${RATIOS:-"0xC000 0xA000 0x8000 0x6000 0x4000"}
UNITY=$(( 0x10000 ))
DO_ENGAGE=0
rc=0

for arg in "$@"; do
	case "$arg" in
	--engage) DO_ENGAGE=1 ;;
	*) echo "unknown argument: $arg" >&2; exit 2 ;;
	esac
done

BASE=$(( 0x05180000 + INST * 0x100 ))
A00=$(printf '0x%08x' $(( BASE + 0x00 )))
A08=$(printf '0x%08x' $(( BASE + 0x08 )))
A14=$(printf '0x%08x' $(( BASE + 0x14 )))

say()  { printf '%s\n' "$*"; }
rule() { printf '%s\n' "------------------------------------------------------------"; }
hex()  { printf '0x%08x' "$1"; }
rd()   { $SSH "busybox devmem $1 32" 2>/dev/null; }
ins()  { local w=$1 v=$2 p=$3 n=$4 m; m=$(( ((1<<n)-1) << p )); echo $(( (w & ~m) | ((v<<p) & m) )); }

T0=0
el() { awk -v a="$T0" 'BEGIN{printf "%+6.1f", systime()-a}'; }

rule
say "PREFLIGHT"
$SSH true 2>/dev/null || { say "  cannot reach root@$BOARD"; exit 1; }
say "  kernel: $($SSH 'uname -r' 2>/dev/null)"
mips=$($SSH 'busybox devmem 0x0306101c 32' 2>/dev/null)
case "$mips" in
*0x00000000) say "  MIPS parked ($mips)" ;;
"") say "  REFUSING: could not read MIPS state."; exit 1 ;;
*) say "  REFUSING: MIPS is alive ($mips)."; exit 1 ;;
esac
case "$INST" in
0|1) say "  instance $INST (base $(hex $BASE)) -- confirmed live 2026-09-11" ;;
*)   say "  WARNING: instance $INST was NOT shown live on our raster."
     say "  Instance 2 is not in our path and 3 is untested. Continuing anyway." ;;
esac

# --------------------------------------------------------- read and plan
rule
say "CURRENT STATE (cold-boot / firmware values expected)"
O00=$(rd $A00); O08=$(rd $A08); O14=$(rd $A14)
for v in "$O00" "$O08" "$O14"; do
	[ -n "$v" ] || { say "  REFUSING: could not read the block."; exit 1; }
done
say "  +0x00 H phase   $O00"
say "  +0x08 H ratio   $O08   -> ratio_h $(printf '0x%06x' $(( $(( O08 )) & 0x3fffff )))"
say "  +0x14 bypass    $O14   -> bit27 $(( ( $(( O14 )) >> 27 ) & 1 ))"
say "  (geometry 0x2c/0x30/0x34/0x40, ratio_v 0x3c and V phase 0x38 are NOT touched)"

if [ "$(( $(( O08 )) & 0x3fffff ))" -ne "$UNITY" ]; then
	say "  REFUSING: ratio_h is not at unity, so this is not a clean baseline."
	exit 1
fi

W14=$(ins $(( O14 )) 0 27 1)          # bypass cleared, used by every step
rule
say "PLAN -- one ssh per step, geometry untouched"
printf '  %-8s %-12s %-12s %-12s  %s\n' "step" "+0x14" "+0x08" "+0x00" "note"
printf '  %-8s %-12s %-12s %-12s  %s\n' "0" "$(hex $W14)" "$O08" "$O00" \
	"CONTROL: bypass clear, ratio still unity"
i=0
for r in $RATIOS; do
	i=$(( i + 1 ))
	rv=$(( r ))
	ph=$(( ( UNITY + rv ) >> 2 ))
	w08=$(ins $(( O08 )) "$rv" 0 22)
	w00=$(ins $(( O00 )) "$ph" 0 16)
	carry=""
	[ "$ph" -ge $(( 0x8000 )) ] && carry=" (phase >= 0x8000: firmware would carry into 0x08[30:28])"
	printf '  %-8s %-12s %-12s %-12s  %s\n' "$i" "-" "$(hex $w08)" "$(hex $w00)" \
		"ratio_h $(printf '0x%06x' $rv) = $(awk -v a="$rv" -v u="$UNITY" 'BEGIN{printf "%.3f", a/u}')x$carry"
done

if [ "$DO_ENGAGE" -eq 0 ]; then
	rule
	say "Plan only. Re-run with --engage while filming."
	say "Expect a STAIRCASE if ratio_h drives the picture: progressively more"
	say "horizontal compression with each step. If step 0 already changes the"
	say "picture, the bypass bit is responsible and the ramp is uninterpretable."
	exit 0
fi

# ------------------------------------------------------------ raster gate
rule
say "RASTER GATE (DECD video)"
play=$($SSH "
	for c in ${CLIP:-} /root/leota-av-720p.mp4; do [ -f \"\$c\" ] && clip=\$c && break; done
	[ -n \"\${clip:-}\" ] || { echo NOCLIP; exit 1; }
	echo \"clip \$clip\"
	cat > /tmp/psr-play.sh <<'PLAY'
export LIBVA_DRIVER_NAME=v4l2_request
exec mpv --no-config --no-audio --vo=drm --hwdec=vaapi --loop-file=inf \
    --msg-level=all=status,vd=v,vo=v,ffmpeg=v CLIP
PLAY
	sed -i \"s|CLIP|\$clip|\" /tmp/psr-play.sh
	setsid bash /tmp/psr-play.sh </dev/null >/tmp/psr-play.log 2>&1 &
	echo \$! > /tmp/psr-play.pid
	sleep $GATE_WAIT
	st=\$(ls /sys/kernel/debug/dri/*/state 2>/dev/null | head -1)
	fbs=
	for i in 1 2 3 4 5 6; do
		fbs=\"\$fbs \$(grep -A2 '^plane\[38\]:' \"\$st\" 2>/dev/null | sed -n 's/.*fb=//p' | head -1)\"
		sleep 0.3
	done
	echo \"fbs\$fbs distinct \$(echo \$fbs | tr ' ' '\n' | sort -u | grep -c .)\"
" 2>&1)
T0=$(date +%s)
say "$play" | sed 's/^/  /'
stop_playback() {
	$SSH 'p=$(cat /tmp/psr-play.pid 2>/dev/null); [ -n "$p" ] && kill -TERM "$p" 2>/dev/null
	      pkill -TERM -x mpv; sleep 2; pkill -9 -x mpv' >/dev/null 2>&1
}
echo "$play" | grep -q NOCLIP && { say "  no clip. aborting."; exit 1; }
if ! echo "$play" | awk '/distinct/{for(i=1;i<=NF;i++) if($i=="distinct" && $(i+1)+0>=2) ok=1} END{exit !ok}'; then
	say "  video plane cycled < 2 framebuffers. aborting."; stop_playback; exit 1
fi
say "  scanout confirmed."

raster_ok() {
	$SSH '
		st=$(ls /sys/kernel/debug/dri/*/state 2>/dev/null | head -1)
		sw=$(grep -c "Using software decoding" /tmp/psr-play.log 2>/dev/null)
		fb=$(grep -A2 "^plane\[38\]:" "$st" 2>/dev/null | sed -n "s/.*fb=//p" | head -1)
		[ "${sw:-0}" -eq 0 ] && [ -n "$fb" ] && [ "$fb" != "0" ]
	' >/dev/null 2>&1
}
restore_all() { $SSH "busybox devmem $A00 32 $O00; busybox devmem $A08 32 $O08; busybox devmem $A14 32 $O14" >/dev/null 2>&1; }

# ----------------------------------------------------------------- the ramp
rule
say "RAMP. WATCH THE PANEL."
say "  Geometry is untouched throughout; only ratio_h and its phase move."
say "  Expect a STAIRCASE of increasing horizontal compression."
say "  Step offsets below are seconds since mpv started -- use them to align the film."
say ""

# step 0: the control -- bypass cleared, ratio still unity
$SSH "busybox devmem $A14 32 $(hex $W14)" >/dev/null 2>&1
got=$(rd $A14)
say "  [$(el)s] step 0  CONTROL: bypass cleared, ratio_h still unity   readback $got"
[ "$(( ${got:-0} ))" -ne "$W14" ] && { say "    bypass write did not stick -- that is the answer"; rc=1; }
sleep "$DWELL"
raster_ok || { say "  RASTER LOST after the control step -- aborting."; restore_all; stop_playback; exit 1; }

i=0
for r in $RATIOS; do
	i=$(( i + 1 ))
	rv=$(( r )); ph=$(( ( UNITY + rv ) >> 2 ))
	w08=$(ins $(( O08 )) "$rv" 0 22); w00=$(ins $(( O00 )) "$ph" 0 16)
	# ONE ssh: both writes land together, so the transition is crisp on film.
	$SSH "busybox devmem $A08 32 $(hex $w08); busybox devmem $A00 32 $(hex $w00)" >/dev/null 2>&1
	say "  [$(el)s] step $i  ratio_h $(printf '0x%06x' $rv) ($(awk -v a="$rv" -v u="$UNITY" 'BEGIN{printf "%.3f", a/u}')x)  phase $(printf '0x%04x' $ph)"
	sleep "$DWELL"
	if ! raster_ok; then
		say "  RASTER LOST after step $i -- steps 0..$(( i - 1 )) are on the good raster,"
		say "  step $i is NOT. Aborting."
		rc=1; break
	fi
done

# ------------------------------------------------------------------ restore
restore_all
rule
say "RESTORE"
r00=$(rd $A00); r08=$(rd $A08); r14=$(rd $A14)
say "  +0x00 $r00 (was $O00)"
say "  +0x08 $r08 (was $O08)"
say "  +0x14 $r14 (was $O14)"
if [ "$r00" != "$O00" ] || [ "$r08" != "$O08" ] || [ "$r14" != "$O14" ]; then
	say "  RESTORE FAILED -- record this before power-cycling."
	stop_playback; exit 2
fi
say "  back to the cold-boot values."
stop_playback
rule
say "Done. Send the film."
say "  a staircase       -> ratio_h drives the picture; the 09-11 collapse was"
say "                       the GEOMETRY registers, not the ratio."
say "  nothing until 0x14 -> the bypass bit alone is the actor."
say "  nothing at all     -> ratio_h is inert without matching geometry."
exit $rc
