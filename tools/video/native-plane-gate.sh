#!/bin/bash
# Letterbox Phase 5 regression gate: the NATIVE video plane (1280x720 at 0,0)
# is what it was before the letterbox kernels (0161-0165). RUNS ON THE TARGET,
# as root. Headless: nothing here needs the operator.
#
#   native-plane-gate.sh [CLIP...]
#
# WHY. Letterbox rewrote the plane's atomic_check/update around a geometry
# table. The native geometry is supposed to be the table's identity entry,
# programming exactly what the pre-letterbox driver did -- but every
# letterbox test so far was about the OTHER geometries. This checks the
# identity against a capture taken before any letterbox kernel existed
# (docs/reference/letterbox-baseline-2026-10-04/native-720p.txt, kernel
# 0160, native 720p H.264 playing), register by register, so a difference
# is found by a diff rather than by an operator look.
#
# NV12, per CLIP (default: one native 720p clip per codec in /root):
#   route    h713-play picks plane-native (a GPU route proves nothing);
#   alive    the video plane's fb id changes between two samples, the
#            source is enabled (0x05600010 bits 1:0 = 3) and vsyncs count;
#   format   0x05600010 bits 15:8 = 0 (NV12);
#   regs     letterbox-baseline.py diffed against the known-good capture:
#            0 differences outside the per-frame words (slot addresses,
#            status and counters, listed in VOLATILE below);
#   irqs     0 GPU and 0 IOMMU interrupts.
# P010 (kms-p010-plane-test, a static LSB10 frame and an MSB one):
#   format   bits 15:8 = 7 (LSB10 modifier) and 6 (plain P010);
#   budget   the fetch budgets (high halves of +030/+048/+04c) are twice
#            NV12's, the strides (+040/+044, low halves) equal NV12's:
#            16-bit formats count samples in the strides and bytes in the
#            budgets (p010-video-plane, 2026-09-30);
#   regs     the same register diff, which must differ from NV12 ONLY in
#            those budgets and the format byte.
# Stock GStreamer cannot carry P010 into kmssink (patches/gstreamer, which
# could, is gone), so 10-bit plays through the GPU route; the P010 plane is
# still the zero-copy path for mpv --vo=drm and must not regress.
#
# Prints `NATIVE key=value` lines and one `NATIVE RESULT PASS|FAIL` line.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
PLAY=${PLAY:-$HERE/h713-play}
MMIO=${MMIO:-/root/mmio-read}
BASELINE_PY=${BASELINE_PY:-/root/letterbox-baseline.py}
REF=${REF:-/root/native-720p.txt}
P010_TEST=${P010_TEST:-/root/kms-p010-plane-test}
OUT=${OUT:-/tmp/native-plane-gate}
# 10-second testsrc2 clips, one per plane codec, made on the host:
#   local/h713-lab/native-gate/native-{h264,hevc}.mp4, native-vp9.webm,
#   native-av1.ivf (ffmpeg testsrc2 1280x720 30 fps, 2 Mb/s).
# The conformance vectors are 0.5-2 s long: too short to sample.
CLIPS=${CLIPS:-/dev/shm/native-gate}
[ $# -gt 0 ] || set -- "$CLIPS"/native-h264.mp4 "$CLIPS"/native-hevc.mp4 \
	"$CLIPS"/native-vp9.webm "$CLIPS"/native-av1.ivf
mkdir -p "$OUT"

# Words that change every frame or every boot, never geometry: AFBD's
# control/status (+010, checked by field instead), slot addresses and
# status (+058/+05c, +070-+0a4, +0b8/+0bc, +140, +184, +300-+310), as the
# Phase 0 baseline documented them.
VOLATILE='^afbd\+(010|058|05c|07[0-9a-f]|08[0-9a-f]|09[0-9a-f]|0a[0-4]|0b8|0bc|140|184|30[0-9a-f]|310) '

irq() {
	awk -v n="$1" '$NF == n { s = 0; for (i = 2; i <= NF; i++) if ($i ~ /^[0-9]+$/) s += $i; print s; f = 1 }
		END { if (!f) print 0 }' /proc/interrupts
}
video_fb() {
	cat /sys/kernel/debug/dri/*/state 2>/dev/null | awk '
		/^plane\[/ { p = ($0 ~ /video-0/) }
		p && /fb=/ && !/format/ { sub(/.*fb=/, ""); print; exit }'
}
video_state() { # the first card's video plane only
	cat /sys/kernel/debug/dri/*/state 2>/dev/null | awk '
		/^plane\[/ { if (p) exit; p = ($0 ~ /video-0/) } /^(crtc|connector)\[/ { if (p) exit }
		p && /(crtc-pos|crtc-size|src-pos|src-size|format|modifier)=/ { gsub(/^[ \t]+/, ""); printf "%s ", $0 }
		END { print "" }'
}
reg() { "$MMIO" "$1" 1 2>/dev/null | awk 'NR == 1 { print $2 }'; }
regdiff() { # dump -> lines that differ from the reference, outside VOLATILE
	diff <(grep -vE "$VOLATILE" "$REF") <(grep -vE "$VOLATILE" "$1") | grep '^[<>]'
}

fail=0
check() { # name ok-expression message
	if eval "$2"; then echo "NATIVE $1 ok: $3"; else echo "NATIVE $1 FAIL: $3"; fail=1; fi
}
for f in "$MMIO" "$BASELINE_PY" "$REF" "$P010_TEST"; do
	[ -r "$f" ] || { echo "NATIVE missing $f" >&2; exit 2; }
done

dmesg -C
g0=$(irq panfrost-job) m0=$(irq 2010000.iommu)

# --- NV12, decoded, through the shipped launcher ----------------------------
for clip in "$@"; do
	n=${clip##*/}
	"$PLAY" --route=plane "$clip" > "$OUT/$n.log" 2>&1 < /dev/null &
	pid=$!
	# Sample once the plane carries a frame (up to 5 s), not after a fixed
	# sleep: a sample after the clip ends reads the idle state.
	for i in $(seq 50); do
		fb=$(video_fb); [ -n "$fb" ] && [ "$fb" != 0 ] && break; sleep 0.1
	done
	sleep 1
	fb1=$(video_fb) f1=$(irq h713-afbd) ctrl=$(reg 5600010) st=$(video_state)
	python3 "$BASELINE_PY" > "$OUT/$n.regs" 2>/dev/null
	fb2=$(video_fb) f2=$(irq h713-afbd)
	wait $pid; rc=$?
	route=$(grep -m1 -oE 'plane-[a-z]+|: gpu' "$OUT/$n.log")
	d=$(regdiff "$OUT/$n.regs")
	echo "NATIVE $n plane: $st"
	check "$n:route" '[ "$route" = plane-native ] && [ $rc = 0 ]' "route=${route:-none} exit=$rc"
	check "$n:alive" '[ -n "$fb1" ] && [ "$fb1" != "$fb2" ] && [ $(( ctrl & 3 )) = 3 ] && [ $(( f2 - f1 )) -gt 0 ]' \
		"fb $fb1 -> $fb2, source ctrl $ctrl, $(( f2 - f1 )) vsyncs"
	check "$n:format" '[ $(( (ctrl >> 8) & 0xff )) = 0 ]' "fetch format $(( (ctrl >> 8) & 0xff )) (0 = NV12)"
	check "$n:regs" '[ -z "$d" ]' "$(printf '%s' "$d" | grep -c '^<') of $(grep -cvE "$VOLATILE" "$REF") registers differ from the pre-letterbox capture"
	[ -n "$d" ] && printf '%s\n' "$d" | head -20 | sed 's/^/NATIVE   /'
done

# --- P010, a static frame, both layouts -------------------------------------
for fill in lsb msb; do
	[ $fill = lsb ] && want=7 || want=6
	ALLOC=heap FILL=$fill ARMED=yes "$P010_TEST" 4 > "$OUT/p010-$fill.log" 2>&1 < /dev/null &
	pid=$!
	sleep 2
	ctrl=$(reg 5600010) st=$(video_state)
	python3 "$BASELINE_PY" > "$OUT/p010-$fill.regs" 2>/dev/null
	wait $pid; rc=$?
	# Expected: NV12's native words with the three budgets doubled. (The
	# board's awk is mawk: no bit operations, so the arithmetic is shell.)
	d= nb=0
	while read -r k ref got; do
		case $k in
		afbd+030|afbd+048|afbd+04c)
			r=$((16#$ref)) g=$((16#${got:-0}))
			if [ $(( g & 0xffff )) = $(( r & 0xffff )) ] && [ $(( g >> 16 )) = $(( 2 * (r >> 16) )) ]; then
				nb=$((nb + 1)); continue
			fi ;;
		esac
		d="$d$k ref $ref got ${got:--}"$'\n'
	done < <(join -a1 -a2 -e - -o 0,1.3,2.3 \
		<(grep -vE "$VOLATILE" "$REF" | sort) <(grep -vE "$VOLATILE" "$OUT/p010-$fill.regs" | sort) |
		awk '$2 != $3')
	d=${d%$'\n'}
	echo "NATIVE p010-$fill plane: $st"
	check "p010-$fill:run" '[ $rc = 0 ]' "kms-p010-plane-test exit $rc"
	check "p010-$fill:format" '[ $(( (ctrl >> 8) & 0xff )) = $want ]' "fetch format $(( (ctrl >> 8) & 0xff )) (want $want)"
	check "p010-$fill:budget" '[ "$nb" = 3 ]' "$nb of 3 fetch budgets differ from NV12's (doubled)"
	check "p010-$fill:regs" '[ -z "$d" ]' "$(printf '%s' "$d" | grep -c .) registers differ beyond the doubled budgets"
	[ -n "$d" ] && printf '%s\n' "$d" | head -20 | sed 's/^/NATIVE   /'
done

g=$(( $(irq panfrost-job) - g0 )) m=$(( $(irq 2010000.iommu) - m0 ))
bad=$(dmesg | grep -E 'sun50i-h713-afbd|iommu' | grep -iE 'warn|err|fault|did not|not expressible|timeout')
echo "NATIVE irqs gpu=$g iommu=$m"
check gpu '[ "$g" = 0 ]' "$g GPU interrupts"
check iommu '[ "$m" = 0 ]' "$m IOMMU interrupts"
check kernel '[ -z "$bad" ]' "$(printf '%s' "$bad" | grep -c .) display/IOMMU complaints"
[ -n "$bad" ] && printf '%s\n' "$bad" | head -20 | sed 's/^/NATIVE   /'

[ $fail = 0 ] && echo "NATIVE RESULT PASS" || echo "NATIVE RESULT FAIL"
exit $fail
