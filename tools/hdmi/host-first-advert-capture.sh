#!/usr/bin/env bash
# Host-side capture for the HDMI first-advert failure (NVIDIA source PC).
#
# Run with sudo in a terminal AFTER logging in and BEFORE powering the board:
#
#   sudo bash tools/hdmi/host-first-advert-capture.sh [OUTDIR]
#
# It turns on NVIDIA modesetting (nvidia_modeset debug=1) and kernel DRM
# (drm.debug=0x6: driver + KMS) debug output, records the full journal, DRM
# uevents and the HDMI connector status with host monotonic timestamps, and
# restores both debug knobs on exit (Ctrl-C, q, timeout or error). Nothing
# persistent is changed. Keys while running:
#   Enter  write a MARK line (press it the moment you power the board on)
#   q      stop
#
# Limits: stops by itself after MAX_SECONDS (default 900) or when the journal
# capture exceeds MAX_MB (default 200).
set -u

SYS=${SYS:-/sys}
MAX_SECONDS=${MAX_SECONDS:-900}
MAX_MB=${MAX_MB:-200}
NVKMS=$SYS/module/nvidia_modeset/parameters/debug
DRMDBG=$SYS/module/drm/parameters/debug
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
OUT=${1:-$ROOT/local/recovery/host-first-advert/$(date +%Y%m%dT%H%M%S)}

now() { cut -d' ' -f1 /proc/uptime; }
log() { printf '%s %s\n' "$(now)" "$*" | tee -a "$OUT/events.log"; }

if [ "${ALLOW_NONROOT:-0}" != 1 ] && [ "$(id -u)" != 0 ]; then
	echo "run with sudo (needs to write $NVKMS and $DRMDBG)" >&2
	exit 2
fi
for f in "$NVKMS" "$DRMDBG"; do
	[ -w "$f" ] || { echo "missing or not writable: $f" >&2; exit 2; }
done
mkdir -p "$OUT" || exit 2

OLD_NVKMS=$(cat "$NVKMS")
OLD_DRM=$(cat "$DRMDBG")
PIDS=()
restored=0
restore() {
	[ "$restored" = 1 ] && return
	restored=1
	for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null; done
	wait 2>/dev/null
	echo "$OLD_NVKMS" > "$NVKMS"
	echo "$OLD_DRM" > "$DRMDBG"
	log "RESTORED nvidia_modeset.debug=$(cat "$NVKMS") drm.debug=$(cat "$DRMDBG")"
	if [ -n "${SUDO_USER:-}" ]; then chown -R "$SUDO_USER": "$OUT" 2>/dev/null; fi
	echo "capture in $OUT"
}
trap restore EXIT
trap 'exit 130' INT TERM HUP

{
	echo "host_boot $(cat /proc/sys/kernel/random/boot_id)"
	echo "uname $(uname -r)"
	head -1 /proc/driver/nvidia/version 2>/dev/null
	echo "old nvidia_modeset.debug=$OLD_NVKMS drm.debug=$OLD_DRM"
	for c in "$SYS"/class/drm/card*-*; do
		[ -e "$c/status" ] && echo "connector $(basename "$c") $(cat "$c/status")"
	done
} > "$OUT/context.txt"

# Start the recorders before turning debug on, so the switch itself is logged.
journalctl -f -n 0 -o short-monotonic > "$OUT/journal.log" 2>&1 &
PIDS+=($!)
udevadm monitor --kernel --udev --property --subsystem-match=drm > "$OUT/uevents.log" 2>&1 &
PIDS+=($!)
(
	prev=""
	while :; do
		s=""
		for c in "$SYS"/class/drm/card*-HDMI-*; do
			[ -e "$c/status" ] && s="$s $(basename "$c")=$(cat "$c/status")"
		done
		if [ "$s" != "$prev" ]; then printf '%s%s\n' "$(now)" "$s" >> "$OUT/connector.log"; prev=$s; fi
		sleep 0.1
	done
) &
PIDS+=($!)
sleep 0.5

echo 1 > "$NVKMS"
echo 0x6 > "$DRMDBG"
log "DEBUG ON nvidia_modeset.debug=$(cat "$NVKMS") drm.debug=$(cat "$DRMDBG")"
echo "Recording. Power the board on now and press Enter at that moment; q to stop."

end=$(( $(date +%s) + MAX_SECONDS ))
while [ "$(date +%s)" -lt "$end" ]; do
	if read -r -t 1 key; then
		[ "$key" = q ] && { log "STOP (q)"; break; }
		log "MARK${key:+ $key}"
	fi
	mb=$(( $(stat -c %s "$OUT/journal.log" 2>/dev/null || echo 0) / 1048576 ))
	if [ "$mb" -ge "$MAX_MB" ]; then log "STOP (journal ${mb} MB)"; break; fi
done
[ "$(date +%s)" -ge "$end" ] && log "STOP (timeout ${MAX_SECONDS} s)"
exit 0
