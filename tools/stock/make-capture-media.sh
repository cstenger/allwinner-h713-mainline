#!/usr/bin/env bash
# Build the media set for the vendor-stack capture session
# (docs/vendor-capture-plan.md, operator sheet docs/stock-capture-operator-sheet.md).
#
# Every clip is the geometry card from tools/display/make-scaler-testcard.py,
# rasterised natively at the clip's own size, so a photograph of the panel
# measures position and scale with tools/display/measure-panel-photo.py and
# the card's size stamp names the file in the photo. Three rules, each from a
# session that lost time without it:
#
#   * EVERY FILE HAS AN AUDIO TRACK. TvdVideo refuses video-only files ("Do not
#     support this video"); a silent AAC track is enough (2026-08-29).
#   * EVERY FILE MOVES. A white marker crosses the card's empty band (between
#     the frequency blocks and the circle row), so "playing" and "frozen" differ
#     on the panel. Checked here by hashing three frames, because a clip whose
#     overlay silently never rendered once wasted an observation.
#   * EVERY CLIP RUNS 180 s: two snapshots land in steady state, and the clip
#     is still playing when the operator, in their own turn, photographs it.
#
# The card goes in as NV12 (its own .nv12 output), not PNG, so luma keeps the
# card's limited-range values instead of an RGB->YUV squeeze.
#
#   tools/stock/make-capture-media.sh [OUTDIR]     default local/h713-lab/stock-capture-20261001/media
#   ONLY='0[1-3]*' tools/stock/make-capture-media.sh   a subset (glob on the file name)
#   FORCE=1 ...                                        rebuild files that already exist
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
OUT=${1:-$ROOT/local/h713-lab/stock-capture-20261001/media}
CARDS=$OUT/cards
DUR=${DUR:-180}
FPS=30
ONLY=${ONLY:-*}
mkdir -p "$OUT" "$CARDS"

log() { printf '%s\n' "$*" >&2; }
# WebM takes only Opus/Vorbis; Opus is what played on stock on 2026-09-29.
acodec() { case $1 in *.webm) echo "-c:a libopus -b:a 64k" ;; *) echo "-c:a aac -b:a 64k" ;; esac; }
want() { [[ $1 == $ONLY ]]; }
# Already built? Skip, unless FORCE=1. Applies to building only, not to verify.
todo() { want "$1" && { [ -n "${FORCE:-}" ] || [ ! -s "$OUT/$1" ]; }; }

card() {  # WxH -> path of the NV12 card, rendered once
	local f=$CARDS/scaler-testcard-$1.nv12
	[ -s "$f" ] || python3 "$ROOT/tools/display/make-scaler-testcard.py" "$CARDS" --size "$1" >/dev/null
	echo "$f"
}

