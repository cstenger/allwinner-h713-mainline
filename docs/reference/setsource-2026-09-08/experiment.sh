#!/bin/sh
set -eu
OUT=/root/setsource-20260908
mkdir -p "$OUT"
COMP='0x050000f0 0x05000210 0x05000174 0x050001b4 0x05000224 0x05000274 0x05000278 0x050002b4 0x050002b8 0x05000444 0x05000544 0x05000804 0x0500080c 0x05000840 0x05000844 0x05000858 0x0500085c'
AFBD='0x05600010 0x05600020 0x05600024 0x05600030 0x05600040 0x05600044 0x05600048 0x0560004c 0x05600060 0x05600070 0x05600074 0x05600078 0x0560007c 0x05600084 0x05600088 0x0560008c 0x05600090 0x05600098'
mark() { echo "$*"; echo "setsource-test: $*" > /dev/kmsg; }
snap() {
  label=$1
  mark "$label"
  for r in $COMP; do printf '%s %s\n' "$r" "$(busybox devmem "$r" 32)"; done > "$OUT/$label.comp"
  for r in $AFBD 0x0306101c 0x02010030 0x051c006c; do printf '%s %s\n' "$r" "$(busybox devmem "$r" 32)"; done > "$OUT/$label.afbd"
  cat /sys/module/sunxi_decd/parameters/ring_writes_max /sys/module/sunxi_decd/parameters/ring_writes_done > "$OUT/$label.budget"
  python3 /root/elog-dump.py > "$OUT/$label.elog"
  cat "$OUT/$label.budget" "$OUT/$label.comp" "$OUT/$label.afbd"
  obj=$(busybox devmem 0x4b27266c 32)
  obj=$(( (obj & 0x1fffffff) + 0x40000000 ))
  [ "$obj" -ge $((0x4b100000)) ] && [ "$obj" -lt $((0x4c000000)) ]
  det=$(busybox devmem $((obj + 0x5a8)) 32)
  det=$(( (det & 0x1fffffff) + 0x40000000 ))
  [ "$det" -ge $((0x4b100000)) ] && [ "$det" -lt $((0x4c000000)) ]
  {
    printf 'object=0x%x detector=0x%x\n' "$obj" "$det"
    for off in 0 0x59c 0x5a0 0x5a4 0x5a8; do printf 'obj+0x%x %s\n' "$off" "$(busybox devmem $((obj+off)) 32)"; done
    for off in 0 0xb0 0xb4 0xb8 0xbc 0x140 0x144 0x148 0x14c; do printf 'det+0x%x %s\n' "$off" "$(busybox devmem $((det+off)) 32)"; done
  } > "$OUT/$label.state"
  cat "$OUT/$label.state"
  sync
}
[ "$(cat /sys/module/sunxi_decd/parameters/ring_writes_done)" = 0 ]
mark 'stage corrected frame budget=1'
/root/decd-client.coord1080 show /root/decd-test-frame.nv12 2000 > "$OUT/client.txt" 2>&1
python3 /root/mips-shell.py --cmd 'dtv get_fb' > "$OUT/getfb.txt"
sleep 2
snap before
[ "$(cat /sys/module/sunxi_decd/parameters/ring_writes_done)" = 1 ]
[ "$(cat /sys/module/sunxi_decd/parameters/ring_writes_max)" = 1 ]
mark 'single SetSource(1), ring frozen at 1/1'
/root/cpu-comm-probe THal_Vp_SetSource_1_000 1 > "$OUT/rpc.txt" 2>&1
cat "$OUT/rpc.txt"
snap immediate
sleep 2
snap delayed
dmesg > "$OUT/dmesg.txt"
sync
