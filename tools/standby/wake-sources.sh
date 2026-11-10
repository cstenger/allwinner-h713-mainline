#!/bin/sh
# wake-sources.sh -- can the case button and the remote wake s2idle? RUNS ON
# THE TARGET, as root, DETACHED (WiFi suspends):
#
#   nohup sh wake-sources.sh [OUTDIR] >/dev/null 2>&1 &
#
# Two real s2idle sleeps. Before each, a prompt on the panel (tty1) says which
# key to press; a 60 s RTC alarm is the safety net. After each wake it logs
# how long it slept and which interrupt woke it (/sys/power/pm_wakeup_irq),
# then runs the systemd-sleep hooks (the hotspot) by hand, since rtcwake
# bypasses systemd. h713-keyd is stopped meanwhile: the waking press is a
# KEY_POWER too. docs/standby-plan.md, phase 3.
set -u
OUT=${1:-/root/wake-sources-$(date +%Y%m%d-%H%M%S)}
mkdir -p "$OUT"
LOG=$OUT/wake.log
log() { echo "$(cut -d' ' -f1 /proc/uptime) $*" >> "$LOG"; }
say() { printf '\033[2J\033[H\n\n\n    %s\n' "$@" > /dev/tty1; }
irqname() { awk -v n="$1:" '$1 == n { print $NF }' /proc/interrupts; }

echo N > /sys/module/printk/parameters/console_suspend
# The waking press is also a KEY_POWER; keep h713-keyd from toggling standby.
systemctl stop h713-keyd.service
trap 'systemctl start h713-keyd.service' EXIT
log "start $(uname -v)"
for key in "CASE BUTTON" "REMOTE POWER"; do
  say "ASLEEP: press the $key" "(it wakes by itself after 60 s)"
  sleep 2
  t0=$(cut -d' ' -f1 /proc/uptime)
  rtcwake -m freeze -s 60 >> "$LOG" 2>&1
  t1=$(cut -d' ' -f1 /proc/uptime)
  irq=$(cat /sys/power/pm_wakeup_irq 2>/dev/null)
  log "$key: slept $(awk -v a=$t0 -v b=$t1 'BEGIN{printf "%.1f", b-a}') s, woken by irq $irq ($(irqname "$irq"))"
  for h in /usr/lib/systemd/system-sleep/*; do [ -x "$h" ] && "$h" post s2idle; done
  say "AWAKE - wait for the next prompt"
  sleep 12
done
say "DONE - thank you"
log "DONE"
