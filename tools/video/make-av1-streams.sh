#!/bin/bash
# AV1 feature streams for the hardware gate (tools/video/av1-gate.sh). RUNS ON THE HOST.
#
# Each clip turns on one coding tool the basic set does not reach, so a
# failure names its feature. libaom is the encoder because it exposes every
# tool individually; each clip gets its libdav1d reference next to it.
#
#   usage: make-av1-streams.sh OUTDIR
set -eu
out=${1:?usage: make-av1-streams.sh OUTDIR}
mkdir -p "$out"

# name  size  frames  extra ffmpeg/libaom options
enc() {
	local name=$1 size=$2 n=$3; shift 3
	[ -s "$out/$name.ivf" ] || ffmpeg -v error -y -f lavfi -i "testsrc2=s=$size:r=30" -frames:v "$n" \
		-pix_fmt yuv420p -c:v libaom-av1 -cpu-used 6 -crf 35 -b:v 0 -g 8 -row-mt 1 \
		"$@" -f ivf "$out/$name.ivf"
	if [ "$name" = mono ]; then
		# 4:0:0 comes out of libdav1d as gray, and swscale's gray -> yuv420p
		# rescales the range; the decoder's NV12 is that luma untouched
		# over a flat 0x80 chroma, so build exactly that
		local cw=$(( ${size%x*} / 2 )) ch=$(( ${size#*x} / 2 ))
		ffmpeg -v error -y -c:v libdav1d -i "$out/$name.ivf" \
			-f lavfi -i "nullsrc=s=${cw}x${ch}:r=30,format=gray,geq=lum=128" \
			-filter_complex "[0:v][1:v][1:v]mergeplanes=0x001020:yuv420p" \
			-frames:v "$n" -f framemd5 "$out/$name.ivf.framemd5"
	else
		ffmpeg -v error -y -c:v libdav1d -i "$out/$name.ivf" -pix_fmt yuv420p \
			-f framemd5 "$out/$name.ivf.framemd5"
	fi
	printf '%-22s %s frames\n' "$name" "$(grep -vc '^#' "$out/$name.ivf.framemd5")"
}
p() { echo -aom-params "$1"; }
# the same through aomenc, for the options ffmpeg's wrapper does not pass on
aenc() {
	local name=$1 size=$2 n=$3; shift 3
	[ -s "$out/$name.ivf" ] || ffmpeg -v error -f lavfi -i "testsrc2=s=$size:r=30" -frames:v "$n" \
		-pix_fmt yuv420p -f yuv4mpegpipe - |
		aomenc --ivf --cpu-used=6 --end-usage=q --cq-level=35 --kf-max-dist=8 \
		--passes=1 "$@" -o "$out/$name.ivf" - 2>/dev/null
	enc "$name" "$size" "$n"
}

# tiles: grids past 2x2, uneven spacing, several tile groups per frame
enc tiles-4x4        1920x1080 6 -tiles 4x4
enc tiles-8x4-uhd    3840x2160 4 -tiles 8x4
enc tiles-1x4        1280x720  6 -tiles 1x4
enc tiles-4x1        1280x720  6 -tiles 4x1
enc tiles-uneven     1920x1080 6 $(p tile-width=1,2,4,8:tile-height=1,3,5)
enc tgroups-2        1920x1080 6 -tiles 2x2 $(p num-tile-groups=2)
enc tgroups-4        1920x1080 6 -tiles 4x2 $(p num-tile-groups=4)
# film grain: the 16 libaom test vectors cover update_grain=0 and chroma-from-luma scaling
for v in 1 2 5 8 11 14 16; do
	enc fgrain-t$v   640x360   8 $(p film-grain-test=$v)
done
# frame geometry
enc odd-354x290      354x290   8
enc odd-1918x1078    1918x1078 4
enc small-64x64      64x64     8
enc small-130x66     130x66    8
aenc superres-fixed   1280x720  8 --superres-mode=1 --superres-denominator=12 --superres-kf-denominator=12
aenc superres-random  1280x720  12 --superres-mode=2
aenc resize-fixed     1280x720  8 --resize-mode=1 --resize-denominator=12 --resize-kf-denominator=10
aenc resize-random    1280x720  12 --resize-mode=2
# coding tools
enc sb64             1280x720  8 $(p sb-size=64)
enc sb128            1280x720  8 $(p sb-size=128)
enc screen           1280x720  8 $(p tune-content=screen)
aenc intrabc-palette  640x360   6 --cpu-used=2 --cq-level=20 --kf-max-dist=0 --tune-content=screen --enable-intrabc=1 --enable-palette=1
aenc mono             640x360   8 --monochrome
enc lossless         640x360   6 $(p lossless=1)
enc seg-aq1          1280x720  8 $(p aq-mode=1)
enc seg-aq3          1280x720  8 $(p aq-mode=3)
enc deltaq-lf        1280x720  8 $(p deltaq-mode=1:delta-lf-mode=1)
aenc sframe           640x360   24 --sframe-dist=5 --sframe-mode=2 --kf-max-dist=24 --kf-min-dist=24 --lag-in-frames=19
enc still            1280x720  1 -still-picture 1
enc reduced-tx       640x360   8 $(p reduced-tx-type-set=1:enable-tx64=0)
enc no-restoration   640x360   8 $(p enable-restoration=0:enable-cdef=0)
enc altref-lag       640x360   40 -g 40 -lag-in-frames 25 $(p enable-tpl-model=1)
enc cbr-rt           640x360   30 -usage realtime -cpu-used 8 -crf 0 -b:v 300k -g 30
