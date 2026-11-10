#!/usr/bin/env bash
# Is the inline scaler at 0x05000000 usable from Linux? RUNS ON THE HOST.
#
# WHY THIS EXISTS. Static analysis of display.bin settled how stock scales
# 1080p to this 720p panel: the block at 0x05000000 (`tvdisp@5000000`), driven
# by the MIPS. A lui-immediate scan gives it 45 call sites -- more than any
# other display block -- and at those sites the firmware WRITES exactly the
# registers we sampled live: +0x174 (ratio 0x00400040), +0x178 (540), +0x1b8
# (1080), and a second coordinate space at +0x274/+0x278 (360)/+0x2b8 (720).
#
# Our KMS driver does not map that block. Before writing a line of driver code
# there are two questions, and both can be answered without an operator looking
# at the panel:
#
#   1. IS IT IN OUR PATH? If the block sees the pixels DECD fetches, something
#      in it must move when our playback runs. Phase 2 samples every register
#      before, during and after a real Linux DECD playback. A register that
#      moves only during playback is the block observing our traffic.
#
#   2. DOES IT RESPOND WITH THE MIPS PARKED? Our whole video path requires the
#      MIPS parked. A block that is clock-gated or held in reset in that
#      configuration cannot be programmed no matter what the firmware does with
#      it. Phase 3 is the project's writability triage: write, read back,
#      restore, verify the restore.
#
# WHAT A NEGATIVE LOOKS LIKE, stated up front so it cannot be explained away
# afterwards. The 2026-09-03 reading of this block ("inert, bit 31 never set")
# was taken during a 720p playback, where an inert scaler is expected whether
# or not it is in the path -- it never discriminated, and this script exists
# because that was the wrong measurement, not because the answer was wrong.
#   * Phase 2 finds NOTHING moving  -> the block does not see our pixels.
#     Either our route bypasses it, or it is gated. Phase 3 separates those.
#   * Phase 3 writes do not stick   -> gated or in reset with the MIPS parked.
#     Combined with a null phase 2, the Linux-driven scaler route is closed and
#     the GPU is the only remaining stage-1 scaler on this SoC.
#   * Phase 3 writes DO stick       -> the block is live and programmable from
#     Linux, and the driver question becomes where it sits on our route.
#
# SAFETY. Phases 1 and 2 are read-only. Phase 3 writes to live display hardware
# and is opt-in (--write). Every write is restored immediately and the restore
# is verified; a failed restore aborts the run and is reported as the serious
# result it is. The script refuses to run with the display MIPS alive, because
# live MIPS plus real Cedrus/DECD traffic is a reproducible whole-SoC hard lock
# with no watchdog recovery.
#
# PHASE 4 AND WHY IT NEEDS AN OPERATOR. Phases 1-3 cannot decide whether this
# block is on our path, and no future register read will either: it has no
# free-running state anywhere -- no counters, no status bits -- and both ratio
# registers sit at 0x00400040, unity. An inline pass-through configured to do
# nothing looks identical to a block that is not in the path at all. Two
# separate readings (2026-09-03's "inert", and this script's own first phase-2
# result) were reported as "not in our path" when all they showed was silence.
#
# So the discriminating test is visible, and it is the only one there is: the
# block is writable and at unity, so set a NON-unity ratio during a live
# playback and look at the panel. Picture changes => on our path, controllable
# from Linux. Picture does not change => genuinely unrouted.
#
#   usage: tools/display/scaler-probe.sh            # read-only, phases 1 and 2
#          tools/display/scaler-probe.sh --write    # adds the writability triage
#          tools/display/scaler-probe.sh --visible  # adds the ratio test (WATCH THE PANEL)
#          BOARD=192.168.4.1 HOLD=8 tools/display/scaler-probe.sh --visible
set -uo pipefail

BOARD=${BOARD:-192.168.4.1}
SSH="ssh -o ConnectTimeout=8 root@$BOARD"
SCALER=0x05000000
HOLD=${HOLD:-8}
DO_WRITE=0
DO_VISIBLE=0
rc=0

for arg in "$@"; do
	case "$arg" in
	--write) DO_WRITE=1 ;;
	--visible) DO_VISIBLE=1 ;;
	*) echo "unknown argument: $arg" >&2; exit 2 ;;
	esac