# encode NAME WxH SAR VIDEO-ARGS...   -> $OUT/NAME, card + marker + silent audio
# (VF=,filter appends to the video chain for one call)
encode() {
	local name=$1 size=$2 sar=$3; shift 3
	todo "$name" || return 0
	local w=${size%x*} h=${size#*x} src mw mh
	src=$(card "$size")
	mw=$(( (w / 20 + 1) & ~1 )) mh=$(( (h / 20 + 1) & ~1 ))
	log "encode $name ($size, SAR $sar)"
	local audio=(-f lavfi -i "anullsrc=r=48000:cl=stereo") amap=(-map 1:a $(acodec "$name") -shortest)
	[[ " $* " == *" -an "* ]] && audio=() amap=()
	ffmpeg -hide_banner -v error -y \
		-stream_loop -1 -f rawvideo -pix_fmt nv12 -s "$size" -r $FPS -i "$src" \
		"${audio[@]}" \
		-filter_complex "color=c=white:s=${mw}x${mh}:r=$FPS[m];[0:v][m]overlay=x='W*0.1+mod(t*W/6\,W*0.85-w)':y='H*0.33':eval=frame:shortest=1,setsar=$sar${VF:-}[v]" \
		-map "[v]" -t "$DUR" "$@" "${amap[@]}" "$OUT/$name"
}

# rotate NAME SRC DEGREES   -> copy of SRC with a display matrix, no re-encode
rotate() {
	todo "$1" || return 0
	log "rotate $1 ($3 deg, from $2)"
	ffmpeg -hide_banner -v error -y -display_rotation:v:0 "$3" -i "$OUT/$2" -map 0 -c copy "$OUT/$1"
}

# retime NAME SRC FPS   -> SRC's video at FPS frames/s (holds each resolution
# segment long enough to capture), plus silent audio
retime() {
	local name=$1 src=$2 rate=$3 n
	todo "$name" || return 0
	n=$(ffprobe -v error -count_packets -select_streams v:0 -show_entries stream=nb_read_packets -of csv=p=0 "$src")
	log "retime $name ($n frames at $rate fps = $(( n / rate )) s, from $src)"
	ffmpeg -hide_banner -v error -y -r "$rate" -i "$src" \
		-f lavfi -i "anullsrc=r=48000:cl=stereo" \
		-map 0:v -map 1:a -c:v copy $(acodec "$name") -t $(( n / rate )) "$OUT/$name"
}

# segments NAME CODEC-ARRAY-NAME WxH:SECONDS...  -> card clips at each size,
# concatenated without re-encoding: a mid-stream resolution change at a
# keyframe, the way vp9-rc.ivf does it, but with a card in every segment so
# each one measures in a photo. Audio is added over the whole length after.
segments() {
	local name=$1 codec=$2; shift 2
	todo "$name" || return 0
	local ext=${name##*.} list=$OUT/.seg-$name.txt i=0 total=0 seg size secs
	local -n args=$codec
	: > "$list"
	for seg in "$@"; do
		size=${seg%:*} secs=${seg#*:}
		ONLY="*" FORCE=1 DUR=$secs encode ".seg$i-$name" "$size" 1 "${args[@]}" -an
		echo "file '$OUT/.seg$i-$name'" >> "$list"
		total=$((total + secs)) i=$((i + 1))
	done
	log "segments $name ($*)"
	ffmpeg -hide_banner -v error -y -f concat -safe 0 -i "$list" \
		-f lavfi -i "anullsrc=r=48000:cl=stereo" \
		-map 0:v -map 1:a -c:v copy $(acodec "$name") -t $total "$OUT/$name"
	rm -f "$list" "$OUT"/.seg*-"$name"
}

X264=(-c:v libx264 -preset veryfast -profile:v high -g $FPS -pix_fmt yuv420p)
X265=(-c:v libx265 -preset fast -g $FPS -pix_fmt yuv420p -x265-params log-level=error)
X265_10=(-c:v libx265 -preset fast -g $FPS -pix_fmt yuv420p10le -profile:v main10 -x265-params log-level=error)
VP9=(-c:v libvpx-vp9 -deadline realtime -cpu-used 8 -row-mt 1 -b:v 2M -g $FPS -pix_fmt yuv420p)
AV1=(-c:v libsvtav1 -preset 10 -g $FPS -pix_fmt yuv420p -svtav1-params loglevel=0)
AV1_10=(-c:v libsvtav1 -preset 10 -g $FPS -pix_fmt yuv420p10le -svtav1-params loglevel=0)
# Field order comes from the frames (VF=,setfield=tff below), not an encoder option.
MPEG2I=(-c:v mpeg2video -b:v 12M -g 15 -flags +ilme+ildct -pix_fmt yuv420p)
# Colour tags come from the frames in ffmpeg 9 (encoder -color_* options were
# ignored), so they are set by VF=,setparams on the call below.
HDR10_VF=,setparams=color_primaries=bt2020:color_trc=smpte2084:colorspace=bt2020nc
HDR10=(-x265-params "log-level=error:hdr10=1:repeat-headers=1:master-display=G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(10000000,50):max-cll=1000,400")

# --- 0x  Downscale: 1080p sources on the 720p panel -------------------------
encode 01-h264-1080.mp4     1920x1080 1 "${X264[@]}"
encode 02-hevc-1080.mp4     1920x1080 1 "${X265[@]}"
encode 03-hevc10-1080.mp4   1920x1080 1 "${X265_10[@]}"
encode 04-vp9-1080.webm     1920x1080 1 "${VP9[@]}"
encode 05-av1-1080.mp4      1920x1080 1 "${AV1[@]}"
encode 06-av110-1080.mp4    1920x1080 1 "${AV1_10[@]}"
VF=,setfield=tff encode 07-mpeg2-1080i.ts 1920x1080 1 "${MPEG2I[@]}"

# --- 1x  Fit / letterbox: everything below and around 720p -------------------
encode 10-h264-640x360.mp4    640x360   1     "${X264[@]}"
encode 11-h264-852x480.mp4    852x480   1     "${X264[@]}"
encode 12-h264-960x540.mp4    960x540   1     "${X264[@]}"
encode 13-h264-352x288.mp4    352x288   1     "${X264[@]}"
encode 14-h264-640x480.mp4    640x480   1     "${X264[@]}"
encode 15-h264-720x576-sar16x15.mp4 720x576 16/15 "${X264[@]}"
encode 16-h264-1000x600.mp4   1000x600  1     "${X264[@]}"
encode 17-h264-2560x1080.mp4  2560x1080 1     "${X264[@]}"
encode 18-h264-1440x1080.mp4  1440x1080 1     "${X264[@]}"
encode 19-vp9-852x480.webm    852x480   1     "${VP9[@]}"
encode 1a-av1-852x480.mp4     852x480   1     "${AV1[@]}"
encode 1b-h264-1280x720.mp4   1280x720  1     "${X264[@]}"   # native control

# --- 2x  Size change mid-stream ---------------------------------------------
# 20: vp9-rc.ivf's own size sequence (640x360 -> 1280x720 -> 352x288 ->
# 640x360), rebuilt from card segments of 30/30/15/30 s: vp9-rc's content is
# static, which makes "playing" and "frozen" look the same on the panel.
# 21: the real r01 HEVC stream (640x480 <-> 320x240, ~24 frames per segment),
# retimed to 1 fps so each segment holds ~24 s; its content moves.
segments 20-vp9-rc.webm VP9 640x360:30 1280x720:30 352x288:15 640x360:30
retime 21-hevc-r01.mp4 "$ROOT/local/video-test/r01-resolution-change.h265" 1

# --- 3x  Rotation metadata (display matrix; ffmpeg's angle convention) ------
encode 30-h264-720.mp4 1280x720 1 "${X264[@]}"
encode 31-hevc-720.mp4 1280x720 1 "${X265[@]}"
encode 32-vp9-720.mp4  1280x720 1 "${VP9[@]}"
encode 33-av1-720.mp4  1280x720 1 "${AV1[@]}"
for base in 30-h264 31-hevc 32-vp9 33-av1; do
	for deg in 90 180 270; do
		rotate "$base-720-rot$deg.mp4" "$base-720.mp4" $deg
	done
done

# --- 4x  10-bit / HDR at 720p ----------------------------------------------
VF=$HDR10_VF encode 40-hevc10-hdr10-720.mp4 1280x720 1 "${X265_10[@]}" "${HDR10[@]}"
encode 41-av110-720.mp4        1280x720 1 "${AV1_10[@]}"

# --- 5x  Above the decoder's scale threshold -------------------------------
# Stock's cedarc gates its own (VE) scaler on nWidthTh/nHeightTh = 1920x1080
# (getScreenSize, prop_value 0; 2026-10-01): 1080p sources are left to the
# HWC's GPU scaler. Only a source ABOVE 1080p can show the VE scale recipe.
DUR=60 encode 50-vp9-2160.webm  3840x2160 1 "${VP9[@]}"
DUR=60 encode 51-hevc-2160.mp4  3840x2160 1 "${X265[@]}"
DUR=60 encode 52-h264-2160.mp4  3840x2160 1 "${X264[@]}"

# --- verify -----------------------------------------------------------------
# Size, codec, an audio track, the duration, and motion (three distinct frames).
fail=0
printf '%-34s %-10s %-11s %-6s %-7s %-6s %s\n' file codec size audio 'dur(s)' moving 'rotation (matrix; rotN = ffmpeg -display_rotation N, anticlockwise)'
for f in "$OUT"/[0-9]*; do
	n=$(basename "$f"); want "$n" || continue
	# TS lists each stream twice (under its program too): first hit only.
	v=$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height -of csv=p=0 "$f" | head -1 | tr ',' ' ')
	r=$(ffprobe -v error -select_streams v:0 -show_entries stream_side_data=rotation -of csv=p=0 "$f" | grep -m1 . || true)
	a=$(ffprobe -v error -select_streams a -show_entries stream=codec_name -of csv=p=0 "$f" | head -1)
	d=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f" | cut -d. -f1)
	h=$(for t in 3 13 23; do ffmpeg -v error -ss $t -i "$f" -frames:v 1 -f rawvideo - 2>/dev/null | md5sum; done | sort -u | wc -l)
	set -- $v
	ok=yes
	[ -n "$a" ] && [ "${d:-0}" -ge 15 ] && [ "$h" -ge 2 ] || { ok=NO; fail=1; }
	printf '%-34s %-10s %-11s %-6s %-7s %-6s %s %s\n' "$n" "$1" "$2x$3" "${a:-NONE}" "$d" "$h/3" "${r:-0}" "$([ $ok = yes ] || echo '<-- FAIL')"
done
du -sh "$OUT" | sed 's/^/total /'
exit $fail
