#!/bin/bash
# The generator gate: for every clip, run the vendor library in emulation
# (vendor-decode.py, cached) and the rig, and compare them field by field and
# buffer by buffer (compare.py). Exit 0 only if every frame of every clip
# matches.
#
#   gate.sh WORKDIR [STOCK.ivf]
#
# Clips are encoded with ffmpeg/libaom into WORKDIR; STOCK.ivf (the stock
# firmware's av1a clip, 10 frames) is added when given. Vendor captures take
# a few minutes per clip the first time.
set -u
here=$(cd "$(dirname "$0")" && pwd)
W=${1:?usage: gate.sh WORKDIR [STOCK.ivf]}; STOCK=${2:-}
R=$here/obj/rig; C=$here/../compare.py; V=$here/../vendor-decode.py
[ -x "$R" ] || "$here/build.sh" || exit 1
mkdir -p "$W"; cd "$W" || exit 1
enc() { # name frames extra-ffmpeg-args...
	local n=$1 fr=$2; shift 2
	[ -f "$n.ivf" ] || ffmpeg -hide_banner -loglevel error -y -f lavfi \
		-i "testsrc2=size=${SIZE}:rate=30" -frames:v "$fr" -c:v libaom-av1 \
		-cpu-used 8 "$@" -f ivf "$n.ivf" || exit 1
}
for s in 352x288 640x360 1000x600 1920x1080 3840x2160; do
	SIZE=$s enc "sz-$s" 3 -pix_fmt yuv420p -b:v 2M
done
SIZE=1920x1080 enc tiles-2x2 4 -pix_fmt yuv420p -b:v 4M -tiles 2x2
SIZE=640x360 enc fg 4 -pix_fmt yuv420p -b:v 1M -aom-params film-grain-test=1
SIZE=640x360 enc ten 3 -pix_fmt yuv420p10le -b:v 1M
fail=0; total=0
run() { # clip frames
	local n=$1 fr=$2
	if [ ! -f "v-$n/frame000.set0.regs" ]; then
		VERBOSE=0 python3 "$V" "$n.ivf" "v-$n" "$fr" >"v-$n.log" 2>&1 ||
			{ echo "$n: VENDOR EMULATION FAILED (v-$n.log)"; fail=1; return; }
	fi
	rm -rf "r-$n"
	"$R" "$n.ivf" "r-$n" "$fr" >"r-$n.log" 2>&1 || { echo "$n: RIG FAILED"; fail=1; return; }
	out=$(python3 "$C" "v-$n" "r-$n" "$fr"); rc=$?
	echo "$n: ${out##*$'\n'}"
	[ $rc = 0 ] || { echo "$out" | grep -v ': 0 field(s) differ.*OK *\(pdec:\(OK\|none\)\)\?$' | head -40; fail=1; }
	total=$((total + fr))
}
[ -n "$STOCK" ] && { cp -n "$STOCK" stock.ivf; run stock 10; }
for s in 352x288 640x360 1000x600 1920x1080 3840x2160; do run "sz-$s" 3; done
run tiles-2x2 5
run fg 4
run ten 3
echo "gate: $total frame(s), $([ $fail = 0 ] && echo PASS || echo FAIL)"
exit $fail
