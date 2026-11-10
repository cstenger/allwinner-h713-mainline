#!/bin/sh
# suspend-ladder.sh -- exercise s2idle one stage at a time. RUNS ON THE TARGET,
# as root, DETACHED (WiFi suspends with the devices, so ssh drops):
#
#   nohup sh suspend-ladder.sh [OUTDIR] [STAGES] >/dev/null 2>&1 &
#
# STAGES (default "freezer devices") are /sys/power/pm_test levels, needing
# CONFIG_PM_DEBUG: "freezer" freezes and thaws every task, "devices" also
# runs every driver's suspend and resume; each comes back on its own after
# 5 s with no wake source. "rtc" is a REAL s2idle, woken by the RTC alarm
# after 20 s. Every stage is followed by the same health check, and the
# ladder stops at the first stage that fails. docs/standby-plan.md, phase 3.
set -u
OUT=${1:-/root/suspend-ladder-$(date +%Y%m%d-%H%M%S)}
STAGES=${2:-"freezer devices"}
mkdir -p "$OUT"
LOG=$OUT/ladder.log
log() { echo "$(cat /proc/uptime | cut -d' ' -f1) $*" >> "$LOG"; }

irq() { awk -v n="$1" '$NF == n { s = 0; for (i = 2; i <= 5; i++) s += $i; print s }' /proc/interrupts; }

# Health: the display still scans out (vblank IRQs tick), the VE decodes a
# clip in hardware (its IRQ count rises), WiFi is up, and the kernel printed
# no new errors. Prints "HEALTH ok" or "HEALTH FAIL <what>".
health() {
  bad=
  v0=$(irq h713-afbd); sleep 1; v1=$(irq h713-afbd)
  [ $((v1 - v0)) -ge 30 ] || bad="$bad vblank($((v1 - v0))/s)"
  e0=$(irq 1c0e000.video-codec)
  LIBVA_DRIVER_NAME=v4l2_request timeout 30 ffmpeg -nostdin -loglevel error \
    -hwaccel vaapi -hwaccel_output_format vaapi -i /root/h264test.mp4 \
    -vf hwdownload,format=nv12 -frames:v 30 -f null - >> "$OUT/ffmpeg.log" 2>&1 ||
    bad="$bad ffmpeg"
  e1=$(irq 1c0e000.video-codec)
  [ $((e1 - e0)) -ge 20 ] || bad="$bad ve($((e1 - e0)))"
  ip -br addr show wlan0 | grep -q UP || bad="$bad wlan0"
  n=$(dmesg --level=err,crit,alert,emerg | wc -l)
  [ "$n" -le "${ERR0:-0}" ] || bad="$bad dmesg-errors(+$((n - ${ERR0:-0})))"
  ERR0=$n
  log "HEALTH ${bad:-ok} (vblank $((v1 - v0))/s, ve +$((e1 - e0)))"
  [ -z "$bad" ]
}

echo N > /sys/module/printk/parameters/console_suspend   # keep serial alive
for f in pm_print_times pm_debug_messages; do
  [ -w /sys/power/$f ] && echo 1 > /sys/power/$f   # CONFIG_PM_SLEEP_DEBUG
done
log "start: $(uname -v); stages: $STAGES"
dmesg > "$OUT/dmesg-before.txt"
ERR0=$(dmesg --level=err,crit,alert,emerg | wc -l)
health || { log "baseline unhealthy, not suspending"; exit 1; }

for st in $STAGES; do
  m0=$(dmesg | wc -l)
  if [ "$st" = rtc ]; then
    echo none > /sys/power/pm_test
    log "stage rtc: rtcwake -m freeze -s 20"
    rtcwake -m freeze -s 20 >> "$LOG" 2>&1; rc=$?
  else
    echo "$st" > /sys/power/pm_test
    log "stage $st: freeze"
    echo freeze > /sys/power/state 2>> "$LOG"; rc=$?
    echo none > /sys/power/pm_test
  fi
  dmesg | tail -n +$((m0 + 1)) > "$OUT/dmesg-$st.txt"
  # Raw /sys/power/state writes and rtcwake bypass systemd, so run its sleep
  # hooks by hand (the hotspot one restarts the AP that suspend stopped).
  for h in /usr/lib/systemd/system-sleep/*; do [ -x "$h" ] && "$h" post s2idle; done
  log "stage $st returned $rc; $(grep -c . "$OUT/dmesg-$st.txt") new kernel lines"
  sleep 8                          # hotspot restart + re-association
  if ! health || [ $rc -ne 0 ]; then log "STOP after $st"; exit 1; fi
done
cat /sys/power/suspend_stats/* > "$OUT/suspend_stats.txt" 2>/dev/null
log "DONE all stages passed"
