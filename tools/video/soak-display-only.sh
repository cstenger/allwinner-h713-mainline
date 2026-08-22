#!/bin/sh
# The control this investigation never ran with adequate exposure: the display
# path hot for an hour with the video engine never opened.
#
#     MINUTES=60 sh soak-display-only.sh            # GPU renderer (panfrost)
#     MINUTES=60 VO=drm sh soak-display-only.sh     # no GPU at all
#
# VO=drm is the arm that takes panfrost out of the picture: mpv renders frames
# with the CPU into dumb buffers and page-flips them, so the KMS/CMA scanout is
# exercised exactly as before while the GPU never runs. That matters because
# panfrost was live in every run on record, clean and crashing alike, and it
# maps the scanout dma-buf into its OWN page tables -- a mapping the sun50i
# IOMMU cannot see and cannot fault on. If a stale one of those is the stray
# writer, this arm is clean and the default arm is not.
#
# WHY. Every long run that crashed had cedrus decoding in it -- but so did
# nearly every long run, so that correlation is far weaker than it looked, and
# the one display-only run on record lasted 48 seconds against a bug whose crash
# latency ranges 113-848 s. This is the other arm: same kernel, same clip, same
# KMS/GBM scanout out of CMA, mpv doing *software* decode. If it crashes,
# cedrus is largely exonerated and the display path becomes the suspect.
#
# /proc/interrupts is both the guard and the exposure meter, which is why the
# heartbeat is built on it rather than on parsing mpv:
#
#   ve=  must not move.   A flat count is positive proof that no frame ever
#        reached the VE -- stronger than "we did not ask it to", because the
#        driver is built in on this kernel and cannot be removed.
#   gpu= rises on the default arm and must stay FLAT on VO=drm, where it is the
#        same kind of positive proof ve= is: panfrost is loaded and could fire,
#        so a flat count means the GPU genuinely never ran.
#   afbd= must keep rising on BOTH arms. It counts scanout commits, so it is the
#        exposure meter that survives changing the renderer -- gpu= cannot be
#        that on an arm where the GPU is deliberately absent. If mpv dies into a
#        still frame the run looks calm and means nothing, and a soak that
#        silently stopped exercising the thing under test is exactly how you get
#        a false "survived".
#   mmu= is the IOMMU's own interrupt, and it is the honest fault meter. The
#        driver's fault print is ratelimited (patch 0051), deliberately, so
#        counting "Page fault for" lines in dmesg understates a storm by
#        whatever the ratelimiter dropped. This counter does not. It is only
#        meaningful on a kernel that translates the master under test -- on a
#        stock kernel it sits at zero because nothing faults.
#
# Requires the panel to be up: `h713_disp auto 0x34 logo` at the U-Boot prompt
# before boot, or there is no KMS device at all.
set -u

CLIP=${CLIP:-/var/tmp/long.mp4}
MINUTES=${MINUTES:-60}
PERIOD=${PERIOD:-30}
MPVLOG=${MPVLOG:-/var/tmp/soak-display-only.mpv.log}
VO=${VO:-gpu}

# Sum the per-CPU columns of every /proc/interrupts line matching a pattern.
# The column count comes from the header row rather than from "looks like a
# number": a GIC line is `32: 1234 0 0 0  GICv3  55 Level  1c0e000.video-codec`,
# and that hwirq 55 is a bare integer that would otherwise be summed in.
irqsum() {
	awk -v p="$1" 'NR == 1 { ncpu = NF; next }
	               $0 ~ p { for (i = 2; i <= ncpu + 1; i++) s += $i }
	               END { print s + 0 }' /proc/interrupts
}

# Card numbers swap between the module and built-in kernels, so ask the driver
# rather than hardcoding a minor.
CARD=${CARD:-}
if [ -z "$CARD" ]; then
	for c in /sys/class/drm/card[0-9]; do
		[ -e "$c/device/uevent" ] || continue
		if grep -q '^DRIVER=sun50i-h713-afbd' "$c/device/uevent"; then
			CARD=/dev/dri/$(basename "$c")
		fi
	done
fi
if [ -z "$CARD" ]; then
	echo "SOAK FATAL: no sun50i-h713-afbd DRM node."
	echo "SOAK        the panel was not brought up in U-Boot (h713_disp auto 0x34 logo)."
	exit 1
fi
[ -r "$CLIP" ] || { echo "SOAK FATAL: no clip at $CLIP"; exit 1; }

