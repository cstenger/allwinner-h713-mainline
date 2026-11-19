#!/usr/bin/env bash
# Read the whole eMMC of a board running stock Android over adb, in chunks,
# verifying each chunk against a hash computed on the board. Read-only.
#
#   tools/stock/adb-emmc-capture.sh OUT_DIR NAME [CHUNK_MIB]
#
# XFER_TIMEOUT (s, default 600) bounds each adb transfer; 3 tries per chunk.
# RESUME=N continues an interrupted run at chunk N (the .img must hold exactly
# N chunks). LIVE_FROM_SECTOR=S: a chunk ending above sector S lies in a
# partition Android has mounted read-write (UDISK = /data), so it can change
# between the host read and the board's hash; such a chunk is kept with
# status "live" instead of failing. Every chunk below S must match.
#
# Writes OUT_DIR/NAME.img, NAME.img.sha256, NAME.chunks.tsv and NAME.capture.log.
# Needs /dev/block/mmcblk0 readable by the adb shell user (true on stock H713
# Android). Captures hold per-unit secrets: keep them under local/ only.
set -euo pipefail

out=${1:?OUT_DIR}; name=${2:?NAME}; chunk=${3:-256}
dev=/dev/block/mmcblk0
mkdir -p "$out"
img="$out/$name.img"; log="$out/$name.capture.log"; tsv="$out/$name.chunks.tsv"
resume=${RESUME:-0}; live_from=${LIVE_FROM_SECTOR:-}
xfer_timeout=${XFER_TIMEOUT:-600}
if [ "$resume" -eq 0 ]; then
  [ -e "$img" ] && { echo "refusing: $img exists" >&2; exit 2; }
  : > "$img"; : > "$log"; : > "$tsv"
else
  [ "$(stat -c %s "$img")" -eq $((resume * chunk * 1048576)) ] || { echo "refusing: $img is not $resume chunks" >&2; exit 2; }
fi

sectors=$(adb shell cat /sys/block/mmcblk0/size | tr -d '\r')
total=$((sectors * 512))
mib=$(( (total + 1048575) / 1048576 ))
n=$(( (mib + chunk - 1) / chunk ))
{
  echo "UTC: $(date -u)"
  echo "Serial: $(adb get-serialno)"
  echo "Fingerprint: $(adb shell getprop ro.build.fingerprint | tr -d '\r')"
  echo "Source: $dev  sectors=$sectors bytes=$total chunk=${chunk}MiB chunks=$n"
} | tee -a "$log"

echo "resume=$resume live_from_sector=${live_from:-none}" | tee -a "$log"
for ((i = resume; i < n; i++)); do
  skip=$((i * chunk))
  tmp="$img.part"
  # adb exec-out can wedge mid-stream with the board's dd already gone
  # (2026-11-18, chunk 16 hung 3 h); bound every transfer and retry.
  for ((try = 1; ; try++)); do
    if timeout "$xfer_timeout" adb exec-out "dd if=$dev bs=1048576 skip=$skip count=$chunk 2>/dev/null" > "$tmp" &&
       board=$(timeout "$xfer_timeout" adb shell "dd if=$dev bs=1048576 skip=$skip count=$chunk 2>/dev/null | sha256sum") &&
       [ "$(stat -c %s "$tmp")" -gt 0 ]; then
      break
    fi
    echo "chunk $i transfer failed (try $try)" | tee -a "$log"
    [ "$try" -lt 3 ] || exit 1
    sleep 5
  done
  host=$(sha256sum < "$tmp" | cut -d' ' -f1)
  board=$(printf '%s' "$board" | cut -d' ' -f1 | tr -d '\r')
  bytes=$(stat -c %s "$tmp")
  status=ok
  if [ "$host" != "$board" ]; then
    end_sector=$(( (skip + chunk) * 2048 ))
    if [ -n "$live_from" ] && [ "$end_sector" -gt "$live_from" ]; then
      status=live
    else
      echo "chunk $i MISMATCH host=$host board=$board bytes=$bytes" | tee -a "$log"
      exit 1
    fi
  fi
  cat "$tmp" >> "$img"; rm -f "$tmp"
  printf '%d\t%d\t%d\t%s\t%s\n' "$i" "$skip" "$bytes" "$host" "$status" >> "$tsv"
  echo "chunk $i/$((n - 1)) $status bytes=$bytes $host" | tee -a "$log"
done

size=$(stat -c %s "$img")
[ "$size" -eq "$total" ] || { echo "size $size != $total" | tee -a "$log"; exit 1; }
sha256sum "$img" | tee "$img.sha256" | tee -a "$log"
chmod a-w "$img" "$img.sha256"
echo "DONE $(date -u)" | tee -a "$log"
