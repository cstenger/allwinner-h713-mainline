#!/usr/bin/env bash
# Drive the vendor-stack capture session from the host, over adb.
# Plan: docs/vendor-capture-plan.md. Order and operator steps:
# docs/stock-capture-operator-sheet.md.
#
# Everything on the target is READ-ONLY: stock-capture.sh reads registers and
# DRAM through /dev/hidtvreg (opened O_RDONLY, mapped PROT_READ) and nothing
# here writes a register. The only things this does to Android are starting
# and stopping the stock player, and pushing files to /data/local/tmp and
# /sdcard/Movies.
#
#   capture-session.sh check                adb up, hidtvreg readable
#   capture-session.sh push                 tools + media to the board
#   capture-session.sh baseline             fw identity + idle state
#   capture-session.sh case FILE [TAG]      play FILE, capture, summarise (leaves it playing)
#   capture-session.sh state TAG            capture whatever is on screen now (menus)
#   capture-session.sh stop                 stop the player
#   capture-session.sh logs TAG             logcat + media.player dump
#   capture-session.sh pull                 everything under out/ to the host
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
LAB=${LAB:-$ROOT/local/h713-lab/stock-capture-20261001}
MEDIA=$LAB/media
OUT=$LAB/out
T=/data/local/tmp/cap
MOVIES=/sdcard/Movies
PLAYER=com.softwinner.TvdVideo/.TvdVideoActivity
mkdir -p "$OUT"

die() { echo "capture-session: $*" >&2; exit 1; }
sc() { adb shell "T=$T sh $T/stock-capture.sh $*"; }

fetch() {  # TAG-glob -> host OUT, via tar (one round trip, keeps the layout)
	adb exec-out "cd $T/out && tar cf - $1 2>/dev/null" | tar xf - -C "$OUT"
}

mime() {
	case $1 in
	*.mp4) echo video/mp4 ;; *.webm) echo video/webm ;; *.ts) echo video/mp2ts ;;
	*) die "no mime type for $1" ;;
	esac
}

cmd_check() {
	adb get-state >/dev/null 2>&1 || die "no adb device -- plug USB in once Android is up"
	adb shell 'getprop ro.build.fingerprint; ls -l /dev/hidtvreg; df -h /data /sdcard | tail -2'
}

cmd_push() {
	local bin=$LAB
	[ -x "$bin/hidtvreg-read" ] && [ -x "$bin/hidtvreg-raw" ] || die "build/stage hidtvreg-read and hidtvreg-raw in $bin"
	adb shell "mkdir -p $T/out"
	adb push "$bin/hidtvreg-read" "$bin/hidtvreg-raw" "$ROOT/tools/stock/stock-capture.sh" $T/
	adb shell "chmod 755 $T/hidtvreg-read $T/hidtvreg-raw $T/stock-capture.sh"
	adb push "$MEDIA"/[0-9]* $MOVIES/
	adb shell "ls $MOVIES | grep -c '^[0-9]'" | sed 's/^/media files on the board: /'
}

summary() {  # TAG
	local prev=
	[ -s "$OUT/.last" ] && prev="--previous-elog $OUT/$(cat "$OUT/.last")-2/elog.bin"
	# shellcheck disable=SC2086
	python3 "$ROOT/tools/stock/capture-summary.py" "$OUT" "$1" $prev
	echo "$1" > "$OUT/.last"
}

cmd_baseline() {
	sc fw fw
	sc play idle
	fetch 'fw idle-*'
	echo; tr -d '\000' < "$OUT/fw/cfg.bin" | grep -E "<(mode|level) val" | sed 's/^/loaded cfg: /'
	python3 - "$OUT/fw/fw-text.bin" "$ROOT/local/mips-display/board-b-mips/display.bin" <<-'EOF'
	import sys
	live, ref = open(sys.argv[1], "rb").read(), open(sys.argv[2], "rb").read()[0x10000:0x20000]
	print("firmware text == board-b display.bin:", live == ref,
	      "" if live == ref else "-- NOT the FAT firmware: elog address unproven")
	EOF
	summary idle
}

cmd_case() {
	local f=$1 tag=${2:-}
	[ -n "$tag" ] || { tag=$(basename "$f"); tag=${tag%.*}; }
	[ -s "$MEDIA/$(basename "$f")" ] || die "no such media file: $f"
	# Host wall-clock per case: photos are matched to cases by their EXIF time.
	echo "$(date '+%F %T') case $tag $(basename "$f")" >> "$OUT/cases.log"
	adb shell am start -n $PLAYER -a android.intent.action.VIEW \
		-d "file://$MOVIES/$(basename "$f")" -t "$(mime "$f")" | { grep -v '^Starting' || true; }
	sleep 3
	sc elog "$tag-early"	# setup records, before a busy ring can wrap them
	sleep 5
	sc play "$tag"
	fetch "$tag-*"
	echo; summary "$tag"
}

cmd_state() {
	echo "$(date '+%F %T') state $1" >> "$OUT/cases.log"
	sc elog "$1-early"
	sc play "$1" 3
	fetch "$1-*"
	echo; summary "$1"
}

case ${1:-} in
check)    cmd_check ;;
push)     cmd_push ;;
baseline) cmd_baseline ;;
case)     cmd_case "${2:?file}" "${3:-}" ;;
state)    cmd_state "${2:?tag}" ;;
stop)     adb shell am force-stop "${PLAYER%%/*}" ;;
logs)     sc logs "${2:?tag}"; fetch "$2" ;;
pull)     adb exec-out "cd $T && tar cf - out" | tar xf - -C "$LAB" && du -sh "$OUT" ;;
*)        sed -n '2,20p' "$0"; exit 2 ;;
esac
