#!/bin/sh
# Does the firmware's geometry rewrite on submit break composition?
# RUNS ON THE BOARD, DECD-exclusive kernel, MIPS alive.
#
# A DECD submit kills the display output path for the rest of the boot: the
# panel goes black and stays black even with source 0 disabled and latched, the
# OSD channel enabled on a buffer that demonstrably still holds an image, both
# commit latches consuming, and the raster running. See
# docs/reference/decd-submit-breaks-scanout-2026-08-30.md.
#
# The hypothesis this tests: the firmware rewrites the geometry registers on
# submit and rewrites them wrong. After a submit, 0x05600030 and 0x0560004c read
# 0x0354 = 852 in the low half and 480/240 in the high half -- 852x480 on a
# 1280x720 panel -- while 0x05600020 still reads 1280x720 minus one and the
# stride is 1280. Stock's playback capture has 0x0560004c = 0x02D00500. If
# composition uses that geometry it would break every layer, which is what we
# see and would explain why clearing source 0's enable did not restore the OSD.
#
# So: capture the geometry while the panel demonstrably works, submit one frame,
# and put the geometry back. If the OSD returns, the rewrite is the mechanism.
#
# The submit and the restore are in one script deliberately. Doing them as two
# ssh commands leaves the board sitting in the broken state across a round trip,
# and this state hard-locks -- twice in five submits so far, always inside the
# submit. If it locks, the restore never runs and the log still holds everything
# up to that point.
#
#   usage: geom-restore-test.sh mark     paint a marker, then LOOK at the panel
#          geom-restore-test.sh run      submit, then restore the geometry
set -u

FRAME=${FRAME:-/root/decd-test-frame.nv12}
CLIENT=${CLIENT:-/root/decd-client}
FILL=${FILL:-/root/mem-fill}
LOG=/root/geom-test-$(date +%Y%m%d-%H%M%S).log

GEOM="0x05600020 0x05600024 0x05600030 0x05600040 0x05600044 0x05600048 0x0560004c"

say() { echo "$@" | tee -a "$LOG"; sync; }
reg() { printf '  %-12s %s\n' "$1" "$(busybox devmem "$1" 32 2>/dev/null)" | tee -a "$LOG"; sync; }

case "${1:-}" in
mark)
	SRC=$(busybox devmem 0x05600178 32)
	echo "OSD channel source is $SRC"
	echo "painting a red band over the top third of it"
	# The marker has to be unmistakable. Shades of black are a judgement
	# call; a red band over white is not.
	"$FILL" "$(echo "$SRC" | sed 's/^0x//' | tr 'A-F' 'a-f')" 100000 00ff0000 1
	echo "now LOOK at the panel. It must show the red band before the"
	echo "experiment means anything -- that is the whole point of the marker."
	;;
run)
	say "=== geometry-restore test $(date) ==="
	say ""
	say "--- healthy geometry, panel confirmed working ---"
	for r in 0x05600010 $GEOM; do reg $r; done
	say ""

	# Snapshot the healthy values so the restore uses what was actually
	# there, not what a previous boot happened to have.
	SAVED=""
	for r in $GEOM; do
		SAVED="$SAVED $r=$(busybox devmem $r 32)"
	done
	say "saved:$SAVED"
	say ""

	say "--- submit (the lock window) ---"
	DECD_FMT=0 timeout 6s stdbuf -oL -eL "$CLIENT" show "$FRAME" 300 \
	    >"$LOG.client" 2>&1
	RC=$?
	cat "$LOG.client" >>"$LOG"; cat "$LOG.client"; rm -f "$LOG.client"; sync
	say "client rc=$RC"
	say ""

	say "--- geometry the firmware left behind ---"
	for r in 0x05600010 $GEOM; do reg $r; done
	say ""

	say "--- restoring it, then disabling source 0, then latching ---"
	for pair in $SAVED; do
		r=${pair%%=*}; v=${pair#*=}
		busybox devmem "$r" 32 "$v"
	done
	busybox devmem 0x05600010 32 0x03000010
	busybox devmem 0x05600014 32 1
	busybox devmem 0x05600144 32 1
	sync
	say ""

	say "--- after the restore ---"
	for r in 0x05600010 0x05600014 $GEOM; do reg $r; done
	say "  OSD ctrl     $(busybox devmem 0x05600140 32)"
	say "  OSD src      $(busybox devmem 0x05600178 32)"
	say "  raster       $(busybox devmem 0x05880000 32) / $(busybox devmem 0x05880000 32)"
	say ""
	say "NOW LOOK AT THE PANEL."
	say "  red band back -> the geometry rewrite is the mechanism"
	say "  still black   -> it is not, and the break is elsewhere in the submit"
	say ""
	say "log: $LOG"
	;;
*)
	echo "usage: $0 mark | run" >&2
	exit 2
	;;
esac
