#!/bin/sh
# Read-only check of the automatic HDMI startup path on the target. Prints
# evidence and exits nonzero on the first unmet production condition.
set -u
fail() { echo "FAIL: $*"; exit 1; }
P=/sys/module
echo "== boot $(cat /proc/sys/kernel/random/boot_id) $(uname -r) up $(cut -d' ' -f1 /proc/uptime)s"
H=/proc/device-tree/chosen/h713,hdmi-boot-v1
[ -f "$H" ] || fail 'no U-Boot handoff property'
handoff=$(od -An -tx1 -v "$H" | tr -d ' \n'); echo "handoff $handoff"
case "$handoff" in 48444d4900000000????????) ;; *) fail 'handoff not magic/0/pid';; esac
[ "${handoff#48444d4900000000}" != 00000000 ] || fail 'handoff pid zero'
for u in h713-hdmi-capture h713-hdmi-signal; do
  s=$(systemctl show -p ActiveState,Result,ConditionResult,ExecMainStatus --value $u | tr '\n' ' ')
  echo "$u: $s"
  [ "$(systemctl is-active $u)" = active ] || fail "$u not active"
done
grep -q '"phase": "ready"' /run/h713-hdmi-session/state.json || fail 'session state not ready'
r() { cat "$P/$1/parameters/$2" 2>/dev/null; }
for kv in h713_hdmi_receiver:clock_count:4 h713_hdmi_receiver:init_error:0 h713_hdmi_receiver:firmware_pin:Y \
          h713_hdmi_receiver:edid_ready:Y h713_hdmi_receiver:clients:2 h713_hdmi_audio:dsp_failed:N \
          h713_hdmi_audio:manage_dsp:Y h713_hdmi_audio:manage_tvfe:Y h713_hdmi_signal:ready:Y \
          h713_hdmi_signal:failed:N h713_hdmi_signal:restored:N; do
  m=${kv%%:*}; rest=${kv#*:}; k=${rest%%:*}; want=${rest#*:}
  got=$(r "$m" "$k"); echo "$m.$k=$got"
  [ "$got" = "$want" ] || fail "$m.$k is '$got', want '$want'"
done
[ -d $P/h713_ddc_pins ] || fail 'DDC pins not held'
for d in tvfe tvcap; do
  [ "$(cat /sys/devices/h713-hdmi-$d/power/runtime_status)" = active ] || fail "$d domain inactive"
done
for m in h713_scp_probe h713_hdmi_dsp_probe h713_hdmi_power h713_edid_clock h713_hdmi_tvfe_hold; do
  [ ! -d $P/$m ] || fail "diagnostic module $m loaded"
done
dmesg | grep -E 'DSP versions|patch verified' || fail 'no DSP version log'
dmesg | grep 'DSP versions' | head -1 | grep -q '0000/0000' || fail 'DSP did not start at 0/0'
dmesg | grep -q 'patch verified versions 1/1' || fail 'DSP patch not 1/1'
grep -q H713HDMI /proc/asound/cards || fail 'no ALSA card'
cat /proc/asound/H713HDMI/pcm0c/sub0/status
# No dependency on a bench bundle or host-provided proof.
ls -d /tmp/h713* /tmp/*hdmi* 2>/dev/null && echo 'note: /tmp artifacts exist (units use only /usr/lib/h713-hdmi)'
systemctl show -p ExecStart --value h713-hdmi-capture | grep -q -- '--boot-handoff' || fail 'service not using DT handoff'
echo "rtc gp6 latch unknown from Linux (U-Boot checked)"
journalctl -b -u h713-hdmi-capture -u h713-hdmi-signal --no-pager | tail -15
echo PASS
