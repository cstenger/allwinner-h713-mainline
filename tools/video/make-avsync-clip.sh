#!/bin/sh
# Make the A/V sync clips for tools/video/av-sync-probe.c. RUNS ON THE HOST.
#
# Black video with a full-screen white flash on frames 0-1 of every second,
# and a 1 kHz beep starting on every whole second (50 ms), so a correct player
# puts the beep on the flash. aevalsrc, not sine+volume=enable: the enable
# switch acts on whole 1024-sample frames, which smeared the onsets by 9-21 ms.
# The AAC is 44.1 kHz like most real files, so the player has to resample.
#
#   usage: make-avsync-clip.sh [OUTDIR]   -> avsync-1080p.mp4, avsync-720p.mp4
set -eu
out=${1:-.}
ffmpeg -v error -y \
	-f lavfi -i "color=c=black:s=1920x1080:r=30:d=40,drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='lt(mod(t\,1)\,0.05)'" \
	-f lavfi -i "aevalsrc='0.8*sin(2*PI*1000*t)*lt(mod(t\,1)\,0.05)':s=44100:d=40" \
	-c:v libx264 -profile:v high -pix_fmt yuv420p -g 30 \
	-c:a aac -b:a 128k -ac 2 -shortest "$out/avsync-1080p.mp4"
ffmpeg -v error -y -i "$out/avsync-1080p.mp4" -vf scale=1280:720 \
	-c:v libx264 -g 30 -c:a copy "$out/avsync-720p.mp4"
echo "wrote $out/avsync-1080p.mp4 $out/avsync-720p.mp4"
