#!/bin/sh
# Make the A/V sync clips for tools/video/av-sync-probe.c. RUNS ON THE HOST.
#
# Black video with a full-screen white flash (two frames) and a 1 kHz beep
# (50 ms) at the same instants, so a correct player puts the beep on the
# flash. The instants are IRREGULAR (0.7-1.4 s apart, on frame boundaries):
# with a beep every second, audio 770 ms late paired with the next flash and
# read as 230 ms early. av-sync-probe matches the whole sequence within +-3 s,
# which only one offset can do; the pattern repeats every 8.4 s, so that holds.
# aevalsrc, not sine+volume=enable: the enable switch acts on whole
# 1024-sample frames, which smeared the onsets by 9-21 ms. The AAC is 44.1 kHz
# like most real files, so the player has to resample.
#
#   usage: make-avsync-clip.sh [OUTDIR] [SECONDS] [all]
#     -> avsync-1080p.mp4, avsync-720p.mp4 (H.264); with "all" also
#        avsync-1080p-hevc.mp4, avsync-720p-hevc.mp4, avsync-720p-vp9.webm,
#        avsync-720p-av1.mp4 (the WP4 soak set). SECONDS defaults to 40.
set -eu
out=${1:-.}
secs=${2:-40}
# Event offsets in frames within one 252-frame (8.4 s) cycle: steps
# 21 33 27 42 24 36 30 39. Video keys on the integer frame number n (two
# frames lit) and audio on t*30 (1.5 frames = 50 ms), both in frame units:
# mod(t, 8.4) on frame times put some flashes a frame late after 10 minutes,
# because 8.4 is not exact in binary.
ev=$(awk 'BEGIN { split("0 21 54 81 123 147 183 213", f);
	for (i = 1; i <= 8; i++) printf "%s%d", (i > 1 ? " " : ""), f[i] }')
von=$(for e in $ev; do printf '+between(mod(n\,252)\,%d\,%d)' "$e" $((e + 1)); done | cut -c2-)
aon=$(for e in $ev; do printf '+between(mod(t*30\,252)\,%d\,%d.5)' "$e" "$((e + 1))"; done | cut -c2-)
ffmpeg -v error -y \
	-f lavfi -i "color=c=black:s=1920x1080:r=30:d=$secs,drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='$von'" \
	-f lavfi -i "aevalsrc='0.8*sin(2*PI*1000*t)*($aon)':s=44100:d=$secs" \
	-c:v libx264 -profile:v high -pix_fmt yuv420p -g 30 \
	-c:a aac -b:a 128k -ac 2 -shortest "$out/avsync-1080p.mp4"
ffmpeg -v error -y -i "$out/avsync-1080p.mp4" -vf scale=1280:720 \
	-c:v libx264 -g 30 -c:a copy "$out/avsync-720p.mp4"
echo "wrote $out/avsync-1080p.mp4 $out/avsync-720p.mp4 (${secs} s)"
[ "${3:-}" = all ] || exit 0
ffmpeg -v error -y -i "$out/avsync-1080p.mp4" -c:v libx265 -x265-params log-level=error \
	-pix_fmt yuv420p -g 30 -c:a copy "$out/avsync-1080p-hevc.mp4"
ffmpeg -v error -y -i "$out/avsync-720p.mp4" -c:v libx265 -x265-params log-level=error \
	-pix_fmt yuv420p -g 30 -c:a copy "$out/avsync-720p-hevc.mp4"
ffmpeg -v error -y -i "$out/avsync-720p.mp4" -c:v libvpx-vp9 -deadline realtime \
	-cpu-used 8 -b:v 1M -g 30 -c:a libopus -b:a 128k "$out/avsync-720p-vp9.webm"
# Low-delay prediction: SVT-AV1's default hierarchy left the first lit frame
# of most flashes too dim, so they read one frame late (33 ms of fake skew).
ffmpeg -v error -y -i "$out/avsync-720p.mp4" -c:v libsvtav1 -preset 10 \
	-svtav1-params pred-struct=1 -g 30 \
	-pix_fmt yuv420p -c:a copy "$out/avsync-720p-av1.mp4"
echo "wrote the HEVC, VP9 and AV1 variants"
