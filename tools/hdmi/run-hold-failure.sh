#!/bin/sh
# H2 bench: force the realistic signal-stop failure (a capture consumer still
# recording when the signal owner stops) and shut down with HDMI holds
# retained. Run on the target from its staged directory, operator watching.
#   inject poweroff|reboot   preflight, start the busy recorder ordered to
#                            outlive the signal unit, then request the verb
#   consumer                 M2: a user-session consumer (pw-record through
#                            the user's PipeWire) still capturing when the
#                            signal owner stops; poweroff must reclaim it and
#                            tear down normally
#   verify                   on the next cold boot: prove the injected boot
#                            failed closed (stop refused, nothing parked), or
#                            for consumer, reclaimed and parked
# The record of each injection lives in /var/tmp so it survives the cycle.
set -u
D=$(cd "$(dirname "$0")" && pwd)
U=h713-hdmi-signal.service
BUSY=h713-h2-busy-pcm.service
CONSUMER=h713-m2-consumer.service
NODE=alsa_input._sys_devices_h713-hdmi-audio-dma_sound_card1.stereo-fallback
NO_RECLAIM=/run/h713-hdmi-signal/no-reclaim
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
  # Without this the wrapper would reclaim the recorder at shutdown and the
  # stop would succeed; H2 needs it to fail. Runtime-only: gone next boot.
  : > $NO_RECLAIM
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
  printf '{"boot_id": "%s", "verb": "%s", "mode": "h2", "uptime": "%s"}\n' "$boot" "$verb" "$(cut -d' ' -f1 /proc/uptime)" > "$R/injected.json"
  sync
  echo "h713-hold-failure: injecting $verb with capture open" > /dev/kmsg
  echo "injected; requesting $verb (boot $boot). Watch the board."
  systemctl $verb --no-block
  ;;
consumer)
  sh "$D/check-startup.sh" > "$R/preflight.log" 2>&1 || { cat "$R/preflight.log"; fail 'production startup check failed'; }
  echo 'production startup check passed'
  [ ! -e $NO_RECLAIM ] || fail 'bench no-reclaim knob is set; cold cycle first'
  [ "$(cat $PCM)" = closed ] || fail 'capture PCM already open'
  # pw-record talks to the user's PipeWire, which opens the PCM. Before= the
  # signal unit keeps the stream alive while the signal owner stops.
  systemd-run --unit=$CONSUMER --collect --uid=media -E XDG_RUNTIME_DIR=/run/user/1000 -p Before=$U \
    pw-record --target $NODE /dev/null || fail 'consumer did not start'
  sleep 3
  [ "$(systemctl is-active $CONSUMER)" = active ] || fail 'consumer exited'
  state=$(grep '^state:' $PCM); echo "pcm $state"
  [ "$state" = 'state: RUNNING' ] || { systemctl stop $CONSUMER; fail 'PCM not running; consumer stopped, nothing injected'; }
  dev=/dev/snd/pcmC$(readlink /proc/asound/H713HDMI | sed 's/card//')D0c
  holder=$(for p in /proc/[0-9]*; do ls -l $p/fd 2>/dev/null | grep -q " $dev\$" && cat $p/comm; done | sort -u | tr '\n' ' ')
  echo "pcm holders: $holder"
  case " $holder" in *' pipewire '*) ;; *) systemctl stop $CONSUMER; fail 'PCM not held by the user PipeWire; consumer stopped';; esac
  boot=$(cat /proc/sys/kernel/random/boot_id)
  printf '{"boot_id": "%s", "verb": "poweroff", "mode": "consumer", "uptime": "%s"}\n' "$boot" "$(cut -d' ' -f1 /proc/uptime)" > "$R/injected.json"
  sync
  echo "h713-hold-failure: consumer still capturing at poweroff" > /dev/kmsg
  echo "injected; requesting poweroff (boot $boot)."
  systemctl poweroff --no-block
  ;;
verify)
  [ -f "$R/injected.json" ] || fail 'no injection recorded'
  cat "$R/injected.json"
  boot=$(sed 's/.*"boot_id": "\([^"]*\)".*/\1/' "$R/injected.json" | tr -d -)
  verb=$(sed 's/.*"verb": "\([^"]*\)".*/\1/' "$R/injected.json")
  [ "$boot" != "$(tr -d - < /proc/sys/kernel/random/boot_id)" ] || fail 'still on the injected boot'
  journalctl -b "$boot" -o short-monotonic --no-pager > "$R/injected-boot.journal" 2>&1 || fail 'injected boot not in the journal'
  j=$R/injected-boot.journal
  grep -E 'h713-hold-failure|h713-hdmi-signal|h713-ddc-pins|h713-hdmi-capture|h713-hdmi-receiver|python3\[|h2-busy|m2-consumer|Power|reboot|Shutting down' "$j" | sed -n '/h713-hold-failure/,$p' | tee "$R/injected-boot.extract"
  case "$(cat "$R/injected.json")" in
  *'"mode": "consumer"'*)
    grep -q 'shutdown: closing HDMI capture consumers' "$j" || fail 'consumers were not reclaimed'
    ! grep -q 'capture is open; signal retained' "$j" || fail 'signal stop still refused'
    grep -q 'h713-hdmi-signal: peripheral readback, SRAM and vectors restored' "$j" || fail 'signal not restored'
    grep -q 'h713-ddc-pins: DDC pins returned to' "$j" || fail 'DDC pins not returned'
    grep -q 'terminal MIPS parked' "$j" || fail 'MIPS not parked'
    verb='consumer reclaim then poweroff';;
  *)
    grep -q 'capture is open; signal retained' "$j" || fail 'signal stop did not refuse on the open PCM'
    grep -q 'signal owner/helper must restore and stop before backend shutdown' "$j" || fail 'backend did not refuse parking'
    ! grep -q 'terminal MIPS parked' "$j" || fail 'MIPS was parked; the failure was not injected'
    ! grep -qE 'h713-hdmi-signal: .*restored; SCP stopped' "$j" || fail 'signal restored; the failure was not injected'
    verb="$verb with retained holds";;
  esac
  grep -q 'Shutting down' "$j" || fail 'shutdown never reached the final stage'
  sh "$D/check-startup.sh" > "$R/next-boot-check.log" 2>&1 || { cat "$R/next-boot-check.log"; fail 'this boot is not a clean cold boot'; }
  echo "PASS verify: $verb as designed; this cold boot is clean"
  mv "$R/injected.json" "$R/verified-$boot.json"
  ;;
*) echo "usage: $0 inject poweroff|reboot | consumer | verify" >&2; exit 2;;
esac
