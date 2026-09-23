#!/bin/bash
# M2 -- does cedrus decode MPEG-2 correctly, and still? RUNS ON THE TARGET.
#
# THIS GATE IS SHAPED DIFFERENTLY FROM THE H.264 AND HEVC ONES, on purpose.
#
# H.264, HEVC and VP8 define exact integer reconstruction, so a host software
# decode is a correctness ORACLE and the target must match it bit-for-bit.
# MPEG-2 (ISO/IEC 13818-2) specifies an IDCT *accuracy requirement* instead: a
# conformant hardware IDCT is allowed to differ from any particular software
# one, and here it does, by about 72 dB PSNR. Scoring MPEG-2 by md5 against a
# software decode would therefore fail permanently and correctly.
#
# So this gate asks three separate questions, because no one of them is enough:
#
#   1. md5 vs a PINNED HARDWARE BASELINE  -- regression detection. Does the
#      engine still produce exactly what it produced when the port was
#      validated? This is exact, and it is the part that catches a change.
#   2. PSNR vs a software decode          -- correctness. A baseline can pin a
#      bug: if the engine were broken when the baseline was captured, question 1
#      would pass forever. PSNR is what says the pixels are actually right.
#      Expect ~72 dB. NOT inf -- inf means a software fallback, not success.
#   3. VE interrupt delta                 -- proves the hardware did the work.
#      A silent software fallback would sail through 1 and 2 otherwise.
#
# The baseline lives in mpeg2-reference-md5.txt and is committed. Without it
# this script refuses to run: a missing reference used to mean every vector
# scored "no reference on file" and the run exited 0 having checked nothing.
#
#   usage: ./mpeg2-decode-test.sh [vector-name ...]
#          ./mpeg2-decode-test.sh --capture-reference     (re-baseline; read the
#                                                          warning it prints)

set -u

DIR=$(cd "$(dirname "$0")" && pwd)
# NOT /tmp on this image: it is a 467 MB tmpfs and tmpfs is RAM. m03 alone is
# 69 MB of hardware output plus 69 MB of software output.
OUT=${OUT:-/var/tmp/m2-out}
REF=${REF:-$DIR/mpeg2-reference-md5.txt}
# Per-vector PSNR floors live in the table below (55 dB: well under the ~72 dB an
# IDCT difference produces, well over anything actually broken -- a floor, not a
# target). Setting PSNR_MIN here overrides every one of them.
PSNR_MIN=${PSNR_MIN:-}

# name:width:height:frames:psnr_floor:psnr_frames
#
# m05 is field-coded (31 frames as 62 pictures) and is the only rung that
# exercises kernel patch 0123; it ships as a committed binary because ffmpeg
# cannot encode field pictures. See vectors/README.md.
#
# m05 compares 30 of its 31 frames. Its final frame is genuinely damaged -- the
# stream carries no sequence_end_code, ffmpeg reports "ac-tex damaged at 0 22"
# on it, and the analysis in docs/reference/inherited-codecs-2026-09-17.md
# established that as the stream's property, not the decoder's. Since ffmpeg
# averages MSE rather than dB, that one frame at ~24 dB drags a 31-frame average
# to roughly 39 dB and would fail a floor that every good frame passes. Excluding
# it keeps the SAME strict floor on the 30 frames that are real evidence, which
# is more discriminating than lowering the floor for the whole vector.
VECTORS_ALL="m01-352x288-progressive:352:288:25:55:0
m02-720x576-progressive:720:576:50:55:0
m03-1280x720-progressive:1280:720:50:55:0
m04-720x576-interlaced:720:576:50:55:0
m05-720x576-field:720:576:31:55:30"

CAPTURE=0
[ "${1:-}" = "--capture-reference" ] && { CAPTURE=1; shift; }

mkdir -p "$OUT"

# Kernel clock at startup, so the dmesg section reports THIS run rather than
# whatever is in the ring buffer. See the note in va-decode-test.sh.
KMSG_T0=$(cut -d' ' -f1 /proc/uptime 2>/dev/null || echo 0)

hr() { printf '\n=== %s ===\n' "$1"; }

