#!/bin/sh
# Make the A/V sync clips for tools/video/av-sync-probe.c. RUNS ON THE HOST.
#
# Black video with a full-screen white flash (two frames) and a 1 kHz beep
# (50 ms) at the same instants, so a correct player puts the beep on the
# flash. The instants are IRREGULAR (0.7-1.4 s apart, on frame boundaries):
# with a beep every second, audio 770 ms late paired with the next flash and
# read as 230 ms early. av-sync-probe matches the whole sequence, which only
# one offset can do. aevalsrc, not sine+volume=enable: the enable
# switch acts on whole 1024-sample frames, which smeared the onsets by 9-21 ms.
# The AAC is 44.1 kHz like most real files, so the player has to resample.
#
#   usage: make-avsync-clip.sh [OUTDIR]   -> avsync-1080p.mp4, avsync-720p.mp4
set -eu
out=${1:-.}
# Event times in frames (30 fps): steps cycle through 21..42 frames.
on=$(awk 'BEGIN { f = 0; split("21 33 27 42 24 36 30 39", d);
	for (i = 0; f < 1170; i++) { printf "%sbetween(t\\,%.6f\\,%.6f)", i ? "+" : "", f / 30, f / 30 + 0.05; f += d[i % 8 + 1] } }')
ffmpeg -v error -y \
	-f lavfi -i "color=c=black:s=1920x1080:r=30:d=40,drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='$on'" \
	-f lavfi -i "aevalsrc='0.8*sin(2*PI*1000*t)*($on)':s=44100:d=40" \
	-c:v libx264 -profile:v high -pix_fmt yuv420p -g 30 \
	-c:a aac -b:a 128k -ac 2 -shortest "$out/avsync-1080p.mp4"
ffmpeg -v error -y -i "$out/avsync-1080p.mp4" -vf scale=1280:720 \
	-c:v libx264 -g 30 -c:a copy "$out/avsync-720p.mp4"
echo "wrote $out/avsync-1080p.mp4 $out/avsync-720p.mp4"
