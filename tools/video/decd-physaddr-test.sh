#!/bin/sh
# decd-physaddr-test.sh -- fetch the frame by PHYSICAL address under IOMMU bypass.
#
# Every visible run so far has fetched through an IOMMU mapping (master 2
# translating, patch 0076).  decd-client stages the frame in a *reserved
# carveout* at a known physical address (IMAGE_PHYS 0x6c500000), and that
# memory was verified byte-exact against the source file.  So the same frame
# can be fetched with no translation at all -- which is what stock does
# (vendor DTB leaves dec@5600000 on master 2 in bypass).
#
# This removes the IOMMU from the picture entirely and tests whether the
# mapping contributes to the diagonal shear.
#
# ORDERING MATTERS.  Set bypass BEFORE writing the physical addresses:
#   - bypass first  -> the stale IOVA is read as a physical address.  Garbage
#     fetch, benign, seen many times, recoverable.
#   - addresses first -> a physical address presented to a translating IOMMU
#     is an unmapped IOVA -> page fault on master 2, which has blacked the
#     panel until a power cycle before.
# Garbage is cheap.  Faults are not.

set -u

Y_PHYS=0x6c500000
C_PHYS=0x6c5E1000     # +0xE1000 = 1280*720
BYPASS=0x02010030
LATCH=0x05600014
R_Y=0x05600070
R_C=0x05600084
FRAME=${FRAME:-/root/decd-test-frame.nv12}
DWELL=${DWELL:-30}

d() { busybox devmem "$1" 32; }
w() { busybox devmem "$1" 32 "$2"; }

say() { echo "$*"; echo "physaddr: $*" > /dev/kmsg 2>/dev/null; }

say "=== state before ==="
say "core   0x0306101c = $(d 0x0306101c)"
say "bypass $BYPASS = $(d $BYPASS)"

# Stage the frame and leave the source enabled.  decd-client holds for its
# dwell; we run it in the background and reprogram underneath it.
say "staging $FRAME via decd-client (carveout $Y_PHYS)"
/root/decd-client show "$FRAME" $((($DWELL + 20) * 1000)) &
CLIENT=$!
sleep 4

say "=== after submit (driver's own programming) ==="
say "bypass = $(d $BYPASS)   Y = $(d $R_Y)   C = $(d $R_C)"
say "info   = $(d 0x05600098)"

# 1. bypass FIRST (see ordering note above)
say "--- setting IOMMU master 2 to BYPASS ---"
w $BYPASS 0x7C
say "bypass = $(d $BYPASS)"

# 2. now the physical addresses
say "--- programming PHYSICAL Y=$Y_PHYS C=$C_PHYS ---"
w $R_Y $Y_PHYS
w $R_C $C_PHYS
say "Y = $(d $R_Y)   C = $(d $R_C)"

# 3. latch.  0x05600014 is self-clearing: reading 0 back is SUCCESS, so do not
#    readback-verify it (that mistake cost a run once already).
w $LATCH 1
say "latched (0x05600014 reads $(d $LATCH), 0 = consumed = success)"

say "=== HOLDING ${DWELL}s -- LOOK AT THE PANEL NOW ==="
i=0
while [ $i -lt $DWELL ]; do
	sleep 5
	i=$((i + 5))
	say "  t=${i}s  Y=$(d $R_Y) C=$(d $R_C) bypass=$(d $BYPASS)"
done

say "=== done; leaving state as-is for inspection ==="
wait $CLIENT 2>/dev/null
say "client exited"
