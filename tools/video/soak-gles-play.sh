#!/bin/sh
# The other GPU arm: panfrost rendering, but through gles-play instead of mesa.
#
#     MINUTES=20 sh soak-gles-play.sh
#
# WHY. The corruption needs panfrost doing real work -- mpv --vo=drm ran 2406 s
# clean with gpu_delta=0, while mpv --vo=gpu crashes in 40-90 s. But gles-play
# also drives panfrost and the one run on record (run D, 480 s) was clean, which
# is why "GPU + carveout is safe" was believed for a while. The carveout half of
# that was refuted directly (patch 0054: same mpv, scanout from a reserved pool,
# still crashed at ~31 s), so what is left to separate is:
#
#   * the mesa/GBM path specifically -- importing a card1 dumb buffer into
#     panfrost -- being what corrupts, or
#   * simply the AMOUNT of GPU work, with gles-play's 480 s being low stress
#     rather than a safe configuration.
#
# If gles-play crashes here, run D was underpowered and the answer is the second
# one. If it survives 20 minutes at a real frame rate, the mesa import pairing
# is implicated and run D stands.
#
# NOTE gles-play is not a pure renderer swap: it decodes on the VE (cedrus) and
# renders into the 0x6c100000 carveout, committing by writing AFBD registers
# through /dev/mem rather than through KMS. So ve= RISES here, unlike every
# other arm in this investigation. That is expected, not a fault -- but it does
# mean this arm cannot also be used to exonerate cedrus.
set -u

CLIP=${CLIP:-/var/tmp/long.h264}
MINUTES=${MINUTES:-20}
PERIOD=${PERIOD:-30}
LOG=${LOG:-/var/tmp/soak-gles-play.child.log}
BIN=${BIN:-/root/video-test/gles-play}

irqsum() {
	awk -v p="$1" 'NR == 1 { ncpu = NF; next }
	               $0 ~ p { for (i = 2; i <= ncpu + 1; i++) s += $i }
	               END { print s + 0 }' /proc/interrupts
}

[ -x "$BIN" ]  || { echo "SOAK FATAL: no gles-play at $BIN"; exit 1; }
[ -r "$CLIP" ] || { echo "SOAK FATAL: no Annex-B stream at $CLIP"; exit 1; }

echo "SOAK start kernel=$(uname -r) bin=$BIN clip=$CLIP minutes=$MINUTES"
echo "SOAK cmdline: $(cat /proc/cmdline)"
echo 1 > /proc/sys/debug/exception-trace 2>/dev/null

VE0=$(irqsum 'video-codec')
GPU0=$(irqsum 'panfrost')
AFBD0=$(irqsum 'h713-afbd')
PREVGPU=$GPU0

: > "$LOG"
T0=$(date +%s)
END=$((T0 + MINUTES * 60))
RUNS=0

# gles-play plays a file and exits, so the loop is the soak. Each pass is one
# process lifetime, which also exercises EGL/GBM setup and teardown repeatedly
# -- closer to mpv's behaviour than a single long-lived context would be.
(
	while [ "$(date +%s)" -lt "$END" ]; do
		EGL_PLATFORM=surfaceless "$BIN" "$CLIP" >> "$LOG" 2>&1 </dev/null
		echo "--- pass exit=$? ---" >> "$LOG"
	done
) &
LOOP=$!

while [ "$(date +%s)" -lt "$END" ]; do
	sleep "$PERIOD"
	t=$(($(date +%s) - T0))
	kill -0 "$LOOP" 2>/dev/null || { echo "SOAK LOOP-DIED by t=${t}s"; break; }
	ve=$(irqsum 'video-codec')
	gpu=$(irqsum 'panfrost')
	afbd=$(irqsum 'h713-afbd')
	RUNS=$(grep -c '^--- pass exit=' "$LOG" 2>/dev/null || echo 0)
	echo "SOAK t=${t}s ve_delta=$((ve - VE0)) gpu=${gpu} gpu_rate=$(((gpu - PREVGPU) / PERIOD))/s afbd_delta=$((afbd - AFBD0)) passes=${RUNS}"
	PREVGPU=$gpu
done

kill "$LOOP" 2>/dev/null
pkill -x gles-play 2>/dev/null
sleep 2
ve=$(irqsum 'video-codec')
gpu=$(irqsum 'panfrost')
afbd=$(irqsum 'h713-afbd')
echo "SOAK DONE t=$(($(date +%s) - T0))s passes=${RUNS} ve_delta=$((ve - VE0)) gpu_delta=$((gpu - GPU0)) afbd_delta=$((afbd - AFBD0))"
tr '\r' '\n' < "$LOG" | grep -av '^[[:space:]]*$' | tail -3 | sed 's/^/SOAK   last: /'