done

# The offsets the MIPS firmware actually touches, from the lui scan of
# display.bin. "w" = the firmware writes it (sw), "r" = read-only there (lw).
# Keeping the firmware's own split visible means a register that moves here but
# is never written there is immediately recognisable as status rather than
# configuration.
WROFFS="0004 0010 0018 001c 0030 0040 00f0 0138 0174 0178 01b4 01b8 0210 0224
        0274 0278 02b4 02b8 0434 0438 0444 044c 0468 0534 0538 0544 0550 0568
        0804 0808 080c 082c 0840 0844 0854 0858 085c 0860"
RDOFFS="0000 0008 000c 0014 0020 002c 0034 0318 0440 0490 0628 073c 07d0 07d4
        0900 09d4 0a00"
ALLOFFS="$(echo $WROFFS $RDOFFS | tr ' ' '\n' | sort -u | tr '\n' ' ')"

# One remote helper, sourced by each phase, so a sample is the same operation
# every time it is taken.
read -r -d '' REMOTE_LIB <<'EOF'
SCALER=0x05000000
sample() {   # sample <offsets...> -> "offset value" lines
	for o in "$@"; do
		printf "%s %s\n" "$o" "$(busybox devmem $((SCALER + 0x$o)) 32)"
	done
}
EOF

echo "=== preflight ==="
pre=$($SSH "
	echo \"uname   \$(uname -r)\"
	echo \"uptime  \$(cut -d' ' -f1 /proc/uptime)\"
	echo \"mips    \$(busybox devmem 0x0306101c 32)\"
	echo \"tcon_a  \$(busybox devmem 0x05880000 32)\"
	sleep 1
	echo \"tcon_b  \$(busybox devmem 0x05880000 32)\"
	echo \"select  \$(busybox devmem 0x051c006c 32)\"
	echo \"route   \$(busybox devmem 0x05140054 32)\"
	echo \"iommu   \$(busybox devmem 0x02010108 32)\"
" 2>&1)
[ -n "$pre" ] || { echo "    board unreachable at $BOARD"; exit 1; }
echo "$pre" | sed 's/^/    /'

mips=$(echo "$pre" | awk '/^mips/{print $2}')
case "$mips" in
0x00000000) ;;
*)
	echo
	echo "    REFUSING TO RUN: display MIPS is not parked ($mips)."
	echo "    Live MIPS + real Cedrus/DECD traffic hard-locks the SoC with no"
	echo "    watchdog. Boot the normal U-Boot 'auto' path, which quiesces it."
	exit 1
	;;
esac

# A moving TCON scan counter is what makes the rest of the run interpretable:
# if the raster is not clocking, "nothing moved" would mean nothing at all.
ta=$(echo "$pre" | awk '/^tcon_a/{print $2}')
tb=$(echo "$pre" | awk '/^tcon_b/{print $2}')
if [ "$ta" = "$tb" ]; then
	echo "    WARNING: TCON scan counter did not move ($ta). The raster may be"
	echo "    stopped, which would make a null phase-2 result meaningless."
	rc=1
else
	echo "    raster is scanning ($ta -> $tb)"
fi