echo "SOAK start kernel=$(uname -r) card=$CARD clip=$CLIP minutes=$MINUTES vo=$VO"
echo "SOAK cmdline: $(cat /proc/cmdline)"
grep -E 'video-codec|panfrost|h713-afbd|decd|iommu' /proc/interrupts | sed 's/^/SOAK irq0 /'
# Which masters are actually translated. "No fault" is only evidence if the
# device under test was attached in the first place.
for d in /sys/kernel/iommu_groups/*/devices/*; do
	[ -e "$d" ] && echo "SOAK iommu-attach group $(basename "$(dirname "$(dirname "$d")")") $(basename "$d")"
done

VE0=$(irqsum 'video-codec')
GPU0=$(irqsum 'panfrost')
MMU0=$(irqsum 'iommu')
AFBD0=$(irqsum 'h713-afbd')
MIG0=$(awk '/^pgmigrate_success/ { print $2 }' /proc/vmstat)
# panfrost-mmu on its own. It is inside the gpu= sum, which is right for
# "did the GPU run at all", but wrong for "is the GPU touching addresses it
# has no mapping for" -- and that second question is the one that matters
# now that panfrost is the remaining suspect. Some panfrost MMU faults are
# normal (growable heap), so read the RATE, not the presence.
PMMU0=$(irqsum 'panfrost-mmu')
PREVGPU=$GPU0
PREVAFBD=$AFBD0

# The first run of this control died here and told us almost nothing: mpv
# vanished at ~250 s and the script stopped, so an hour's exposure became four
# minutes. Worse, `dmesg` was silent and that reads as exoneration -- but
# exception-trace defaults to 0 on this rootfs, so the kernel would not have
# printed a SIGSEGV even if one happened. Turn it on and say so in the log,
# because "no fault reported" is only evidence when faults would be reported.
echo 1 > /proc/sys/debug/exception-trace 2>/dev/null
echo "SOAK exception-trace=$(cat /proc/sys/debug/exception-trace 2>/dev/null)"

start_mpv() {
	# --gpu-context is meaningful only to vo=gpu; vo=drm takes --drm-device
	# directly and renders with the CPU, never opening a render node.
	if [ "$VO" = gpu ]; then
		set -- --vo=gpu --gpu-context=drm --drm-device="$CARD"
	else
		set -- --vo="$VO" --drm-device="$CARD"
	fi
	mpv --hwdec=no "$@" \
	    --loop-file=inf --no-audio --input-terminal=no \
	    "$CLIP" >> "$MPVLOG" 2>&1 < /dev/null &
	MPID=$!
}

# 139 = 128 + SIGSEGV. mpv prints `Exiting... (reason)` on every ordinary
# termination including errors, so a status with no such line is a signal.
signame() {
	case "$1" in
	139) echo "SIGSEGV" ;;
	135) echo "SIGBUS" ;;
	134) echo "SIGABRT" ;;
	137) echo "SIGKILL" ;;
	136) echo "SIGFPE" ;;
	0)   echo "clean-exit" ;;
	*)   echo "status-$1" ;;
	esac
}

: > "$MPVLOG"
start_mpv

T0=$(date +%s)
END=$((T0 + MINUTES * 60))
DEATHS=0

# mpv dying must not end the run. The point of this control is an hour of
# *display* exposure; restarting keeps that accumulating, and each death is
# recorded with its signal, which turns one anecdote into a rate.
while [ "$(date +%s)" -lt "$END" ]; do
	sleep "$PERIOD"
	t=$(($(date +%s) - T0))
	if ! kill -0 "$MPID" 2>/dev/null; then
		wait "$MPID"
		rc=$?
		DEATHS=$((DEATHS + 1))
		echo "SOAK MPV-DIED #${DEATHS} by t=${t}s rc=${rc} $(signame $rc)"
		tr '\r' '\n' < "$MPVLOG" | grep -av '^[[:space:]]*$' | tail -1 | sed 's/^/SOAK   last: /'
		start_mpv
	fi
	ve=$(irqsum 'video-codec')
	gpu=$(irqsum 'panfrost')
	mmu=$(irqsum 'iommu')
	afbd=$(irqsum 'h713-afbd')
	cma=$(awk '/CmaFree/ { print $2 }' /proc/meminfo)
	# Page migration. NOTE: the hypothesis this was added for is DEAD -- it
	# supposed that CMA pages could be migrated out from under a live GPU
	# mapping, but cma_alloc() takes the pages out of the buddy allocator, so
	# an allocated CMA buffer is not a migration candidate. Kept as a cheap
	# background counter, not as evidence for anything.
	mig=$(awk '/^pgmigrate_success/ { print $2 }' /proc/vmstat)
	pmmu=$(irqsum 'panfrost-mmu')
	# The CPU's ACTUAL frequency, not the governor's name. Pinning to the
	# performance governor does not stop thermal throttling from changing
	# it, so a DVFS experiment that only checks the governor proves
	# nothing. If khz= moves during a supposedly-pinned run, the run is
	# void the same way a CMA drop voided the carveout arm.
	khz=$(cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq 2>/dev/null || echo 0)
	echo "SOAK t=${t}s ve=${ve} ve_delta=$((ve - VE0)) gpu=${gpu} gpu_rate=$(((gpu - PREVGPU) / PERIOD))/s afbd_rate=$(((afbd - PREVAFBD) / PERIOD))/s mmu_delta=$((mmu - MMU0)) pmmu_delta=$((pmmu - PMMU0)) mig_delta=$((mig - MIG0)) khz=${khz} cma=${cma}kB deaths=${DEATHS}"
	PREVGPU=$gpu
	PREVAFBD=$afbd
done

kill "$MPID" 2>/dev/null
sleep 2
ve=$(irqsum 'video-codec')
gpu=$(irqsum 'panfrost')
mmu=$(irqsum 'iommu')
afbd=$(irqsum 'h713-afbd')
mig=$(awk '/^pgmigrate_success/ { print $2 }' /proc/vmstat)
pmmu=$(irqsum 'panfrost-mmu')
echo "SOAK DONE vo=${VO} t=$(($(date +%s) - T0))s deaths=${DEATHS} ve_delta=$((ve - VE0)) gpu_delta=$((gpu - GPU0)) afbd_delta=$((afbd - AFBD0)) mmu_delta=$((mmu - MMU0)) pmmu_delta=$((pmmu - PMMU0)) mig_delta=$((mig - MIG0))"
# The last few distinct fault addresses, if any. The count above is the truth;
# these are the addresses the ratelimiter let through, which is what identifies
# the master and tells you where it went.
dmesg | grep -a 'Page fault for' | tail -20 | sed 's/^/SOAK fault /'
