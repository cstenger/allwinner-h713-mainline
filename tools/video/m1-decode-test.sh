#!/bin/bash
# M1 — does the H713 VE actually decode? Runs ON THE TARGET.
#
# Cedrus binding proves nothing about the silicon: it binds on a DT compatible
# and clock handles, and nothing in a successful probe touches a codec register.
# This script is the actual gate.
#
# STATUS 2026-08-09: all five vectors PASS bit-exact on the bench board. Keep
# this as the regression test -- the failure it originally caught (the ve node's
# `iommus` naming an IOMMU that does not exist at that address) corrupted kernel
# memory and panicked the board rather than reporting an error.
#
# Scoring is per-vector, and the ladder is the instrument: v01 failing and v03
# failing mean completely different things. See docs/video-decode.md.
#
#   usage: ./m1-decode-test.sh [vector-name ...]     (default: all)

set -u

DIR=$(cd "$(dirname "$0")" && pwd)
OUT=${OUT:-/tmp/m1-out}
DEV=${DEV:-/dev/video0}
REF=${REF:-$DIR/reference-md5.txt}
mkdir -p "$OUT"

# The kernel clock as this run starts, so the dmesg section at the bottom can
# show THIS RUN's messages instead of whatever happens to be in the ring.
KMSG_T0=$(cut -d' ' -f1 /proc/uptime 2>/dev/null || echo 0)

hr() { printf '\n=== %s ===\n' "$1"; }

# `dmesg | tail -20` under a heading that says "from this run" attributes
# whatever is in the ring buffer to the run that just finished. On 2026-09-22 a
# clean 5/5 ladder printed six "frame processing timed out!" lines that predated
# it by 26 minutes, which reads as a decode that timed out and passed anyway.
# Filter on the kernel timestamp instead.
#
# Returns 1 if dmesg is unreadable and 2 if its lines carry no timestamps to
# filter on -- both of which otherwise produce an empty section that looks
# exactly like "the run was clean".
kmsg_this_run() {   # extended-regex pattern
  local buf
  buf=$(dmesg 2>/dev/null) || return 1
  printf '%s\n' "$buf" | grep -q '^\[[ ]*[0-9][0-9]*\.' || return 2
  printf '%s\n' "$buf" | awk -v t0="$KMSG_T0" '
    match($0, /^\[[ ]*[0-9]+\.[0-9]+\]/) {
      if (substr($0, RSTART + 1, RLENGTH - 2) + 0 >= t0) print
    }' | grep -iE "$1" | tail -20
}

# Print that section, saying which of "nothing happened" and "could not look"
# it is rather than letting both render as blank.
report_kmsg() {   # extended-regex pattern
  local out rc
  out=$(kmsg_this_run "$1"); rc=$?
  case $rc in
  1) echo "  (dmesg unreadable -- run as root to see kernel messages)" ;;
  2) echo "  (dmesg carries no timestamps -- cannot scope to this run;"
     echo "   showing the last 20 matching lines UNSCOPED, which may predate it)"
     dmesg 2>/dev/null | grep -iE "$1" | tail -20 | sed 's/^/  /' ;;
  *) if [ -z "$out" ]; then
       echo "  (none since this run started, at kernel t=${KMSG_T0}s)"
     else
       printf '%s\n' "$out" | sed 's/^/  /'
     fi ;;
  esac
}

# WITHOUT THE REFERENCES THIS SCRIPT CANNOT FAIL, so it refuses to run at all.
# It used to grep a missing file, get nothing back, and land in the "no
# reference on file; size only" branch -- which increments neither pass nor
# fail -- for every vector. The ladder then reported "M1: 0 pass, 0 fail" and
# exited 0, having compared not one pixel. A fresh flash is exactly the case
# that hits this: the file ships in tools/video/ and has to be copied next to
# the script. Deploy it, or point REF at it.
if [ ! -s "$REF" ]; then
  echo "FATAL: no reference hashes at $REF" >&2
  echo "" >&2
  echo "  This gate scores decoded output against per-frame and whole-file md5s." >&2
  echo "  Without them nothing here can fail, so refusing to report a result." >&2
  echo "" >&2
  echo "  Fix: copy tools/video/reference-md5.txt from the repo to $DIR/," >&2
  echo "  or run with REF=/path/to/reference-md5.txt" >&2
  exit 2
