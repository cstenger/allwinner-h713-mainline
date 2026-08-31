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
# WHICH WINDOWS, AND WHY THESE
#
# The default set is the blocks the MIPS firmware actually addresses, from
# tools/mips/block-survey.py, plus one control:
#
#   05000000  45 firmware sites -- the composition page, most-addressed block
#             in the image, and the one carrying the content-following taps
#   050c0000  22 sites -- never characterised, never captured on either stack
#   05040000   7 sites -- likewise
#   05180000   1 site  -- likewise; weak, but a page costs nothing to read
#   05600000  AFBD, 128 words: POSITIVE CONTROL, not a subject
#
# The control is the point of including AFBD. Its Y/C ring is proven to move
# per frame on stock, so it must come back state-driven or free-running. If it
# does not, the capture did not observe the state it claims to and a null
# everywhere else means nothing. Without it, "no differences found" is
# ambiguous between a real negative and a broken run -- and this investigation
# has already spent weeks on nulls that turned out to be unfalsifiable.
#
# Not included: the mixer, GE2D, TVTOP, TCON and PLL all have zero firmware
# references, and the eleven-window sweep already compared them.
#
# Usage:
#   page-sample.sh READER OUTDIR [ADDR:COUNT ...]
#
# ADDR and COUNT are hex, no 0x prefix, matching the readers. Each sample file
# holds every window concatenated, so one state setup captures all of them --
# which matters, because setting up the MIPS-plus-DECD state is the part that
# risks a hard lock, and doing it once per window would multiply that risk.

set -e

READER=$1
OUTDIR=$2
shift 2 || true
WINDOWS=${*:-"05000000:400 050c0000:400 05040000:400 05180000:400 05600000:80"}

if [ -z "$READER" ] || [ -z "$OUTDIR" ]; then
	echo "usage: page-sample.sh READER OUTDIR [ADDR:COUNT ...]" >&2
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

# Prove the reader works and EVERY window is mappable BEFORE asking the operator
# to arrange anything. On stock this fails if /dev/hidtvreg is missing; on ours
# if /dev/mem is gated. Either way, find out now and not four minutes in, with
# the board in a state that took a reboot to reach.
echo "=== probing windows ==="
for w in $WINDOWS; do
	a=${w%:*}
	if ! "$READER" "$a" 4 > "$OUTDIR/.probe" 2>&1; then
		echo "REFUSING: $READER could not read $a:" >&2
		cat "$OUTDIR/.probe" >&2
		exit 1
	fi
	if [ "$(wc -l < "$OUTDIR/.probe")" -lt 4 ]; then
		echo "REFUSING: probe of $a returned fewer than 4 lines:" >&2
		cat "$OUTDIR/.probe" >&2
		exit 1
	fi
	echo "  $a ok"
done
rm -f "$OUTDIR/.probe"

sample() {
	: > "$OUTDIR/$1"
	for w in $WINDOWS; do
		"$READER" "${w%:*}" "${w#*:}" >> "$OUTDIR/$1"
	done
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