kmsg_this_run() {   # extended-regex pattern
  local buf
  buf=$(dmesg 2>/dev/null) || return 1
  printf '%s\n' "$buf" | grep -q '^\[[ ]*[0-9][0-9]*\.' || return 2
  printf '%s\n' "$buf" | awk -v t0="$KMSG_T0" '
    match($0, /^\[[ ]*[0-9]+\.[0-9]+\]/) {
      if (substr($0, RSTART + 1, RLENGTH - 2) + 0 >= t0) print
    }' | grep -iE "$1" | tail -20
}

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

if [ "$CAPTURE" -eq 0 ] && [ ! -s "$REF" ]; then
  echo "FATAL: no reference hashes at $REF" >&2
  echo "" >&2
  echo "  This gate scores hardware output against a pinned hardware baseline." >&2
  echo "  Without it nothing here can fail, so refusing to report a result." >&2
  echo "" >&2
  echo "  Fix: copy tools/video/mpeg2-reference-md5.txt from the repo to $DIR/," >&2
  echo "  or run with REF=/path/to/mpeg2-reference-md5.txt" >&2
  echo "" >&2
  echo "  To create one from THIS board: $0 --capture-reference" >&2
  exit 2
fi

ve_irq() {
  awk '/video-codec/ { for (i = 2; i <= 5; i++) s += $i } END { print s + 0 }' \
    /proc/interrupts
}

# Forcing NV12 is REQUIRED, not tidy: unconstrained, the decoder negotiates
# NV12_32L32 (Allwinner 32x32 tiled), which is correct output that can never
# match a linear baseline and reads as a failure if scored naively.
decode_hw() {   # stream, dst
  GST_DEBUG=${GST_DEBUG:-1} timeout 300 gst-launch-1.0 -q \
    filesrc location="$1" ! mpegvideoparse ! v4l2slmpeg2dec \
    ! video/x-raw,format=NV12 ! filesink location="$2" 2>&1 | sed 's/^/     /'
}

decode_sw() {   # stream, dst
  ffmpeg -hide_banner -v error -i "$1" -f rawvideo -pix_fmt nv12 -y "$2" 2>&1 |
    sed 's/^/     /'
}

# PSNR between two raw NV12 files of known geometry. ffmpeg's psnr filter prints
# "average:NN.NN"; inf comes back as "inf", which is a RED FLAG here rather than
# a perfect score -- see the header.
#
# -v info is LOAD-BEARING. The psnr filter logs its summary at INFO, so under
# the -v error used everywhere else in this file the line does not exist and
# every vector reports "PSNR could not be measured" -- which this script counts
# as a failure, so it fails loudly rather than silently, but it is still wrong.
#
# $5 optionally limits how many frames are compared, for streams whose tail is
# known-damaged; 0 or unset compares everything.
psnr_of() {   # a, b, w, h, [frames]
  local lim=""
  [ "${5:-0}" -gt 0 ] 2>/dev/null && lim="-frames:v $5"
  ffmpeg -hide_banner -v info \
    -f rawvideo -pix_fmt nv12 -s "${3}x${4}" -i "$1" \
    -f rawvideo -pix_fmt nv12 -s "${3}x${4}" -i "$2" \
    -lavfi psnr $lim -f null - 2>&1 |
    sed -n 's/.*average:\([0-9.a-z]*\).*/\1/p' | tail -1
}

want_md5() { grep "^$1 WHOLE" "$REF" | awk '{print $NF}'; }
want_frames() { grep "^$1 WHOLE" "$REF" | awk '{print $3}'; }

pick() {   # vector -> "name:w:h:frames" or empty
  printf '%s\n' "$VECTORS_ALL" | grep "^$1:"
}

# ---------------------------------------------------------------- capture mode
if [ "$CAPTURE" -eq 1 ]; then
  hr "CAPTURE REFERENCE -- read this"
  cat <<'WARN'
  This OVERWRITES the baseline with whatever this board produces right now.
  If the decoder is broken today, the new baseline pins the breakage and the
  gate will pass forever afterwards.

  Only do this when the output has been independently shown correct -- the
  PSNR-vs-software check in a normal run is what does that -- or when a
  deliberate change to the decoder makes the old baseline wrong.
