#!/usr/bin/env bash
# WP5 Phase 2 gate, headless half: kernel 0166's hardware mirror, every
# configuration checked without a camera. RUNS ON THE HOST.
#
#   mirror-gate.sh            run every case, print PASS/FAIL per case
#
# For each case it puts a card up (letterbox-card: --primary for the console
# route, COMMIT=/ROTATION= for placement and the plane property), sets the
# installation mode through sysfs, and checks:
#   1. the mirror registers hold what MIRROR in the driver says
#      (panel 0x0a0[0], program window 0x0c0, source 0 / OSD CTRL[3:2],
#      comp+040[3]);
#   2. debugfs h713_geometry: every window-layer register equals the
#      driver's model ("0 of N registers differ");
#   3. the same registers equal letterbox-recipe.py's (an INDEPENDENT model,
#      self-tested against the stock captures) for the same client request;
#   4. the panel histogram (lvds+0x310/380/3b0/3fc) equals the same card's
#      unmirrored histogram: no row lost, no padding, nothing garbled.
# The orientation itself is the operator's (mirror-gate.sh prints a viewing
# plan); registers and histogram cannot tell left from right.
set -uo pipefail
BOARD=${BOARD:-192.168.4.1}
SSH="ssh -n -o ConnectTimeout=20 -o BatchMode=yes root@$BOARD"
SCP="scp -q -o ConnectTimeout=20 -o BatchMode=yes"
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
R=/root/tools/letterbox
OUT=${OUT:-$REPO/local/h713-lab/mirror-gate-$(date +%Y%m%d-%H%M)}
mkdir -p "$OUT"

$SCP "$HERE/letterbox-card.c" "$HERE/letterbox-baseline.py" "root@$BOARD:$R/" || exit 1
$SSH "cd $R && cc -O2 -Wall -o letterbox-card letterbox-card.c \$(pkg-config --cflags --libs libdrm)" || exit 1
$SSH 'dmesg | grep -E "hardware mirror|video plane:"' | tee "$OUT/dmesg.txt"
grep -q "hardware mirror: available" "$OUT/dmesg.txt" || { echo "FAIL: the mirror is not available"; exit 1; }

# the native baseline the recipe tool needs: video card up, mode 0
$SSH 'echo 0 > /sys/bus/platform/drivers/sun50i-h713-afbd/*/mirror_mode'
$SSH "pkill -x letterbox-card; sleep 1; setsid env ARMED=yes $R/letterbox-card 60 >/tmp/letterbox-card.log 2>&1 </dev/null & sleep 2; python3 $R/letterbox-baseline.py; pkill -x letterbox-card; sleep 1" > "$OUT/native.txt"
python3 "$HERE/letterbox-recipe.py" --live "$OUT/native.txt" --self-test >/dev/null ||
	{ echo "FAIL: the recipe model does not reproduce the native state on this kernel"; exit 1; }

# name  route(primary|video)  mode  rotation  commit(region@x,y or -)  recipe(WxH@X,Y pitch or -)
CASES="
p0     primary 0 -   -           -
p1     primary 1 -   -           -
p2     primary 2 -   -           -
p3     primary 3 -   -           -
prx    primary 0 x   -           -
pry    primary 0 y   -           -
pr180  primary 0 180 -           -
p1rx   primary 1 x   -           -
v0     video   0 -   -           1280x720@0,0:1280
v1     video   1 -   -           1280x720@0,0:1280
v2     video   2 -   -           1280x720@0,0:1280
v3     video   3 -   -           1280x720@0,0:1280
vc0    video   0 -   c@0,0       852x480@0,0:864
vc1    video   1 -   c@0,0       852x480@0,0:864
vc2    video   2 -   c@0,0       852x480@0,0:864
vc3    video   3 -   c@0,0       852x480@0,0:864
vcrx   video   0 x   c@0,0       852x480@0,0:864
vc1rx  video   1 x   c@0,0       852x480@0,0:864
vab2   video   2 -   ab@0,0      1280x536@0,0:1280
vab0   video   0 -   ab@0,0      1280x536@0,0:1280
"
fail=0
echo "$CASES" | while read -r name route mode rot commit rec; do
	[ -n "$name" ] || continue
	prim=; [ "$route" = primary ] && prim=--primary
	env="ARMED=yes"; [ "$rot" != - ] && env="$env ROTATION=$rot"
	[ "$commit" != - ] && env="$env COMMIT=$commit"
	$SSH "pkill -x letterbox-card; sleep 1
	      echo $mode > /sys/bus/platform/drivers/sun50i-h713-afbd/*/mirror_mode
	      setsid env $env $R/letterbox-card $prim 60 >/tmp/letterbox-card.log 2>&1 </dev/null &
	      sleep 2.5
	      echo '== log'; cat /tmp/letterbox-card.log
	      echo '== geometry'; cat /sys/kernel/debug/dri/5600000.display/h713_geometry
	      echo '== hist'; for a in 0x051c0310 0x051c0380 0x051c03b0 0x051c03fc; do busybox devmem \$a; done
	      pkill -x letterbox-card; sleep 1
	      echo 0 > /sys/bus/platform/drivers/sun50i-h713-afbd/*/mirror_mode" > "$OUT/$name.txt" 2>&1
	echo "$name $route $mode $rot $commit $rec"
done > "$OUT/cases.txt"
$SSH 'dmesg | grep -iE "iommu|fault|h713|afbd" | tail -20' > "$OUT/dmesg-after.txt"
python3 "$HERE/mirror-gate-check.py" "$OUT"
