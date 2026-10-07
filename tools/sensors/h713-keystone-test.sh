#!/bin/sh
# Unattended logic test for h713-keystone against a fake sensor and a fake
# mirror. RUNS ON THE TARGET (mawk is the awk that ships), touches no hardware.
#
#   tools/sensors/h713-keystone-test.sh [path/to/h713-keystone]
#
# The fake sensor's mount-matrix is the identity, so raw values are the
# projector frame directly: 1000 = 1 g, Y up, lens along -Z.
set -u
KS=${1:-/usr/local/bin/h713-keystone}
T=$(mktemp -d)
trap 'kill $DPID $WPID 2>/dev/null; rm -rf "$T"' EXIT
WPID=
mkdir -p "$T/dev" "$T/run" "$T/bin"
echo 0.00980665 > "$T/dev/in_accel_x_scale"
echo 100 > "$T/dev/sampling_frequency"
echo "1, 0, 0; 0, 1, 0; 0, 0, 1" > "$T/dev/mount_matrix"
echo 0 > "$T/mirror"
cat > "$T/bin/h713-mirror" <<EOF
#!/bin/sh
[ -f "$T/refuse" ] && exit 1
[ \$# = 0 ] && { cat "$T/mirror"; exit 0; }
echo "\$1" > "$T/mirror"
EOF
chmod +x "$T/bin/h713-mirror"
export PATH="$T/bin:$PATH" H713_KEYSTONE_DEV="$T/dev" H713_KEYSTONE_RUN="$T/run" \
	H713_KEYSTONE_ETC="$T/etc.conf" H713_MIRROR_ATTR="$T/mirror" \
	H713_KEYSTONE_SAMPLE_DELAY=0.02

# Atomic per file, as sysfs is: an echo can be read half-written (empty = 0 g).
# W names the writer's temp files, so the background mover cannot collide.
put() { echo "$2" > "$T/dev/.$1$W"; mv "$T/dev/.$1$W" "$T/dev/in_accel_$1_raw"; }
pose() { put x "$1"; put y "$2"; put z "$3"; }
W=fg
st() { sed -n "s/^$1=//p" "$T/run/state" 2>/dev/null; }
pass=0; fail=0
check() { # NAME ACTUAL EXPECTED
	if [ "$2" = "$3" ]; then pass=$((pass + 1)); echo "  ok   $1: $2"
	else fail=$((fail + 1)); echo "  FAIL $1: got '$2', want '$3'"; fi
}
# 8 still windows publish the converged estimate: ~8 x 10 x 25 ms, plus margin.
settle() { sleep 4; }

pose 0 1000 0
"$KS" daemon > "$T/log" 2>&1 & DPID=$!
settle
echo "level, upright, ceiling off"
check settled "$(st settled)" 1
check pitch "$(st pitch_deg)" 0.0
check inverted "$(st inverted)" 0
check keystone "$(st keystone_deg)" 0.0

echo "turned over with ceiling off: the mirror is left alone"
pose 0 -1000 0; settle
check inverted "$(st inverted)" 1
check mirror "$(cat "$T/mirror")" 0

echo "ceiling auto: front -> ceiling"
"$KS" ceiling auto >/dev/null; settle
check mirror "$(cat "$T/mirror")" 3

echo "set rear while upside down: becomes rear-ceiling"
echo 1 > "$T/mirror"; settle
check mirror "$(cat "$T/mirror")" 2

echo "lens straight up: held upside down, mirror unchanged"
pose 0 0 -1000; settle
check surface "$(st surface)" ceiling
check inverted "$(st inverted)" 1
check mirror "$(cat "$T/mirror")" 2
check pitch "$(st pitch_deg)" -90.0

echo "upright, lens 10 deg up: rear, keystone follows"
pose 0 985 -174; settle
check inverted "$(st inverted)" 0
check mirror "$(cat "$T/mirror")" 1
check pitch "$(st pitch_deg)" 10.0
check keystone "$(st keystone_deg)" 10.0

echo "upside down, lens 10 deg toward its own top"
pose 0 -985 174; settle
check pitch "$(st pitch_deg)" 10.0
check mirror "$(cat "$T/mirror")" 2
pose 0 985 -174; settle

echo "lens 80 deg up, upright: the ceiling, 10 deg short of square"
pose 0 174 -985; settle
check surface-80 "$(st surface)" ceiling
check keystone-80 "$(st keystone_deg)" -10.0
pose 0 985 -174; settle

echo "right side raised 20 deg"
pose 342 940 0; settle
check roll "$(st roll_deg)" 20.0
check pitch "$(st pitch_deg)" 0.0
check level "$(st level_deg)" 20.0
"$KS" off >/dev/null; settle
check level-off "$(st level_deg)" 0.0
"$KS" manual 3 >/dev/null; settle
check level-manual "$(st level_deg)" 0.0
"$KS" auto >/dev/null
pose 0 985 -174; settle

echo "moving: correction held, settled 0"
( W=bg; while :; do pose 0 985 -174; pose 300 700 -500; done ) & WPID=$!
settle
check settled "$(st settled)" 0
check keystone "$(st keystone_deg)" 10.0
kill $WPID; WPID=; pose 0 985 -174; settle
check settled "$(st settled)" 1

echo "half-degree hysteresis: 0.3 deg of noise does not redraw"
pose 0 984 -179; settle
check pitch "$(st pitch_deg)" 10.0

echo "off, manual"
"$KS" off >/dev/null; settle
check keystone "$(st keystone_deg)" 0.0
"$KS" manual -4.5 >/dev/null; settle
check keystone "$(st keystone_deg)" -4.5
"$KS" auto --persist >/dev/null; settle
check keystone "$(st keystone_deg)" 10.0
check persisted "$(grep -c '^keystone=auto' "$T/etc.conf")" 1
check runtime-conf-gone "$(test -e "$T/run/conf" && echo present || echo gone)" gone
check ceiling-kept "$(grep -c '^ceiling=auto' "$T/etc.conf")" 1

echo "a refused flip is retried, not lost"
touch "$T/refuse"; pose 0 -1000 0; settle
check mirror "$(cat "$T/mirror")" 1
check logged "$(grep -c refused "$T/log")" 1
rm "$T/refuse"; sleep 10
check mirror "$(cat "$T/mirror")" 2

echo "calibration: offsets of a real unit, then 0 at the bottom and 90 at the top"
"$KS" ceiling off >/dev/null; echo 0 > "$T/mirror"
pose 15 1040 17; settle
check uncalibrated-level "$(st pitch_deg)" -0.9
check cal-level "$("$KS" calibrate level >/dev/null && echo ok)" ok
settle
check level "$(st pitch_deg)" 0.0
check level-roll "$(st roll_deg)" 0.0
pose 15 12 -985; settle
check uncalibrated-up "$(st pitch_deg)" 89.3
check cal-up "$("$KS" calibrate up >/dev/null && echo ok)" ok
settle
check up "$(st pitch_deg)" 90.0
pose 15 1040 17; settle
check level-again "$(st pitch_deg)" 0.0
check saved "$(grep -c '^bias_' "$T/etc.conf")" 3
pose 15 866 -483; settle
check refuses-tilted "$("$KS" calibrate level 2>/dev/null && echo ok || echo refused)" refused
check refuses-not-up "$("$KS" calibrate up 2>/dev/null && echo ok || echo refused)" refused

echo "trim: adjust, set, clamp, reset, refuse a bare number"
tr() { "$KS" trim "$@" 2>/dev/null | sed -n 's/^h713-keystone: trim [a-z]* \([-0-9.]*\) deg$/\1/p'; }
check trim-plus "$(tr yaw +0.5)" 0.5
check trim-set "$(tr yaw =3)" 3.0
check trim-minus "$(tr yaw -4)" -1.0
check trim-clamp "$(tr pitch +50)" 40.0
check trim-roll "$(tr roll -.5)" -0.5
check trim-bare "$("$KS" trim yaw 3 >/dev/null 2>&1 && echo took || echo refused)" refused
check trim-axis "$("$KS" trim tilt +1 >/dev/null 2>&1 && echo took || echo refused)" refused
check trim-show "$("$KS" trim)" "trim (deg): pitch 40.0  roll -0.5  yaw -1.0"
"$KS" trim reset --persist >/dev/null
check trim-reset "$("$KS" trim)" "trim (deg): pitch 0  roll 0  yaw 0"
check trim-persisted "$(grep -c '^trim_yaw=0$' "$T/etc.conf")" 1

echo "daemon log:"; sed 's/^/  /' "$T/log"
echo "$pass passed, $fail failed"
[ $fail = 0 ]