echo
echo "=== phase 1: idle census ==="
echo "    three samples, 1 s apart, display idle. A register that moves here is"
echo "    free-running and cannot be read as a response to our traffic later."
idle=$($SSH "$REMOTE_LIB
	sample $ALLOFFS > /tmp/sc.a; sleep 1
	sample $ALLOFFS > /tmp/sc.b; sleep 1
	sample $ALLOFFS > /tmp/sc.c
	paste /tmp/sc.a /tmp/sc.b /tmp/sc.c" 2>&1)

echo "$idle" | awk -v w="$WROFFS" '
	BEGIN { n = split(w, a, /[ \n\t]+/); for (i = 1; i <= n; i++) if (a[i] != "") fw[a[i]] = 1 }
	NF >= 6 {
		tag = fw[$1] ? "w" : " "
		if ($2 != $4 || $4 != $6) { printf "    +0x%s %s  %s -> %s -> %s   MOVES\n", $1, tag, $2, $4, $6; moved++ }
		else                        { printf "    +0x%s %s  %s\n", $1, tag, $2 }
	}
	END { printf "\n    %d of %d registers move at idle\n", moved + 0, NR }'
FREE=$(echo "$idle" | awk 'NF>=6 && ($2!=$4 || $4!=$6) {printf "%s ", $1}')
[ -n "$FREE" ] && echo "    free-running: $FREE"

echo
echo "=== phase 2: does the block see our pixel traffic? ==="
during=$($SSH "$REMOTE_LIB
	# A clip with real DURATION, on purpose. leota-720p.h264 is 212 KB: mpv's
	# clock never leaves 00:00:00 and it spends the run seeking and looping, so
	# flips are sparse and the scanout gate below reads as a stalled plane.
	# Measure against continuous playback, not a few frames on repeat.
	for c in /root/leota-av-720p.mp4 /root/video-test/disp-720p.h265 \
	         /root/video-test/v02-1280x720-baseline.h264 \
	         /root/video-test/*.h264 /root/leota-720p.h264; do
		[ -f \"\$c\" ] && clip=\$c && break
	done
	[ -n \"\${clip:-}\" ] || { echo 'NOCLIP'; exit 1; }
	echo \"clip \$clip\"

	sample $ALLOFFS > /tmp/sc.before

	cat > /tmp/sc-play.sh <<'PLAY'
export LIBVA_DRIVER_NAME=v4l2_request
exec mpv --no-config --no-audio --vo=drm --hwdec=vaapi --loop-file=inf \
    --msg-level=all=v CLIP
PLAY
	sed -i \"s|CLIP|\$clip|\" /tmp/sc-play.sh
	setsid bash /tmp/sc-play.sh </dev/null >/tmp/sc-play.log 2>&1 &
	sleep 10

	# Prove the playback is actually scanning out before believing anything
	# the scaler window says. mpv logging the direct path proves selection,
	# not display: gate on the plane holding a framebuffer whose id CHANGES.
	#
	# Sample it SEVERAL times and count distinct ids. mpv cycles a pool of
	# only three framebuffers here, so two samples land on the same id about a
	# third of the time -- the first version of this gate did exactly that and
	# reported a stalled plane during a perfectly healthy playback.
	st=\$(ls /sys/kernel/debug/dri/*/state 2>/dev/null | head -1)
	pl=\$(sed -n 's/.*Using [a-z]* plane \([0-9]*\) as drmprime plane.*/\1/p' /tmp/sc-play.log | head -1)
	fbs=
	for i in 1 2 3 4 5 6; do
		fbs=\"\$fbs \$(grep -A2 \"^plane\[\${pl:-none}\]:\" \"\$st\" 2>/dev/null | sed -n 's/.*fb=//p' | head -1)\"
		sleep 0.3
	done
	ndistinct=\$(echo \$fbs | tr ' ' '\n' | sort -u | grep -c .)

	sample $ALLOFFS > /tmp/sc.during
	sleep 2
	sample $ALLOFFS > /tmp/sc.during2

	echo \"plane \${pl:-none} fbs\$fbs distinct \$ndistinct\"
	echo \"flipfails \$(grep -c 'Failed to queue DRM PRIME' /tmp/sc-play.log || true)\"

	pkill -x mpv 2>/dev/null
	sleep 3
	sample $ALLOFFS > /tmp/sc.after
	echo '---'
	paste /tmp/sc.before /tmp/sc.during /tmp/sc.during2 /tmp/sc.after" 2>&1)

if echo "$during" | grep -q NOCLIP; then
	echo "    no test clip on the board -- phase 2 skipped"
	rc=1
else
	echo "$during" | sed -n '1,3p' | sed 's/^/    /'
	playing=$(echo "$during" | awk '/^plane /{ for (i=1;i<=NF;i++) if ($i=="distinct" && $(i+1)+0 >= 2) print "yes" }')
	if [ "$playing" != "yes" ]; then
		echo "    WARNING: the video plane cycled fewer than two framebuffers, so"
		echo "    nothing new was scanned out. A null result below says nothing."
		rc=1
	else
		echo "    playback confirmed scanning out (plane cycles several fbs)"
	fi
	echo
	echo "$during" | sed -n '/^---$/,$p' | awk -v w="$WROFFS" -v free="$FREE" '
		BEGIN {
			n = split(w, a, /[ \n\t]+/);    for (i=1;i<=n;i++) if (a[i]!="") fw[a[i]]=1
			m = split(free, b, /[ \n\t]+/); for (i=1;i<=m;i++) if (b[i]!="") fr[b[i]]=1
		}
		NF >= 8 {
			tot++
			if (fr[$1]) next                       # free-running: not evidence
			if ($2 != $4 || $4 != $6 || $6 != $8) {
				printf "    +0x%s %s  %s | %s %s | %s   RESPONDS\n",
				       $1, fw[$1]?"w":" ", $2, $4, $6, $8
				hit++
			}
		}
		END {
			printf "\n    %d of %d non-free-running registers changed across the playback\n",
			       hit + 0, tot + 0
			if (hit + 0 == 0) {
				# Do NOT report this as "not in our path". The block has no
				# free-running state at all and both ratios sit at unity, so an
				# inline pass-through doing nothing produces exactly this null.
				# An earlier version of this script drew the stronger conclusion
				# and was wrong; phase 4 is the test that actually decides.
				print "    => INCONCLUSIVE. This block has no status or counter"
				print "       registers, and its ratios are at unity, so silence is"
				print "       what an inline pass-through looks like too. Nothing"
				print "       here distinguishes \"not in our path\" from \"in our"
				print "       path, doing nothing\". Run phase 4."
			} else
				print "    => the block responds to our playback -- it is on our path"
		}'
fi

if [ "$DO_WRITE" != 1 ] && [ "$DO_VISIBLE" != 1 ]; then
	echo
	echo "=== phase 3: skipped (read-only run) ==="
	echo "    re-run with --write to test whether the block accepts writes with"
	echo "    the MIPS parked. That phase writes live display hardware."
	echo "=== phase 4: skipped (read-only run) ==="
	echo "    re-run with --visible for the ratio test. It needs someone looking"
	echo "    at the panel -- no register can answer it."
	exit $rc
fi

if [ "$DO_WRITE" = 1 ]; then

echo
echo "=== phase 3: writability triage (MIPS parked) ==="
echo "    write, read back, restore, verify. 0xDEADBEEF first -- a register that"
echo "    will not take any write cannot be a lever. Masked or encoded controls"
echo "    reject 0xDEADBEEF but accept a legal value, so each one gets a second"
echo "    attempt with a legal encoding before it is called read-only."
# offset : legal-alternate : what it is
#
# Every alternate is a value THIS HARDWARE CURRENTLY HOLDS in the equivalent
# register of the other coordinate space (A: 540/1080, B: 360/720), rather than
# a value invented here. A masked or encoded control that rejects 0xDEADBEEF
# will accept one of these if it accepts anything at all, and none of them can
# be an illegal encoding, because the block is holding it right now.
TRIAGE="0174:0x00800080:ratio,space-A
0178:0x60020168:coord,space-A
01b8:0x600202d0:coord,space-A
0274:0x00800080:ratio,space-B
0278:0x6002021c:coord,space-B
02b8:0x60020438:coord,space-B"

for row in $TRIAGE; do
	off=${row%%:*}; rest=${row#*:}; legal=${rest%%:*}; what=${rest#*:}
	out=$($SSH "
		a=\$(busybox devmem $((SCALER + 0x$off)) 32)
		busybox devmem $((SCALER + 0x$off)) 32 0xDEADBEEF
		b=\$(busybox devmem $((SCALER + 0x$off)) 32)
		busybox devmem $((SCALER + 0x$off)) 32 \$a
		c=\$(busybox devmem $((SCALER + 0x$off)) 32)
		d=- ; e=-
		if [ \"\$b\" = \"\$a\" ]; then
			busybox devmem $((SCALER + 0x$off)) 32 $legal
			d=\$(busybox devmem $((SCALER + 0x$off)) 32)
			busybox devmem $((SCALER + 0x$off)) 32 \$a
			e=\$(busybox devmem $((SCALER + 0x$off)) 32)
		fi
		echo \"\$a \$b \$c \$d \$e\"" 2>&1)
	set -- $out
	orig=${1:-?}; deadbeef=${2:-?}; rest1=${3:-?}; legalrb=${4:-?}; rest2=${5:-?}

	verdict="read-only"
	[ "$deadbeef" != "$orig" ] && verdict="WRITABLE (0xDEADBEEF)"
	[ "$legalrb" != "-" ] && [ "$legalrb" != "$orig" ] && verdict="WRITABLE (legal value only)"

	printf "    +0x%s  %-18s orig %s  beef %s  legal %s  -> %s\n" \
	       "$off" "$what" "$orig" "$deadbeef" "$legalrb" "$verdict"

	for r in "$rest1" "$rest2"; do
		[ "$r" = "-" ] && continue
		if [ "$r" != "$orig" ]; then
			echo "    *** RESTORE FAILED at +0x$off: $orig -> $r"
			echo "    *** Stopping. Treat the display as in an unknown state;"
			echo "    *** a cold power cycle is the recovery, not a reboot."
			exit 3
		fi
	done
done

post=$($SSH "echo \"iommu \$(busybox devmem 0x02010108 32)\"; \
             echo \"select \$(busybox devmem 0x051c006c 32)\"" 2>&1)
echo
echo "    after: $(echo "$post" | tr '\n' ' ')"
echo "    all writes restored and verified"

else
	echo
	echo "=== phase 3: skipped (not requested) ==="
fi

if [ "$DO_VISIBLE" != 1 ]; then
	echo
	echo "=== phase 4: skipped (not requested) ==="
	exit $rc
fi

echo
echo "=== phase 4: the ratio test — WATCH THE PANEL ==="
echo "    The only test that can decide this. Both ratio registers are at unity"
echo "    (0x00400040, where 0x40 is 1:1). We put a 2:1 ratio in one at a time"
echo "    during live 720p playback and hold it for ${HOLD}s."
echo
echo "    Space A carries a 1080-tall image (luma 1080 at +0x1b8, chroma 540 at"
echo "    +0x178); space B carries a 720-tall one (720 at +0x2b8, 360 at +0x278)."
echo "    Our content is 720p, so SPACE B is the one that should matter — space A"
echo "    is tested second as the control. If B changes the picture and A does"
echo "    not, that is the block acting on our stream specifically."

# Restore is not best-effort. If the script is interrupted mid-hold, the
# register must still go back, so the trap owns it and re-reads to confirm.
VIS_OFF=""
VIS_ORIG=""
restore_visible() {
	[ -n "$VIS_OFF" ] || return 0
	back=$($SSH "busybox devmem $((SCALER + 0x$VIS_OFF)) 32 $VIS_ORIG; \
	             busybox devmem $((SCALER + 0x$VIS_OFF)) 32" 2>&1 | tail -1)
	if [ "$back" != "$VIS_ORIG" ]; then
		echo "    *** RESTORE FAILED at +0x$VIS_OFF: wanted $VIS_ORIG, read $back"
		echo "    *** A cold power cycle is the recovery, not a reboot."
	else
		echo "    restored +0x$VIS_OFF to $VIS_ORIG (verified)"
	fi
	VIS_OFF=""
}
trap 'echo; echo "    interrupted -- restoring"; restore_visible; pkill -f sc-vis >/dev/null 2>&1; exit 130' INT TERM
trap 'restore_visible' EXIT

echo
echo "    starting playback..."
vis=$($SSH "
	for c in /root/leota-av-720p.mp4 /root/video-test/disp-720p.h265 \
	         /root/video-test/v02-1280x720-baseline.h264; do
		[ -f \"\$c\" ] && clip=\$c && break
	done
	[ -n \"\${clip:-}\" ] || { echo 'NOCLIP'; exit 1; }
	cat > /tmp/sc-vis.sh <<'PLAY'
export LIBVA_DRIVER_NAME=v4l2_request
exec mpv --no-config --no-audio --vo=drm --hwdec=vaapi --loop-file=inf \
    --msg-level=all=v CLIP
PLAY
	sed -i \"s|CLIP|\$clip|\" /tmp/sc-vis.sh
	setsid bash /tmp/sc-vis.sh </dev/null >/tmp/sc-vis.log 2>&1 &
	sleep 10
	st=\$(ls /sys/kernel/debug/dri/*/state 2>/dev/null | head -1)
	pl=\$(sed -n 's/.*Using [a-z]* plane \([0-9]*\) as drmprime plane.*/\1/p' /tmp/sc-vis.log | head -1)
	fbs=
	for i in 1 2 3 4 5 6; do
		fbs=\"\$fbs \$(grep -A2 \"^plane\[\${pl:-none}\]:\" \"\$st\" 2>/dev/null | sed -n 's/.*fb=//p' | head -1)\"
		sleep 0.3
	done
	echo \"clip \$clip\"
	echo \"distinct \$(echo \$fbs | tr ' ' '\n' | sort -u | grep -c .)\"" 2>&1)

echo "$vis" | sed 's/^/    /'
nd=$(echo "$vis" | awk '/^distinct/{print $2}')
if [ "${nd:-0}" -lt 2 ]; then
	echo
	echo "    ABORTING phase 4: playback is not scanning out (distinct fbs ${nd:-0})."
	echo "    Changing a ratio against a frozen picture would prove nothing, and a"
	echo "    null result would be misread as 'the scaler does nothing'."
	$SSH "pkill -f sc-vis; pkill -x mpv" >/dev/null 2>&1
	exit 1
fi
echo "    playback confirmed scanning out"

for probe in "0274:space B (720-tall — our content)" "0174:space A (1080-tall — control)"; do
	off=${probe%%:*}; label=${probe#*:}
	VIS_OFF=$off
	VIS_ORIG=$($SSH "busybox devmem $((SCALER + 0x$off)) 32" 2>&1)
	echo
	echo "    ---- +0x$off, $label ----"
	echo "    baseline $VIS_ORIG. Look at the panel and note what you see NOW."
	sleep 3
	echo "    >>> WRITING 0x00800080 (2:1) — WATCH THE PANEL FOR ${HOLD}s <<<"
	rb=$($SSH "busybox devmem $((SCALER + 0x$off)) 32 0x00800080; \
	           busybox devmem $((SCALER + 0x$off)) 32" 2>&1 | tail -1)
	echo "    held value reads $rb"
	sleep "$HOLD"
	echo "    >>> RESTORING <<<"
	restore_visible
	sleep 2
done

trap - EXIT INT TERM
# Stop the player FIRST, and never pipe this command into head: a host-side
# `head -1` closes the pipe after the first line, SIGPIPEs the ssh client and
# tears the session down before the later commands in the chain run. That is
# not hypothetical -- it left mpv alive holding DRM master for three minutes
# after a run, which stopped fbcon redrawing and looked like a wedged panel.
# SIGTERM, not SIGKILL, so mpv releases DRM and the console comes back.
cleanup=$($SSH "pkill -TERM -x mpv 2>/dev/null; sleep 3;
                echo \"iommu \$(busybox devmem 0x02010108 32)\";
                echo \"mpv_left \$(pgrep -x mpv | wc -l)\";
                echo \"selector \$(busybox devmem 0x051c006c 32)\"" 2>&1)
echo
echo "$cleanup" | sed 's/^/    /'
case "$cleanup" in
*"mpv_left 0"*) ;;
*) echo "    WARNING: a player is still holding DRM master; the console will not"
   echo "    redraw until it exits. Kill it before judging what is on the panel." ;;
esac
echo
echo "    WHAT DID YOU SEE?"
echo "      picture changed on space B only  -> the scaler is on our path and acts"
echo "                                          on our stream. 1080p is driver work."
echo "      picture changed on both          -> on our path; the two spaces are not"
echo "                                          split the way we read them."
echo "      no change on either              -> INCONCLUSIVE, not 'unrouted'. See below."
echo
echo "    A NULL HERE IS WEAKER THAN IT LOOKS, and this phase should not be quoted"
echo "    as proof the block is off our path. The firmware does not program a ratio"
echo "    on its own: the routine at 0x8b1a4810 read-modify-writes roughly twenty"
echo "    registers across both coordinate spaces and the 0x08xx group, and ENDS on"
echo "    +0x0040 and +0x0138 -- the shape of an enable or a shadow-register commit."
echo "    A ratio written in isolation may sit in the register, read back correctly,"
echo "    and never be latched into the pixel path. Three readings survive a null:"
echo "      (a) the block is not on our path;"
echo "      (b) it is, but the value was never committed;"
echo "      (c) the ratio encoding is not the two 16-bit fields we assumed."
echo "    Separating them means replaying more of the firmware's sequence, not"
echo "    writing one register harder."
exit $rc
