#!/bin/sh
# Bench lifetime cycle of a candidate h713-hdmi-signal module, run on the
# target from its staged directory on a cold boot the installed units brought
# up. Two phases, each self-checking:
#   swap  stop the installed owner (the validated path), then start the
#         candidate through a runtime-only drop-in that vanishes next boot
#   stop  stop the candidate; prove completion, peripheral readback == the
#         saved originals, SRAM/vector restore, client and DDC release
# The first failed check stops the script. It never rmmods, retries, or
# undoes a hold: a failure after SCP release needs a physical cold cycle.
set -u
D=$(cd "$(dirname "$0")" && pwd)
U=h713-hdmi-signal.service
P=/sys/module
DROP=/run/systemd/system/$U.d/50-signal-lifetime.conf
OWNED=/run/h713-hdmi-signal/owned
PCM=/proc/asound/H713HDMI/pcm0c/sub0/status
# Pre-trial values from 300+ bounded-probe runs (HPD, DDC b00/b04/b08).
KNOWN='1014=00000007 1b00=00a0a0a0 1b04=07000000 1b08=00606060'
PHASE=${1:-}
OUT=/var/tmp/h713-signal-lifetime/$(cat /proc/sys/kernel/random/boot_id)
mkdir -p "$OUT"
LOG=$OUT/$PHASE.log

say() { echo "$*" | tee -a "$LOG"; }
fail() { say "FAIL: $*"; dmesg | sed -n "/$MARK/,\$p" > "$OUT/$PHASE-dmesg.log" 2>/dev/null; exit 1; }
r() { cat "$P/$1/parameters/$2" 2>/dev/null; }
want() { got=$(r "$1" "$2"); say "$1.$2=$got"; [ "$got" = "$3" ] || fail "$1.$2 is '$got', want '$3'"; }
# GNU build-id of a loaded module: the last 20 bytes of its exported note.
bid() { od -An -tx1 -v "$P/$1/notes/.note.gnu.build-id" | tr -d ' \n' | tail -c 40; }
since() { dmesg | sed -n "/$MARK/,\$p"; }
mark() { MARK="h713-signal-lifetime: $PHASE begin $(date +%s)"; echo "$MARK" > /dev/kmsg; }
pcm_closed() { s=$(cat "$PCM"); say "pcm: $s"; [ "$s" = closed ] || fail 'capture PCM is open; close every consumer first'; }
unit_stopped() {
  s="$(systemctl show -p ActiveState --value $U) $(systemctl show -p Result --value $U)"; say "$U: $s"
  [ "$s" = 'inactive success' ] || fail "$1"
  [ ! -d $P/h713_hdmi_signal ] || fail 'signal module still loaded'
  [ ! -d $P/h713_ddc_pins ] || fail 'DDC helper still loaded'
  [ ! -e $OWNED ] || fail 'ownership record still present'
  want h713_hdmi_receiver clients 1
}
MARK='^$'

