#!/bin/sh
# Where does each clip land on the panel? RUNS ON THE TARGET.
# WP2's geometry check, done on the scanout rather than on a photograph.
#
#   sh geometry-grab.sh CLIP...          (stock mpv, vo=gpu, cheap settings)
#   MPV=/usr/local/bin/mpv VO=drm sh geometry-grab.sh /tmp/1b-h264-1280x720.mp4
#
# Plays each clip, grabs the framebuffer the display is scanning out
# (tools/display/scanout-grab.c, built as /root/scanout-grab) a few seconds in,
# and compares the picture's bounding box with where aspect-fit says it must be:
# the display aspect (width x SAR / height, swapped for a 90/270 rotation)
# fitted into 1280x720 and centred. The capture media's geometry card has a
# white border at the very edge of the frame, so the bounding box of non-black
# pixels IS the picture. GRABS are kept in /tmp/geom/ for a look.
set -u
MPV=${MPV:-/usr/bin/mpv}
VO=${VO:-gpu}
TOL=${TOL:-3}
CHEAP='--scale=bilinear --dscale=bilinear --cscale=bilinear --dither-depth=no --deband=no --correct-downscaling=no --linear-downscaling=no --sigmoid-upscaling=no --hdr-compute-peak=no'
mkdir -p /tmp/geom

for c in "$@"; do
	b=$(basename "$c")
	set -- $(ffprobe -v error -select_streams v:0 \
		-show_entries stream=width,height,sample_aspect_ratio:stream_side_data=rotation \
		-of default=nw=1:nk=1 "$c" | tr '\n' ' ')
	w=$1 h=$2 sar=${3:-1:1} rot=${4:-0}
	case "$sar" in 0:1|N/A|"") sar=1:1 ;; esac
	exp=$(awk -v w="$w" -v h="$h" -v sar="$sar" -v rot="$rot" 'BEGIN {
		split(sar, s, ":"); dar = w * s[1] / s[2] / h
		if (rot == 90 || rot == -90 || rot == 270 || rot == -270) dar = 1 / dar
		if (dar >= 1280 / 720) { ew = 1280; eh = 1280 / dar } else { eh = 720; ew = 720 * dar }
		printf "%d %d %d %d", (1280 - ew) / 2, (720 - eh) / 2, ew, eh }')
	case "$VO" in gpu*) ctx=--gpu-context=drm ;; *) ctx= ;; esac
	# shellcheck disable=SC2086
	LIBVA_DRIVER_NAME=v4l2_request "$MPV" --no-config --vo="$VO" $ctx --hwdec=vaapi \
		--end=12 --input-terminal=no $CHEAP "$c" > /tmp/geom/mpv.log 2>&1 < /dev/null &
	p=$!
	sleep 7
	g=$(/root/scanout-grab "/tmp/geom/$b.ppm" 2>/dev/null)
	kill $p 2>/dev/null; wait $p 2>/dev/null
	# GRAB 1280x720 content x=X0..X1 y=Y0..Y1 (WxH) -> file
	echo "$g" | awk -v e="$exp" -v n="$b" -v tol="$TOL" -v src="${w}x${h} sar=$sar rot=$rot" '
	/^GRAB/ {
		split(e, E, " ")
		split($4, X, /[=.]+/); split($5, Y, /[=.]+/)
		x0 = X[2]; x1 = X[3]; y0 = Y[2]; y1 = Y[3]
		gw = x1 - x0 + 1; gh = y1 - y0 + 1
		ok = (x0 - E[1] <= tol && E[1] - x0 <= tol && y0 - E[2] <= tol && E[2] - y0 <= tol &&
		      gw - E[3] <= 2*tol && E[3] - gw <= 2*tol && gh - E[4] <= 2*tol && E[4] - gh <= 2*tol)
		printf "GEOM %s %s: picture %dx%d at (%d,%d), expected %dx%d at (%d,%d) -> %s\n",
		       n, src, gw, gh, x0, y0, E[3], E[4], E[1], E[2], ok ? "OK" : "WRONG"
		found = 1 }
	END { if (!found) printf "GEOM %s: no grab\n", n }'
done
