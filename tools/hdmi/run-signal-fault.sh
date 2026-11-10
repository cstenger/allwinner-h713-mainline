#!/bin/sh
# M4 bench: prove that a post-release signal init failure left in a proven
# state is undone (SCP reset, SRAM/vectors restored, every hold released) by
# the real wrapper, on hardware. Runs on the target from its staged directory
# on a clean cold boot. The staged h713-hdmi-signal.ko is a BENCH BUILD
# (-DH713_SIGNAL_FAULT_INJECTION): fault=1 corrupts the EDID header after
# ARM verified it (payload: data_failed, receiver untouched), fault=2 makes
# the payload's first EDID verify read the wrong word (mismatch, then its own
# full restore), fault=3 refuses just before SCP release (M1: the wrapper must
# drop DDC), fault=4 gives up the ready poll at once (late ready: a full
# cooperative stop). All start through a runtime-only drop-in (gone next boot).
# The first failed check stops the script; it never rmmods or undoes holds.
set -u
D=$(cd "$(dirname "$0")" && pwd)
U=h713-hdmi-signal.service
P=/sys/module
DROP=/run/systemd/system/$U.d/50-signal-fault.conf
LATCH=/run/h713-hdmi-signal/attempted
OUT=/var/tmp/h713-signal-fault/$(cat /proc/sys/kernel/random/boot_id)
mkdir -p "$OUT"
LOG=$OUT/run.log
say() { echo "$*" | tee -a "$LOG"; }
fail() { say "FAIL: $*"; dmesg > "$OUT/dmesg-at-failure.log"; exit 1; }
r() { cat "$P/$1/parameters/$2" 2>/dev/null; }
want() { got=$(r "$1" "$2"); say "$1.$2=$got"; [ "$got" = "$3" ] || fail "$1.$2 is '$got', want '$3'"; }
since() { dmesg | sed -n "/$1/,\$p"; }
nothing_held() {
  [ ! -d $P/h713_hdmi_signal ] || fail 'signal module still loaded'
  [ ! -d $P/h713_ddc_pins ] || fail 'DDC helper still loaded'
  [ ! -e /run/h713-hdmi-signal/owned ] || fail 'ownership record still present'
  want h713_hdmi_receiver clients 1
  reg=$(/root/mmio-rw r 7022004 | awk '{print $2}'); say "PL mux register $reg"
  [ "$reg" = 0xFFFFFF3F ] || fail "DDC pins not back to io_disabled ($reg)"
}
# inject FAULT KERNEL-LINE UNIT-LINE [after-release]
inject() {
  fault=$1 kernel=$2 unit=$3 released=${4:-}
  mark="h713-signal-fault: inject $fault $(date +%s)"
  echo "$mark" > /dev/kmsg
  cat > "$DROP" <<EOF
# Runtime-only M4 bench (run-signal-fault.sh); gone after reboot.
[Unit]
RequiresMountsFor=$D
[Service]
ExecStart=
ExecStart=/usr/bin/python3 $D/h713-hdmi-signal.py start --bundle $D --signal-arg fault=$fault
ExecStop=
ExecStop=/usr/bin/python3 $D/h713-hdmi-signal.py stop --bundle $D
EOF
  systemctl daemon-reload
  say "starting the bench owner with fault=$fault (expect: $unit)"
  ! systemctl start $U 2>>"$LOG" || fail "fault=$fault did not fail the start"
  since "$mark" > "$OUT/fault$fault-dmesg.log"
  journalctl -u $U -b --no-pager | tail -4 > "$OUT/fault$fault-unit.log"
  grep 'h713-hdmi-signal' "$OUT/fault$fault-dmesg.log" | tee -a "$LOG"
  grep -q "BENCH BUILD, fault injection $fault" "$OUT/fault$fault-dmesg.log" || fail 'bench build did not inject'
  if [ -n "$released" ]; then
    grep -q 'h713-hdmi-signal: setup failed' "$OUT/fault$fault-dmesg.log" || fail 'init did not fail after release'
  else
    ! grep -q 'h713-hdmi-signal: setup failed' "$OUT/fault$fault-dmesg.log" || fail 'SCP was released'
  fi
  grep -q "$kernel" "$OUT/fault$fault-dmesg.log" || fail "kernel did not log: $kernel"
  grep -q "$unit" "$OUT/fault$fault-unit.log" || fail "wrapper did not report: $unit"
  ! grep -qE 'WARNING:|BUG:|Oops' "$OUT/fault$fault-dmesg.log" || fail 'kernel warning'
  nothing_held
  [ -e $LATCH ] || fail 'per-boot latch missing after the failure'
  say "PASS fault=$fault: $unit; nothing held"
}

[ "$(id -u)" = 0 ] || fail 'run as root'
[ ! -e "$DROP" ] || fail 'already run on this boot; cold cycle before repeating'
sh "$D/check-startup.sh" > "$OUT/check-startup.log" 2>&1 || { cat "$OUT/check-startup.log"; fail 'production startup check failed'; }
say 'production startup check passed'
(cd "$D" && sha256sum -c SHA256SUMS) >> "$LOG" 2>&1 || fail 'staged bundle checksum mismatch'
modinfo -p "$D/h713-hdmi-signal.ko" | grep -q '^fault:' || fail 'staged signal module is not a bench build'
[ "$(cat /proc/asound/H713HDMI/pcm0c/sub0/status)" = closed ] || fail 'capture PCM is open'
say 'stopping the installed signal owner'
systemctl stop $U
[ "$(systemctl show -p ActiveState --value $U) $(systemctl show -p Result --value $U)" = 'inactive success' ] || fail 'installed signal stop failed; holds retained'
nothing_held
mkdir -p "${DROP%/*}"
again() { rm "$LATCH"; systemctl reset-failed $U; } # bench only: another launch this boot
inject 1 'init failure undone from proven state 3;' 'undone from proven state 3, nothing retained' released
again
inject 2 'init failure undone from proven state 2;' 'undone from proven state 2, nothing retained' released
again
inject 3 'BENCH BUILD, fault injection 3' 'refused before SCP release; nothing retained'
again
inject 4 'init failure undone from proven state 1;' 'undone from proven state 1, nothing retained' released
grep -q 'h713-hdmi-signal: stop readback' "$OUT/fault4-dmesg.log" || fail 'late ready did not take the cooperative stop'
say 'PASS: faults 1-4 undone or refused with nothing held; the backend must park at the next shutdown'