[ "$(id -u)" = 0 ] || fail 'run as root'
case $PHASE in
swap)
  [ ! -e "$DROP" ] || fail 'candidate already swapped in on this boot; cold cycle before repeating'
  sh "$D/check-startup.sh" > "$OUT/check-startup.log" 2>&1 || { cat "$OUT/check-startup.log"; fail 'production startup check failed; not a clean cold boot'; }
  say 'production startup check passed'
  (cd "$D" && sha256sum -c SHA256SUMS) >> "$LOG" 2>&1 || fail 'staged bundle checksum mismatch'
  for m in h713-hdmi-signal.ko h713-ddc-pins.ko; do
    set -- $(modinfo -F vermagic "$D/$m"); [ "$1" = "$(uname -r)" ] || fail "$m vermagic $1"
  done
  installed=$(bid h713_hdmi_signal); candidate=$(cat "$D/candidate.build-id")
  say "build-id installed=$installed candidate=$candidate"
  [ ${#installed} = 40 ] && [ ${#candidate} = 40 ] || fail 'build-id unreadable'
  [ "$installed" != "$candidate" ] || fail 'staged module is the installed one'
  pcm_closed
  mark
  say 'stopping the installed signal owner'
  systemctl stop $U
  unit_stopped 'installed signal stop failed; holds retained, do not retry, cold cycle required'
  since | grep -q 'h713-hdmi-signal: peripheral, SRAM and vectors restored' || fail 'installed module did not log restoration'
  mkdir -p "${DROP%/*}"
  cat > "$DROP" <<EOF
# Runtime-only bench candidate (run-signal-lifetime.sh); gone after reboot.
[Unit]
RequiresMountsFor=$D
[Service]
ExecStart=
ExecStart=/usr/bin/python3 $D/h713-hdmi-signal.py start --bundle $D
ExecStop=
ExecStop=/usr/bin/python3 $D/h713-hdmi-signal.py stop --bundle $D
EOF
  systemctl daemon-reload
  say 'starting the candidate signal owner'
  systemctl start $U || fail 'candidate start failed; holds retained, do not retry, cold cycle required'
  [ "$(systemctl is-active $U)" = active ] || fail 'candidate unit not active'
  want h713_hdmi_signal ready Y; want h713_hdmi_signal failed N; want h713_hdmi_signal restored N
  want h713_hdmi_receiver clients 2
  [ -d $P/h713_ddc_pins ] || fail 'DDC pins not held'
  loaded=$(bid h713_hdmi_signal); say "loaded build-id=$loaded"
  [ "$loaded" = "$candidate" ] || fail 'loaded module is not the candidate'
  since | grep 'h713-hdmi-signal: ready' | tee -a "$LOG"
  poison=$(since | grep 'h713-hdmi-signal: ready readback' | tail -1 | grep -o '=ffffffff' | wc -l)
  [ "$poison" = 8 ] || fail "readback area not intact at ready ($poison/8 poison words)"
  original=$(since | grep 'h713-hdmi-signal: ready original' | tail -1 | sed 's/.*ready original //')
  case $original in "$KNOWN "*) say 'originals match the known-good probe values';;
    *) say "NOTE: originals differ from known-good ($KNOWN); report this";; esac
  since > "$OUT/swap-dmesg.log"
  say 'PASS swap: candidate owns EDID/HPD; run the optional capture test, then the stop phase'
  ;;
stop)
  [ -e "$DROP" ] || fail 'swap phase has not run on this boot'
  [ "$(systemctl is-active $U)" = active ] || fail 'candidate unit not active'
  want h713_hdmi_signal ready Y; want h713_hdmi_signal failed N
  pcm_closed
  mark
  say 'stopping the candidate signal owner'
  systemctl stop $U
  since > "$OUT/stop-dmesg.log"
  grep 'h713-hdmi-signal: stop\|h713-hdmi-signal: peripheral\|h713-ddc-pins' "$OUT/stop-dmesg.log" | tee -a "$LOG"
  unit_stopped 'candidate stop failed; holds retained, do not retry, cold cycle required'
  status=$(grep 'h713-hdmi-signal: stop marker=' "$OUT/stop-dmesg.log" | tail -1)
  case $status in *'marker=48444d49 ready=48444d49 exception=0 error=0 done=48444d49') ;;
    *) fail "unexpected payload status: $status";; esac
  original=$(grep 'h713-hdmi-signal: stop original' "$OUT/stop-dmesg.log" | tail -1 | sed 's/.*stop original //')
  readback=$(grep 'h713-hdmi-signal: stop readback' "$OUT/stop-dmesg.log" | tail -1 | sed 's/.*stop readback //')
  say "original $original"; say "readback $readback"
  [ -n "$original" ] && [ "$original" = "$readback" ] || fail 'readback differs from originals'
  grep -q 'h713-hdmi-signal: peripheral readback, SRAM and vectors restored' "$OUT/stop-dmesg.log" || fail 'no restoration line'
  grep -q 'h713-ddc-pins: DDC pins returned to ' "$OUT/stop-dmesg.log" || fail 'DDC idle restore not confirmed'
  ! grep -qE 'WARNING:|BUG:|Oops|input-state restore failed' "$OUT/stop-dmesg.log" || fail 'kernel warning during stop'
  say 'PASS stop: readback equals originals; SCP stopped; client and DDC released'
  ;;
*) echo "usage: $0 swap|stop" >&2; exit 2;;
esac
