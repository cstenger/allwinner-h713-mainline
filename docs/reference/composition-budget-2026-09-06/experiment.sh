#!/bin/sh
set -eu
OUT=/root/composition-budget-20260906
mkdir -p "$OUT"
COMP='0x050000f0 0x05000210 0x05000174 0x050001b4 0x05000224 0x05000274 0x05000278 0x050002b4 0x050002b8 0x05000444 0x05000544 0x05000804 0x0500080c 0x05000840 0x05000844 0x05000858 0x0500085c'
AFBD='0x05600010 0x05600020 0x05600024 0x05600030 0x05600040 0x05600044 0x05600048 0x0560004c 0x05600060 0x05600070 0x05600074 0x05600078 0x0560007c 0x05600084 0x05600088 0x0560008c 0x05600090 0x05600098'
mark() { echo "$*"; echo "composition-budget: $*" > /dev/kmsg; }
snap() {
  label=$1
  mark "$label"
  for r in $COMP; do printf '%s %s\n' "$r" "$(busybox devmem "$r" 32)"; done > "$OUT/$label.comp"
  for r in $AFBD 0x0306101c 0x02010030 0x051c006c; do printf '%s %s\n' "$r" "$(busybox devmem "$r" 32)"; done > "$OUT/$label.afbd"
  cat /sys/module/sunxi_decd/parameters/ring_writes_max /sys/module/sunxi_decd/parameters/ring_writes_done > "$OUT/$label.budget"
  python3 /root/elog-dump.py > "$OUT/$label.elog"
  cat "$OUT/$label.budget" "$OUT/$label.comp" "$OUT/$label.afbd"
  sync
}
case ${1:-} in
first)
  [ "$(cat /sys/module/sunxi_decd/parameters/ring_writes_max)" = 1 ]
  [ "$(cat /sys/module/sunxi_decd/parameters/ring_writes_done)" = 0 ]
  snap before
  mark 'submit corrected frame, budget 1'
  /root/decd-client.coord1080 show /root/decd-test-frame.nv12 2000 > "$OUT/first.client" 2>&1
  cat "$OUT/first.client"
  snap first-submit
  mark 'dtv get_fb after first submit'
  python3 /root/mips-shell.py --cmd 'dtv get_fb' > "$OUT/first.getfb" 2>&1
  cat "$OUT/first.getfb"
  sleep 2
  snap first-serviced
  ;;
more)
  snap before-more
  done_count=$(cat /sys/module/sunxi_decd/parameters/ring_writes_done)
  max_count=$((done_count + 4))
  mark "allow four additional writes: $done_count -> $max_count"
  sync
  echo "$max_count" > /sys/module/sunxi_decd/parameters/ring_writes_max
  /root/decd-client.coord1080 show /root/decd-test-frame.nv12 2000 > "$OUT/more.client" 2>&1
  cat "$OUT/more.client"
  snap more-submit
  python3 /root/mips-shell.py --cmd 'dtv get_fb' > "$OUT/more.getfb" 2>&1
  cat "$OUT/more.getfb"
  sleep 2
  snap more-serviced
  ;;
*) exit 2;;
esac
