#!/usr/bin/env bash
# WP5 Phase 2 gate, the operator's half: one "ready", about 2.5 minutes,
# filmed handheld. RUNS ON THE HOST; the sequence runs detached on the board.
# Everything goes through kernel 0166 (sysfs mirror_mode, plane rotation),
# no register pokes. The console coming back at the end = stop recording.
#
#   lead 30 s   console card upright (letterbox-card --primary)
#   pm1 pm2 pm3 console card in modes 1, 2, 3   (expect L/R, T/B, 180)
#   pr180       console card, mode 0, plane ROTATE_180   (expect 180)
#   vc0..vc3    852x480 video card at client (0,0) in modes 0..3
#               (expect top-left; top-right L/R; bottom-left T/B; bottom-right 180)
#   pb0 pb2     P010 colour bars, mode 0 then mode 2 (expect T/B; look at the
#               boundary between the top and bottom halves for a colour fringe)
# 8 s per step, 3 s of mode 0 between console steps.
set -uo pipefail
BOARD=${BOARD:-192.168.4.1}
SSH="ssh -n -o ConnectTimeout=20 -o BatchMode=yes root@$BOARD"
R=/root/tools/letterbox
OUT=${OUT:-$(cd "$(dirname "$0")/../.." && pwd)/local/h713-lab/mirror-look-$(date +%Y%m%d-%H%M)}
mkdir -p "$OUT"
ssh -o ConnectTimeout=20 -o BatchMode=yes root@$BOARD "cat > /tmp/mirror-look.sh" <<'EOF2'
M=/sys/bus/platform/drivers/sun50i-h713-afbd/5600000.display/mirror_mode
R=/root/tools/letterbox
t(){ echo "$(date +%s.%N | cut -c1-14) $*"; }
card(){ pkill -x letterbox-card; sleep 0.7; setsid env ARMED=yes "$@" >/tmp/letterbox-card.log 2>&1 </dev/null & sleep 1.5; }
echo 0 > $M
card $R/letterbox-card --primary 600
t lead; sleep 30
for m in 1 2 3; do echo $m > $M; t pm$m; sleep 8; echo 0 > $M; sleep 3; done
card ROTATION=180 $R/letterbox-card --primary 600; t pr180; sleep 8
card COMMIT=c@0,0 $R/letterbox-card 600
for m in 0 1 2 3; do echo $m > $M; t vc$m; sleep 8; done
echo 0 > $M; pkill -x letterbox-card; sleep 0.7
cd /root/kmstest; setsid env ARMED=yes FMT=p010 FILL=msb ./kms-p010-plane-test 30 >/tmp/p010.log 2>&1 </dev/null & sleep 2
t pb0; sleep 8; echo 2 > $M; t pb2; sleep 8; echo 0 > $M
kill $(pidof kms-p010-plane-test) 2>/dev/null; pkill -x letterbox-card; sleep 1
t end; echo warnings $(dmesg | grep -c WARNING)
EOF2
$SSH "test -s /tmp/mirror-look.sh && sh -n /tmp/mirror-look.sh" || { echo "the sequence did not reach the board"; exit 1; }
echo "== first change in 30 s, about 2.5 min in all; the console returns at the end =="
$SSH "setsid sh /tmp/mirror-look.sh > /tmp/mirror-look.log 2>&1 < /dev/null & echo \$! > /tmp/mirror-look.pid" 
sleep 160
while $SSH 'kill -0 $(cat /tmp/mirror-look.pid) 2>/dev/null'; do sleep 3; done
$SSH 'cat /tmp/mirror-look.log' | tee "$OUT/look.log"