fi

hr "device"
if [ ! -e "$DEV" ]; then
  echo "FAIL: $DEV does not exist -- cedrus did not register"
  exit 1
fi
cat "/sys/class/video4linux/$(basename "$DEV")/name" 2>/dev/null
v4l2-ctl -d "$DEV" --info 2>&1 | sed 's/^/  /'

hr "output formats (what the decoder ACCEPTS -- the codecs)"
v4l2-ctl -d "$DEV" --list-formats-out 2>&1 | sed 's/^/  /'

hr "capture formats (what the decoder EMITS -- the pixel layouts)"
v4l2-ctl -d "$DEV" --list-formats 2>&1 | sed 's/^/  /'

hr "gstreamer stateless decoder elements"
# The stateless decoders register at runtime only when a compatible device
# exists, so an empty list here is itself the result -- it means GStreamer
# looked at this driver and declined.
gst-inspect-1.0 2>/dev/null | grep -iE "v4l2sl|v4l2.*dec" | sed 's/^/  /' \
  || echo "  (none found)"

hr "decode runs"
pass=0; fail=0
vectors=${*:-"v01-320x240-baseline v02-1280x720-baseline v03-1280x720-main v04-1280x720-high v05-1920x1080-high"}

for v in $vectors; do
  src="$DIR/$v.h264"
  [ -f "$src" ] || { echo "  SKIP $v (no stream)"; continue; }
  dst="$OUT/$v.nv12"
  rm -f "$dst"

  printf '\n-- %s\n' "$v"
  # Forcing NV12 is REQUIRED, not just tidy. Left unconstrained the decoder
  # negotiates NV12_32L32 -- Allwinner's 32x32 tiled layout -- and emits
  # ALIGN(height,32) rows (320x240 becomes 122880 bytes/frame, not 115200).
  # That output is correct but tiled, so it can never match a linear reference
  # and reads as a failure if scored naively.
  GST_DEBUG=${GST_DEBUG:-1} timeout 120 gst-launch-1.0 -q \
      filesrc location="$src" ! h264parse ! v4l2slh264dec \
      ! video/x-raw,format=NV12 ! filesink location="$dst" 2>&1 \
    | sed 's/^/     /'

  if [ -s "$dst" ]; then
    md5=$(md5sum "$dst" | cut -d' ' -f1)
    want=$(grep "^$v WHOLE" "$REF" | awk '{print $NF}')
    nframes=$(grep "^$v WHOLE" "$REF" | awk '{print $3}')
    printf '     output %s bytes, md5 %s\n' "$(stat -c%s "$dst")" "$md5"
    if [ -n "$want" ] && [ "$md5" = "$want" ]; then
      echo "     PASS -- bit-exact against the host reference ($nframes frames)"
      pass=$((pass+1))
    elif [ -n "$want" ]; then
      echo "     MISMATCH -- decoded, but not bit-exact (want $want)"
      echo "     Decoded output exists, so the engine ran. Could be stride"
      echo "     padding, frame count, or genuinely wrong pixels -- pull the"
      echo "     file to the host and compare with ffmpeg PSNR before judging."
      fail=$((fail+1))
    else
      # A present-but-incomplete reference file is the same blind spot as a
      # missing one, one vector at a time -- so an unscored vector counts as a
      # failure rather than vanishing from both tallies.
      echo "     UNVERIFIABLE -- no '$v WHOLE' line in $REF"
      echo "     Decoded something, but nothing checked it. Counting as a failure."
      fail=$((fail+1))
    fi
  else
    echo "     FAIL -- no output produced"
    fail=$((fail+1))
  fi
done

hr "kernel messages from this run"
report_kmsg "cedrus|video-codec"

printf '\nM1: %d pass, %d fail\n' "$pass" "$fail"

# The script used to end on that printf, exiting 0 whatever the tally said --
# so a MISMATCH on every vector still reported success to anything that checked
# $?, and the UNVERIFIABLE count added above would have been decoration. A
# run that scored nothing at all is also a failure: "0 pass, 0 fail" is what a
# missing vector set looks like, and it is not a green run.
if [ $((pass + fail)) -eq 0 ]; then
  echo "M1: scored nothing -- no vector produced a comparable result."
  echo "    Check the streams are deployed next to the script."
  exit 1
fi
[ "$fail" -eq 0 ]
