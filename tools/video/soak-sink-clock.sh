#!/bin/sh
# Overnight 2-hour A/V drift soak for the sink-clock gst-plane-play
# (commit 15ec2d9). RUNS ON THE TARGET, unattended.
#
# WHY. Until 15ec2d9 the plane routes ran on the system clock with alsasink
# slaved to it; the 2-hour soak on 2026-10-04 measured drift +18.1 ms over
# 2 h (sync +15.8 -> +33.9 ms). alsasink now provides the pipeline clock,
# which fixed the clip-start audio gap, and 40-s clips read -1.2 / -2.2 ms,
# but long-run drift on the new clock has not been measured. This repeats
# the 10-04 soak exactly (1080p H.264, plane-ve, 7500 s clip, 122 minutes)
# so the two drifts compare directly.
#
# The clip: tools/video/make-avsync-clip.sh OUTDIR 7500 (host), ~45 MB, too
# big for the board's nearly full root fs, so it is staged in /dev/shm
# (lost on reboot: re-stage after any power cycle).
#
#   usage: soak-sink-clock.sh [CLIP]        foreground
#          soak-sink-clock.sh --detach [CLIP]
#                                           survives the ssh session; poll
#                                           the result file for "DONE"
#   env:   PLAY   player (default /root/h713-play.repo, staged from the repo)
#          PROBE  av-sync-probe (default /root/av-sync-probe)
#          SOAK   plane-soak.sh (default /root/plane-soak.sh)
#          OUT    result file (default /root/soak/sink-clock-2h.txt)
#          MIN    minutes (default 122; MIN=2 with a short clip is a smoke
#                 test of the whole path, not a measurement)
#
# Result: /root/soak/sink-clock-2h.txt (a few lines; the root fs is ~99%
# full). Compare its SOAK SUMMARY drift with +18.1 ms. The DAC is muted with
# its VOLUME for the run and restored to 63 after; never Speaker Switch 0,
# which stalls the PCM DMA and voided the first 2-hour attempt.
set -u
OUT=${OUT:-/root/soak/sink-clock-2h.txt}

if [ "${1:-}" = --detach ]; then
	shift
	setsid nohup sh "$0" "$@" > /dev/null 2>&1 < /dev/null &
	echo "soak-sink-clock: detached (pid $!); result in $OUT"
	exit 0
fi

CLIP=${1:-/dev/shm/avsync-1080p-7500.mp4}
PLAY=${PLAY:-/root/h713-play.repo}
export PLAY PROBE=${PROBE:-/root/av-sync-probe}
SOAK=${SOAK:-/root/plane-soak.sh}
export PIPEWIRE_RUNTIME_DIR=/run/user/1000
CTL=/root/tools/alsa-ctl

mkdir -p /root/soak
{
	echo "soak-sink-clock: start $(date -u +%FT%TZ) uptime $(cut -d' ' -f1 /proc/uptime) s"
	echo "player binary: $(md5sum /usr/local/bin/gst-plane-play)"
	echo "clip: $CLIP ($(ffprobe -v error -show_entries format=duration -of csv=p=0 "$CLIP" 2>&1))"
} > "$OUT"

for f in "$CLIP" "$PLAY" "$PROBE" "$SOAK" "$CTL"; do
	[ -e "$f" ] || { echo "SOAK ERROR: missing $f" >> "$OUT"; echo DONE >> "$OUT"; exit 2; }
done

trap '"$CTL" "DAC Playback Volume" 63 > /dev/null 2>&1' EXIT INT TERM
"$CTL" "DAC Playback Volume" 0 > /dev/null
iommu0=$(dmesg | grep -ci iommu)
sh "$SOAK" "$CLIP" "${MIN:-122}" >> "$OUT" 2>&1
echo "SOAK iommu_msgs=$(($(dmesg | grep -ci iommu) - iommu0)) (new kernel lines mentioning iommu during the run; want 0)" >> "$OUT"
echo "soak-sink-clock: end $(date -u +%FT%TZ)" >> "$OUT"
echo DONE >> "$OUT"
