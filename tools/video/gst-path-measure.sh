#!/bin/sh
# Measure one GStreamer decode pipeline into glimagesink. RUNS ON THE TARGET.
# WP2 of docs/gpu-fallback-plan.md: the GStreamer half of "stock applications
# on our drivers". The mpv half is gpu-path-measure.sh.
#
#   sh gst-path-measure.sh CLIP DECODER [DUR]
#   sh gst-path-measure.sh /tmp/1b-h264-1280x720.mp4 v4l2slh264dec 60
#   sh gst-path-measure.sh /tmp/05-av1-1080.mp4 vaav1dec
#
# There is no X or Wayland here, so glimagesink draws through GBM on the display
# device (GST_GL_WINDOW=gbm). The DECODER element is followed by nothing but the
# sink, so whether frames reach GL zero-copy is decided by caps negotiation;
# zerocopy= reports whether the negotiated caps carry memory:DMABuf or
# memory:VAMemory (import) rather than system memory (a CPU copy).
#
# fps/drops come from fpsdisplaysink's own counters; dec_irq= proves the
# hardware decoded (a software fallback would show zero).
set -u
CLIP=$1 DEC=$2 DUR=${3:-60}
LOG=/tmp/gst-path.log
export GST_GL_WINDOW=gbm GST_GL_PLATFORM=egl GST_GL_GBM_DRM_DEVICE=/dev/dri/card0
export LIBVA_DRIVER_NAME=v4l2_request
# GStreamer registers va decoders only for allow-listed drivers (Intel, Mesa);
# without this none exist for v4l2_request. An environment variable, not a patch.
export GST_VA_ALL_DRIVERS=1

irqsum() {
	awk -v p="$1" 'NR == 1 { ncpu = NF; next }
	               $0 ~ p { for (i = 2; i <= ncpu + 1; i++) s += $i }
	               END { print s + 0 }' /proc/interrupts
}
cpustat() { awk '/^cpu /{ print $2+$3+$4+$6+$7+$8, $5 }' /proc/stat; }

case "$CLIP" in
	*.webm|*.mkv) DEMUX=matroskademux ;;
	*) DEMUX=qtdemux ;;
esac
case "$DEC" in
	*h264*) PARSE=h264parse ;;
	*h265*) PARSE=h265parse ;;
	*vp9*) PARSE=vp9parse ;;
	*av1*) PARSE=av1parse ;;
	*) PARSE=identity ;;
esac

D0=$(irqsum 'video-codec|1c0d000'); G0=$(irqsum 'panfrost-job')
set -- $(cpustat); CB0=$1 CI0=$2
T0=$(date +%s)
gst-launch-1.0 -e -v filesrc location="$CLIP" ! $DEMUX ! $PARSE ! "$DEC" ! \
	fpsdisplaysink name=fps text-overlay=false video-sink=glimagesink sync=true \
	> "$LOG" 2>&1 &
PID=$!
i=0
while kill -0 $PID 2>/dev/null && [ $i -lt "$DUR" ]; do sleep 1; i=$((i + 1)); done
kill -INT $PID 2>/dev/null; sleep 2; kill $PID 2>/dev/null; wait $PID 2>/dev/null
SECS=$(($(date +%s) - T0))
DEC_IRQ=$(( $(irqsum 'video-codec|1c0d000') - D0 ))
GIRQ=$(( $(irqsum 'panfrost-job') - G0 ))
set -- $(cpustat); CB=$(( $1 - CB0 )) CI=$(( $2 - CI0 ))

LAST=$(grep -a 'last-message = rendered' "$LOG" | tail -1 | sed 's/.*last-message = //')
CAPS=$(grep -a "$DEC.*src: caps = " "$LOG" | tail -1 | sed 's/.*caps = //')
case "$CAPS" in
	*memory:DMABuf*) ZC=dmabuf ;;
	*memory:VAMemory*) ZC=vamemory ;;
	"") ZC=unknown ;;
	*) ZC=no-sysmem ;;
esac
ERR=$(grep -aiE 'error|warning|failed|not-negotiated' "$LOG" | sort -u | head -3 | tr '\n' '|')

echo "GST label=$(basename "$CLIP") dec=$DEC secs=$SECS"
echo "GST caps: $CAPS"
echo "GST fps: ${LAST:-none}"
[ -n "$ERR" ] && echo "GST msgs: $ERR"
echo "GST SUMMARY $(basename "$CLIP") $DEC zerocopy=$ZC dec_irq=$DEC_IRQ gpu_irq_s=$((GIRQ / (SECS > 0 ? SECS : 1))) cpu_all=$(awk -v b=$CB -v i=$CI 'BEGIN { printf "%.0f", 100 * b / (b + i) }')% [${LAST:-no fps report}]"