WARN
  tmp=$OUT/mpeg2-reference-md5.txt.new
  {
    echo "# MPEG-2 hardware decode baseline for H713 cedrus."
    echo "#"
    echo "# These are the HARDWARE's own md5s, not a software reference: MPEG-2"
    echo "# specifies IDCT accuracy rather than exact reconstruction, so software"
    echo "# and hardware legitimately differ (~72 dB). This file therefore detects"
    echo "# REGRESSION; mpeg2-decode-test.sh's PSNR check is what shows the output"
    echo "# is correct in the first place."
    echo "#"
    # Do not stamp a date this board cannot vouch for. Its RTC has read 1970
    # with NTP unsynced, which put a capture five months in the past -- and a
    # baseline mis-dated by five months is worse than one with no date, because
    # it looks authoritative. Pass CAPTURE_DATE to supply the real one.
    if [ -n "${CAPTURE_DATE:-}" ]; then
      echo "# captured $CAPTURE_DATE (supplied by the operator)"
      echo "#           board clock said $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    else
      sync=$(timedatectl show -p NTPSynchronized --value 2>/dev/null || echo unknown)
      if [ "$sync" = "yes" ]; then
        echo "# captured $(date -u +%Y-%m-%dT%H:%M:%SZ) (board clock, NTP-synced)"
      else
        echo "# captured $(date -u +%Y-%m-%dT%H:%M:%SZ) by the BOARD CLOCK, which is"
        echo "#           NOT NTP-synced (hwclock: $(hwclock -r 2>&1 | head -1 | cut -c1-24))."
        echo "#           TREAT THIS DATE AS UNRELIABLE. Re-run with CAPTURE_DATE set."
      fi
    fi
    echo "# host     $(uname -n)"
    echo "# kernel   $(uname -r)"
    echo "# gst      $(gst-launch-1.0 --version 2>/dev/null | head -1)"
    echo "#"
  } > "$tmp"
fi

hr "vectors"
vectors=${*:-"m01-352x288-progressive m02-720x576-progressive m03-1280x720-progressive m04-720x576-interlaced m05-720x576-field"}
echo "  $vectors"

pass=0; fail=0
for v in $vectors; do
  spec=$(pick "$v")
  if [ -z "$spec" ]; then echo "  SKIP $v (not a known vector)"; continue; fi
  w=$(echo "$spec" | cut -d: -f2); h=$(echo "$spec" | cut -d: -f3)
  nf=$(echo "$spec" | cut -d: -f4)
  # An explicit PSNR_MIN in the environment overrides every per-vector floor.
  floor=${PSNR_MIN:-$(echo "$spec" | cut -d: -f5)}
  plim=$(echo "$spec" | cut -d: -f6)

  src="$DIR/$v.m2v"
  [ -f "$src" ] || { echo "  SKIP $v (no stream at $src)"; continue; }

  printf '\n-- %s (%sx%s, %s frames)\n' "$v" "$w" "$h" "$nf"
  hw="$OUT/$v.hw.nv12"; sw="$OUT/$v.sw.nv12"
  rm -f "$hw" "$sw"

  a=$(ve_irq)
  decode_hw "$src" "$hw"
  ve=$(( $(ve_irq) - a ))

  if [ ! -s "$hw" ]; then
    echo "     FAIL -- no hardware output produced"
    fail=$((fail+1)); rm -f "$hw" "$sw"; continue
  fi

  md5=$(md5sum "$hw" | cut -d' ' -f1)
  bytes=$(stat -c%s "$hw")
  want_bytes=$(( w * h * 3 / 2 * nf ))
  printf '     hw  %s bytes (want %s), md5 %s, ve+%s\n' "$bytes" "$want_bytes" "$md5" "$ve"

  if [ "$CAPTURE" -eq 1 ]; then
    # Per-frame lines as well as the whole-file one, so a future mismatch can
    # name the frame it starts at instead of just "the file differs".
    python3 - "$hw" "$v" "$(( w * h * 3 / 2 ))" >> "$tmp" <<'PY'
