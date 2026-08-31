#!/bin/sh
# Sample one MMIO page four times, twice in each of two states.
#
# RUNS ON THE BOARD -- either stack. Pass the reader for the stack you are on:
#
#   stock Android   page-sample.sh ./hidtvreg-read /data/local/tmp/cap
#   our Linux       page-sample.sh ./mmio-read     /root/cap
#
# Both readers take a hex address and hex word count and emit a byte-identical
# format, so their captures diff line-for-line. Do not substitute devmem: its
# output format is different and the comparison is the whole point.
#
# WHY FOUR SAMPLES AND NOT TWO
#
# The composition page carries free-running telemetry -- +0xa04 and +0xa08 are
# known to change between reads a second apart, and other groups moved between
# an immediate and a delayed sample. A single capture per state cannot tell a
# free-running counter from a genuine state difference, so a one-sample-per-side
# diff of this page is uninterpretable.
#
# Sampling twice within each state fixes that, and sampling twice in BOTH states
# catches the registers that free-run in only one of them -- which is the actual
# behaviour of AFBD's buffer ring, still at idle and cycling during playback.
# Classification is done on the host by page-classify.py; this script only
# captures, so that nothing here depends on the board having awk.
#
# STATE 1 is the resting state (stock: player open, paused or not started; ours:
# booted, MIPS alive, no submit). STATE 2 is the observable state (stock: video
# actually playing; ours: DECD submitting). The script pauses between them and
# waits for you, because only an operator can tell whether the panel is really
# showing video -- that mistake has cost this project a result before, when a
# clip that never rendered was indistinguishable from a frozen one.
#
# Usage:
#   page-sample.sh READER OUTDIR [ADDR [COUNT]]
#
# ADDR and COUNT are hex, no 0x prefix, matching the readers. They default to
# the firmware-owned composition page, whole: 05000000 400 (1024 words, 4 KiB).

set -e

READER=$1
OUTDIR=$2
ADDR=${3:-05000000}
COUNT=${4:-400}

if [ -z "$READER" ] || [ -z "$OUTDIR" ]; then
	echo "usage: page-sample.sh READER OUTDIR [ADDR [COUNT]]" >&2
	exit 2
fi

if [ ! -x "$READER" ]; then
	echo "REFUSING: $READER is not executable." >&2
	echo "Build it for the stack you are on -- hidtvreg-read is 32-bit ARM," >&2
	echo "mmio-read is arm64. A reader built for the wrong stack fails here" >&2
	echo "rather than after the state has been set up." >&2
	exit 2
fi

mkdir -p "$OUTDIR"

# Prove the reader works and the page is mappable BEFORE asking the operator to
# arrange anything. On stock this fails if /dev/hidtvreg is missing; on ours if
# /dev/mem is gated. Either way, find out now and not four minutes in.
if ! "$READER" "$ADDR" 4 > "$OUTDIR/.probe" 2>&1; then
	echo "REFUSING: $READER could not read $ADDR:" >&2
	cat "$OUTDIR/.probe" >&2
	exit 1
fi
if [ "$(wc -l < "$OUTDIR/.probe")" -lt 4 ]; then
	echo "REFUSING: probe read returned fewer than 4 lines:" >&2
	cat "$OUTDIR/.probe" >&2
	exit 1
fi
rm -f "$OUTDIR/.probe"

sample() {
	"$READER" "$ADDR" "$COUNT" > "$OUTDIR/$1"
	echo "  $1  $(wc -l < "$OUTDIR/$1") lines"
}

echo "=== state 1: resting ==="
echo "Arrange the resting state now, then press Enter."
read -r _
sample state1-a
sleep 2
sample state1-b

echo
echo "=== state 2: the observable ==="
echo "Start video / begin submitting. CONFIRM ON THE PANEL, then press Enter."
echo "Do not press Enter on the assumption that it started -- a clip that never"
echo "rendered looks exactly like a frozen one, and that has cost a result here."
read -r _
sample state2-a
sleep 2
sample state2-b

echo
echo "=== captured to $OUTDIR ==="
echo "Copy the four files off the board and classify on the host:"
echo "  page-classify.py $OUTDIR"
echo "Then diff the two stacks' classifications against each other."
