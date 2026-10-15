#!/bin/sh
# H2 bench: force the realistic signal-stop failure (a capture consumer still
# recording when the signal owner stops) and shut down with HDMI holds
# retained. Run on the target from its staged directory, operator watching.
#   inject poweroff|reboot   preflight, start the busy recorder ordered to
#                            outlive the signal unit, then request the verb
#   verify                   on the next cold boot: prove the injected boot
#                            failed closed (stop refused, nothing parked)
# The record of each injection lives in /var/tmp so it survives the cycle.
set -u
D=$(cd "$(dirname "$0")" && pwd)
U=h713-hdmi-signal.service
BUSY=h713-h2-busy-pcm.service
PCM=/proc/asound/H713HDMI/pcm0c/sub0/status
GUARD=/usr/lib/systemd/system-shutdown/h713-hdmi-hold-guard
R=/var/tmp/h713-hold-failure
mkdir -p "$R"
fail() { echo "FAIL: $*"; exit 1; }
[ "$(id -u)" = 0 ] || fail 'run as root'
case ${1:-} in
inject)
  verb=${2:-}
  case $verb in poweroff|reboot) ;; *) fail 'inject needs poweroff or reboot';; esac
  sh "$D/check-startup.sh" > "$R/preflight.log" 2>&1 || { cat "$R/preflight.log"; fail 'production startup check failed'; }
  echo 'production startup check passed'
  [ -x "$GUARD" ] || fail 'hold guard not installed'
  cmp -s "$D/h713-hdmi-hold-guard" "$GUARD" || fail 'installed hold guard differs from the staged one'
  [ -x /tmp/arecord ] || fail 'stage the recorder at /tmp/arecord first'
  [ "$(cat $PCM)" = closed ] || fail 'capture PCM already open'
  # Before= the signal unit: at shutdown this stops after it, so the signal
  # stop finds the PCM open. Nothing orders it relative to the backend.
  systemd-run --unit=$BUSY --collect -p Before=$U -p RequiresMountsFor=/tmp \
    /tmp/arecord -q -D hw:H713HDMI,0 -f S16_LE -r 48000 -c 2 -t raw /dev/null || fail 'busy recorder did not start'
  sleep 2
  [ "$(systemctl is-active $BUSY)" = active ] || fail 'busy recorder exited'
  state=$(grep '^state:' $PCM); echo "pcm $state"
  [ "$state" = 'state: RUNNING' ] || { systemctl stop $BUSY; fail 'PCM not running; recorder stopped, nothing injected'; }
  systemctl show -p Before --value $BUSY | grep -qw $U || { systemctl stop $BUSY; fail 'ordering not applied; recorder stopped'; }
  boot=$(cat /proc/sys/kernel/random/boot_id)
  printf '{"boot_id": "%s", "verb": "%s", "uptime": "%s"}\n' "$boot" "$verb" "$(cut -d' ' -f1 /proc/uptime)" > "$R/injected.json"
  sync
  echo "h713-hold-failure: injecting $verb with capture open" > /dev/kmsg
  echo "injected; requesting $verb (boot $boot). Watch the board."
  systemctl $verb --no-block
  ;;
verify)
  [ -f "$R/injected.json" ] || fail 'no injection recorded'
  cat "$R/injected.json"
  boot=$(sed 's/.*"boot_id": "\([^"]*\)".*/\1/' "$R/injected.json" | tr -d -)
  verb=$(sed 's/.*"verb": "\([^"]*\)".*/\1/' "$R/injected.json")
  [ "$boot" != "$(tr -d - < /proc/sys/kernel/random/boot_id)" ] || fail 'still on the injected boot'
  journalctl -b "$boot" -o short-monotonic --no-pager > "$R/injected-boot.journal" 2>&1 || fail 'injected boot not in the journal'
  j=$R/injected-boot.journal
  grep -E 'h713-hold-failure|h713-hdmi-signal|h713-ddc-pins|h713-hdmi-capture|h713-hdmi-receiver|python3\[|h2-busy|Power|reboot|Shutting down' "$j" | sed -n '/h713-hold-failure/,$p' | tee "$R/injected-boot.extract"
  grep -q 'capture is open; signal retained' "$j" || fail 'signal stop did not refuse on the open PCM'
  grep -q 'signal owner/helper must restore and stop before backend shutdown' "$j" || fail 'backend did not refuse parking'
  ! grep -q 'terminal MIPS parked' "$j" || fail 'MIPS was parked; the failure was not injected'
  ! grep -qE 'h713-hdmi-signal: .*restored; SCP stopped' "$j" || fail 'signal restored; the failure was not injected'
  grep -q 'Shutting down' "$j" || fail 'shutdown never reached the final stage'
  sh "$D/check-startup.sh" > "$R/next-boot-check.log" 2>&1 || { cat "$R/next-boot-check.log"; fail 'this boot is not a clean cold boot'; }
  echo "PASS verify: $verb with retained holds failed closed; this cold boot is clean"
  mv "$R/injected.json" "$R/verified-$boot.json"
  ;;
*) echo "usage: $0 inject poweroff|reboot | verify" >&2; exit 2;;
esac