import hashlib, sys
path, name, fsize = sys.argv[1], sys.argv[2], int(sys.argv[3])
n = 0
with open(path, 'rb') as fh:
    while True:
        d = fh.read(fsize)
        if len(d) < fsize: break
        print(f"{name} frame{n:04d} {hashlib.md5(d).hexdigest()}")
        n += 1
PY
    echo "$v WHOLE $(( bytes / (w * h * 3 / 2) )) frames $md5" >> "$tmp"
    echo "     captured"
    rm -f "$hw" "$sw"
    continue
  fi

  # ---- question 3: did the hardware actually run?
  if [ "$ve" -eq 0 ]; then
    echo "     FAIL -- VE interrupt count did not move: this was NOT hardware decode"
    fail=$((fail+1)); rm -f "$hw" "$sw"; continue
  fi

  # ---- question 1: regression against the pinned hardware baseline
  want=$(want_md5 "$v"); wf=$(want_frames "$v")
  if [ -z "$want" ]; then
    echo "     UNVERIFIABLE -- no '$v WHOLE' line in $REF"
    echo "     Decoded something, but nothing checked it. Counting as a failure."
    fail=$((fail+1)); rm -f "$hw" "$sw"; continue
  fi
  if [ "$md5" = "$want" ]; then
    md5_ok=1; echo "     md5  MATCH -- identical to the pinned baseline ($wf frames)"
  else
    md5_ok=0; echo "     md5  CHANGED -- differs from baseline (want $want)"
  fi

  # ---- question 2: is it actually right, or is the baseline pinning a bug?
  decode_sw "$src" "$sw"
  if [ ! -s "$sw" ]; then
    echo "     PSNR skipped -- software decode produced nothing"
    p="n/a"; psnr_ok=0
  else
    p=$(psnr_of "$hw" "$sw" "$w" "$h" "$plim")
    if [ "$p" = "inf" ]; then
      # Identical to software means the IDCT difference vanished, which on this
      # codec means something decoded it in software. Not a pass.
      echo "     PSNR inf -- IDENTICAL to software decode, which MPEG-2 should not be."
      echo "     Suspect a software fallback despite the VE interrupts."
      psnr_ok=0
    elif [ -z "$p" ]; then
      echo "     PSNR could not be measured"
      p="n/a"; psnr_ok=0
    else
      psnr_ok=$(awk -v a="$p" -v m="$floor" 'BEGIN { print (a >= m) ? 1 : 0 }')
      scope=$([ "$plim" -gt 0 ] 2>/dev/null && echo " over $plim of $nf frames" || echo "")
      if [ "$psnr_ok" -eq 1 ]; then
        echo "     PSNR $p dB vs software$scope (>= $floor, finite: an IDCT difference)"
      else
        echo "     PSNR $p dB vs software$scope -- BELOW $floor, the output is wrong"
      fi
    fi
  fi

  if [ "$md5_ok" -eq 1 ] && [ "$psnr_ok" -eq 1 ]; then
    echo "     PASS"
    pass=$((pass+1))
  else
    echo "     FAIL"
    fail=$((fail+1))
  fi
  # One vector at a time: m03 is 138 MB of the two decodes together and this
  # rootfs runs near full.
  rm -f "$hw" "$sw"
done

if [ "$CAPTURE" -eq 1 ]; then
  mv "$tmp" "$OUT/mpeg2-reference-md5.txt"
  hr "captured"
  echo "  $OUT/mpeg2-reference-md5.txt"
  echo "  $(grep -c WHOLE "$OUT/mpeg2-reference-md5.txt") vectors, $(wc -l < "$OUT/mpeg2-reference-md5.txt") lines"
  echo "  Copy it to tools/video/ in the repo and commit it."
  exit 0
fi

hr "kernel messages from this run"
report_kmsg "cedrus|video-codec"

printf '\nM2: %d pass, %d fail\n' "$pass" "$fail"
if [ $((pass + fail)) -eq 0 ]; then
  echo "M2: scored nothing -- no vector produced a comparable result."
  exit 1
fi
[ "$fail" -eq 0 ]
