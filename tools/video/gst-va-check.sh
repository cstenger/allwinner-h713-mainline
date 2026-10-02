#!/bin/sh
# Per-frame: a GStreamer decoder element against ffmpeg software decode.
# RUNS ON THE TARGET.
#
#   sh gst-va-check.sh CLIP PARSER DECODER [N]
#   sh gst-va-check.sh /tmp/31-hevc-720.mp4 h265parse vah265dec 60
#   sh gst-va-check.sh /tmp/32-vp9-720.mp4 vp9parse v4l2slvp9dec
#
# Bit-exactness of GStreamer's va elements on this VA driver, which ffmpeg's
# gates never exercise (2026-10-02: they had never decoded a frame). Output goes
# to system memory, which is itself under test: until libva 0025 every
# download failed with a NULL GstMemory.
#
# N+1 frames are requested and the first N compared: identity eos-after cuts the
# stream there, and the last buffer before the cut came out differing, which is
# the cut and not the decoder. irq= counts both decoders' interrupts (cedrus
# and the AV1 core); setup_failures= counts cedrus refusing a job outright.
set -u
c=$1 parse=$2 dec=$3 n=${4:-60}
export GST_VA_ALL_DRIVERS=1 LIBVA_DRIVER_NAME=v4l2_request

case "$c" in *.webm|*.mkv) demux=matroskademux ;; *) demux=qtdemux ;; esac
w=$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of csv=p=0 "$c")
h=$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 "$c")

ffmpeg -v error -i "$c" -frames:v "$n" -an -pix_fmt nv12 -f framemd5 - |
	grep -v '^#' | awk -F', *' '{print $6}' > /tmp/gv.sw
f0=$(dmesg | grep -c 'setup decoding job')
a=$(awk '/1c0e000|1c0d000/ { s += $2 } END { print s }' /proc/interrupts)
# head -c bounds the file whatever the decoder does with the cut: /tmp is a RAM
# tmpfs, and 288 unbounded 720p frames came within 60 MB of filling it.
gst-launch-1.0 -q filesrc location="$c" ! $demux ! $parse ! "$dec" ! \
	video/x-raw,format=NV12 ! identity eos-after=$((n + 1)) ! fdsink fd=1 2>/dev/null |
	head -c $(( (n + 1) * w * h * 3 / 2 )) > /tmp/gv.nv12
b=$(awk '/1c0e000|1c0d000/ { s += $2 } END { print s }' /proc/interrupts)

# filesink writes tightly packed NV12 here; hash the first N frames the same way.
python3 - "$w" "$h" "$n" <<'PY'
import hashlib, sys
w, h, n = (int(v) for v in sys.argv[1:4])
fs = w * h * 3 // 2
# Read only what is compared: a decoder that ignores the cut can write far more
# than RAM (2026-10-02: 288 frames, and the OOM killer took this script).
d = open('/tmp/gv.nv12', 'rb').read(n * fs)
frames = [d[i:i + fs] for i in range(0, len(d) - fs + 1, fs)][:n]
open('/tmp/gv.hw', 'w').write(''.join(hashlib.md5(f).hexdigest() + '\n' for f in frames))
PY
s=$(paste -d' ' /tmp/gv.sw /tmp/gv.hw | awk '$1 == $2' | wc -l)
bad=$(paste -d' ' /tmp/gv.sw /tmp/gv.hw | awk '$1 != $2 { print NR - 1; exit }')
echo "$(basename "$c") $dec: $s/$(wc -l < /tmp/gv.sw) identical (compared $(wc -l < /tmp/gv.hw)) first_bad=${bad:-none} irq+$((b - a)) setup_failures=$(( $(dmesg | grep -c 'setup decoding job') - f0 ))"
rm -f /tmp/gv.nv12
