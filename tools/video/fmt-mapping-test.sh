#!/bin/sh
# Does the firmware's format table behave as the static analysis says?
# RUNS ON THE BOARD, under Linux, with the MIPS left alive.
#
# The question, precisely: the resolver at MIPS 0x8b1a31e8 maps the VideoInfo
# format selector through a 16-entry jump table at 0x8b2078a4 to the byte the
# firmware writes into 0x05600010[15:8].  The table says our old value 11 gives
# fmt 4, which is what hardware showed (0x03000413).  It says 0 gives fmt 0,
# which is what stock plays at.  So:
#
#     DECD_FMT=0   ->  expect 0x05600010 = 0x03000013
#     DECD_FMT=11  ->  expect 0x05600010 = 0x03000413   (the control)
#
# A run that moves the nibble to the predicted value confirms the mapping end to
# end and identifies VideoInfo +0x40 as the resolver's input.  A run that does
# not move it says +0x40 is NOT the input, and the descriptor's own format field
# at +0x08 is the next candidate -- that is a real outcome, not a failure.
#
# See docs/reference/firmware-format-mapping-2026-08-30.md.
#
# WHY IT IS SHAPED LIKE THIS.  MIPS alive + DECD submitting has hard-locked the
# SoC within seconds to tens of seconds, repeatedly.  Everything is therefore
# sequential and synchronous, nothing is backgrounded, and every line is
# appended to a file on the rootfs as it is produced -- earlier runs collected
# over serial lost their results to the lock before anyone could read them.  If
# the board dies mid-run the log still holds everything up to that point.
#
#   usage: fmt-mapping-test.sh [fmt] [dwell-ms]
#          fmt-mapping-test.sh 0            the experiment
#          fmt-mapping-test.sh 11           the control
set -u

FMT=${1:-0}
DWELL=${2:-5000}
FRAME=${FRAME:-/root/decd-test-frame.nv12}
CLIENT=${CLIENT:-/root/decd-client}
LOG=/root/fmt-test-$(date +%Y%m%d-%H%M%S)-fmt$FMT.log

say() { echo "$@" | tee -a "$LOG"; sync; }
reg() { printf '  %-12s %s\n' "$1" "$(busybox devmem "$1" 32 2>/dev/null)" | tee -a "$LOG"; sync; }

say "=== firmware format-table test, DECD_FMT=$FMT, dwell ${DWELL}ms ==="
say "date: $(date)  kernel: $(uname -r)"
say ""

say "--- preconditions ---"
reg 0x0306101c
say "  (0x0306101c must be 1: the MIPS has to be alive for the firmware to"
say "   program anything. If it is 0 this boot used 'auto', not 'init 0x34',"
say "   and the run is void.)"
say "  dec status:     $(cat /proc/device-tree/soc/dec@5600000/status 2>/dev/null | tr -d '\0')"
say "  /dev/decd:      $([ -c /dev/decd ] && echo present || echo MISSING)"
say "  /dev/scanout:   $([ -c /dev/scanout-dmabuf ] && echo present || echo MISSING)"
say "  frame:          $FRAME $([ -r "$FRAME" ] && echo ok || echo MISSING)"
say ""

say "--- before submit ---"
for r in 0x05600010 0x05600020 0x05600030 0x05600040 0x0560004c \
         0x05600070 0x05600084 0x05600098; do reg $r; done
say "  decd irqs:    $(awk '/decd|dec@/ {print $2}' /proc/interrupts | head -1)"
say ""

say "--- submitting one frame with DECD_FMT=$FMT ---"
# Not piped into tee: the client's exit status is wanted, and a pipeline would
# report tee's instead.
DECD_FMT=$FMT timeout $(( DWELL / 1000 + 3 ))s "$CLIENT" show "$FRAME" "$DWELL" \
    >"$LOG.client" 2>&1
RC=$?
cat "$LOG.client" >>"$LOG"; cat "$LOG.client"; rm -f "$LOG.client"; sync
say "client rc=$RC"
say ""

say "--- after submit ---"
for r in 0x05600010 0x05600020 0x05600030 0x05600040 0x0560004c \
         0x05600070 0x05600084 0x05600098; do reg $r; done
say "  decd irqs:    $(awk '/decd|dec@/ {print $2}' /proc/interrupts | head -1)"
say ""

VAL=$(busybox devmem 0x05600010 32 2>/dev/null)
# Extract bits 15:8 arithmetically. devmem prints uppercase hex, so a string
# match would be a case trap waiting to happen.
NUM=$(printf '%d' "$VAL" 2>/dev/null)
if [ -n "$NUM" ]; then
	GOT=$(( (NUM >> 8) & 0xff ))
	ENA=$(( NUM & 0x3 ))
else
	GOT=""; ENA=""
fi

# What the table at 0x8b2078a4 predicts for the input we sent.
case "$FMT" in
  0) WANT=0 ;;  2) WANT=1 ;;  4) WANT=2 ;;  6) WANT=3 ;;
  8) WANT=4 ;;  9) WANT=5 ;; 11) WANT=4 ;; 12) WANT=5 ;;
 14) WANT=7 ;; 15) WANT=6 ;;
  1|3|5|10|13) WANT=0 ;;   # default arm: logs an error, writes 0
  7) WANT="" ;;            # stores nothing; the byte keeps its previous value
  *) WANT="" ;;
esac

say "=== VERDICT ==="
say "0x05600010 = $VAL   (enable=$ENA, fmt nibble=$GOT)"
say "input $FMT, table predicts fmt ${WANT:-<no store>}"
if [ -z "$WANT" ]; then
	say "  -> no prediction for this input; record the value and move on"
elif [ "$GOT" = "$WANT" ]; then
	say "  -> MATCH. The mapping is confirmed end to end, and VideoInfo +0x40"
	say "     is the resolver's input."
else
	say "  -> NO MATCH. Either +0x40 is not the resolver's input (try the"
	say "     descriptor format at +0x08 next), or the submit never reached"
	say "     the firmware -- check the DECD irq count moved and 0x0306101c=1."
fi
say ""
say "log: $LOG"
