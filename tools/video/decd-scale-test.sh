#!/bin/sh
# decd-scale-test.sh -- the original goal: hardware scaling, no GPU.
#
# ############################################################################
# PHASE=scale IS DEAD.  DO NOT RUN IT.  Refuted 2026-09-10, statically:
#   docs/reference/composition-ratio-registers-are-line-buffers-2026-09-10.md
#
# 0x05000174 / 0x050001b4 / 0x050000f0 are NOT scaler ratio registers.  They
# are the AFBD fetch line-buffer descriptor -- Rowbyte, LineBufLevel and
# LineNumber for the Y and C planes -- named in the producing function's own
# log line (FrameBuffer::GetPsuPfuWin, 0x8b1a2668).  There is no ratio in this
# block and nothing here scales.
#
# The "ratio = (source/output)*64" encoding below is an artefact: Rowbyte is
# LINEAR IN THE PICTURE WIDTH, so any two widths give a value ratio equal to
# the width ratio whether or not anything scales.  That is the whole of the
# "43/64 ~ 852/1280" evidence.
#
# Writing 0x00600060 here sets the fetch row length and line-buffer level to 96
# while the source geometry says otherwise.  THAT is the wedge -- a starved or
# overrun fetch, which only a reboot clears.  Two runs, two wedges.  The
# missing 0x05000040 bit-25 apply would not have helped; the values are wrong
# in kind.
#
# PHASE=crop is still a valid crop demonstration and is left runnable.
#
# The live scaling lead is now the panel down-scaler, 0x051c0120..0x051c0138 --
# and note that its 2026-09-04 negative was WITHDRAWN: both runs wrote the
# ratio alone and left 0x051c0124[26:25] = 3, which is the BYPASSED state.
# ############################################################################
#
# Puts a 1920x1080 NV12 frame on a 1280x720 panel by programming the
# firmware-owned composition block's scaler, and compares it against the
# unscaled (cropped) case.
#
# WHY THIS IS NOW POSSIBLE.  Patch 0095 derives the AFBD source geometry from
# the submitted descriptor, so staging a 1080p frame programs the fetcher
# automatically -- verified:
#
#   DECD route: 1920x1080 stride 1920 hw-format 3
#   0x05600020 = 0x0437077F   0x05600030 = 0x04380780
#   0x05600040 = 0x00000780   0x0560004c = 0x021C0780
#
# The firmware does NOT follow suit on composition: it only reprograms that
# block when it SERVICES a frame, and our ring writer is capped at
# ring_writes_max=1.  So composition stays at 1280x720 unity and must be set
# here.
#
# THE SCALER ENCODING, derived from the two states in
# reference/frame-composition-block-capture-2026-08-31.txt:
#
#   source 1280 -> output 1280 : 0x05000174 = 0x40 = 64/64  (unity)
#   source  852 -> output 1280 : 0x05000174 = 0x2B = 43/64  (852/1280*64 ~ 43)
#
#   ratio = (source / output) * 64
#
# So 1920 -> 1280 and 1080 -> 720 are both 1.5, giving 96 = 0x60, i.e.
# 0x00600060.  That is a PREDICTION this test checks, not a captured value.
#
# UNCERTAIN, flagged honestly: 0x05000278 and 0x050002b8.  Their low halves
# track the source height (h/2 and h respectively) and are derived here, but
# their high halves differ between the two captured states (0x6002 vs 0xe002)
# in a way two data points cannot explain.  The 1280x720 high half is carried
# over.  If the picture is geometrically wrong in a way the ratio does not
# explain, suspect these two first.
#
#   PHASE=crop   composition left at 1280x720 unity -> expect the TOP-LEFT
#                1280x720 crop of the 1080p frame, not the whole picture
#   PHASE=scale  composition set for a 1920x1080 source -> expect the WHOLE
#                frame, scaled down to fit
#
# Success is the full picture appearing where a crop was.

set -u

FRAME=${FRAME:-/root/frame-1080p.nv12}
CLIENT=${CLIENT:-/root/decd-client.coord1080}
PHASE=${PHASE:-crop}

if [ "$PHASE" = scale ] && [ "${I_KNOW_SCALE_IS_REFUTED:-}" != yes ]; then
	echo "decd-scale-test.sh: PHASE=scale is refuted and costs a reboot." >&2
	echo "  0x05000174/0x1b4/0x0f0 are line-buffer geometry, not ratios." >&2
	echo "  See docs/reference/composition-ratio-registers-are-line-buffers-2026-09-10.md" >&2
	echo "  Override with I_KNOW_SCALE_IS_REFUTED=yes only to reproduce the wedge." >&2
	exit 2
fi
DWELL=${DWELL:-30}
SRC_W=1920
SRC_H=1080
Y_PHYS=0x6c500000
# chroma follows luma: 1920*1080 = 0x1FA400
C_PHYS=0x6c6FA400
Y_SLOTS="0x05600070 0x05600074 0x05600078 0x0560007c"
C_SLOTS="0x05600084 0x05600088 0x0560008c 0x05600090"

rd() { busybox devmem "$1" 32; }
wr() { busybox devmem "$1" 32 "$2"; }
say() { echo "$*"; echo "scale: $*" > /dev/kmsg 2>/dev/null; }

[ "$(rd 0x0306101c)" = 0x00000001 ] || { echo "ABORT: MIPS not alive" >&2; exit 1; }
[ -r "$FRAME" ] || { echo "ABORT: no $FRAME" >&2; exit 1; }

COMP="0x050000f0 0x05000210 0x05000174 0x05000178 0x050001b4 0x050001b8 0x05000224 0x05000274 0x05000278 0x050002b4 0x050002b8 0x05000444 0x05000544 0x05000804 0x0500080c 0x05000840 0x05000844 0x05000858 0x0500085c"
ROUTE="0x051c006c 0x05140508"

key() { echo "SAVE_$(echo "$1" | tr -d 'x')"; }
SNAPPED=0
snapshot() {
	for r in $COMP $ROUTE; do eval "$(key $r)=$(rd $r)"; done
	[ "$(rd 0x051c006c)" = 0x00000000 ] && SAVE_0051c006c=0x29000000
	SNAPPED=1
}
restore() {
	say "--- restoring ---"
	[ "$SNAPPED" = 1 ] && {
		wr 0x051c006c "$SAVE_0051c006c" 2>/dev/null || true
		for r in $COMP 0x05140508; do
			eval "v=\${$(key $r):-}"
			[ -n "$v" ] && wr "$r" "$v" 2>/dev/null || true
		done
	} || wr 0x051c006c 0x29000000 2>/dev/null || true
	# Put the AFBD side back BEFORE composition.  A failed run used to leave the
	# video source enabled at 1920x1080 on a 720p panel, which wedged the display
	# so hard that even the logo would not come back and the next run then
	# snapshotted the wedged state as its baseline.  An experiment must leave the
	# board able to show what it started with.
	wr 0x05600010 "$(printf '0x%08X' $(( $(rd 0x05600010) & 0xFFFFFFFC )))" 2>/dev/null || true
	wr 0x05600014 1 2>/dev/null || true
	wr 0x05600020 0x02CF04FF 2>/dev/null || true
	wr 0x05600030 0x02D00500 2>/dev/null || true
	wr 0x05600048 0x02D00500 2>/dev/null || true
	wr 0x0560004c 0x01680500 2>/dev/null || true
	wr 0x05600040 0x00000500 2>/dev/null || true
	wr 0x05600044 0x00000500 2>/dev/null || true
	wr 0x05600014 1 2>/dev/null || true

	# The restore must COMMIT too.  Writing the registers back is not enough:
	# composition latches on the 0x05000840[31:16] sequence counter, so without
	# a bump the block keeps whatever it last latched and the logo does not come
	# back.  That is exactly what happened on 2026-09-09 -- the panel stayed
	# black after a run and the NEXT run then snapshotted the drifted values as
	# "inherited" and faithfully restored the wrong ones.
	_v=$(rd 0x05000840)
	_seq=$(( (((_v >> 16) & 0xFFFF) + 1) & 0xFFFF ))
	wr 0x05000840 "$(printf '0x%08X' $(( (_seq << 16) | (_v & 0xFFFF) )))" 2>/dev/null || true
	[ -z "${PID:-}" ] || kill "$PID" 2>/dev/null || true
	say "restored: selector=$(rd 0x051c006c) ratio=$(rd 0x05000174) 0x840=$(rd 0x05000840)"
}
trap restore EXIT INT TERM

say "=== ${SRC_W}x${SRC_H} -> 1280x720, PHASE=$PHASE ==="
DECD_W=$SRC_W DECD_H=$SRC_H "$CLIENT" show "$FRAME" $(( (DWELL + 25) * 1000 )) >/tmp/scale-client.log 2>&1 &
PID=$!
sleep 4
kill -0 "$PID" 2>/dev/null || { echo "ABORT: client died"; tail -3 /tmp/scale-client.log; exit 1; }
snapshot

# ADDRESSING.  The driver dma-maps the carveout and leaves an IOVA in the ring,
# but master 2 is in bypass, so the fetcher reads a non-DRAM address and the
# panel goes white.  The first version of this script omitted this entirely and
# produced exactly that.  Use the proven static configuration: bypass on, and
# the carveout's real physical addresses in all four slots, published through
# the two-plane latch.
wr 0x02010030 0x7C
for r in $Y_SLOTS; do wr "$r" $Y_PHYS; done
for r in $C_SLOTS; do wr "$r" $C_PHYS; done
wr 0x0560006c 1
say "bypass=$(rd 0x02010030) Y0=$(rd 0x05600070) C0=$(rd 0x05600084) (physical)"

say "AFBD (programmed by patch 0095 from the descriptor):"
say "  0x20=$(rd 0x05600020) 0x30=$(rd 0x05600030) pitch=$(rd 0x05600040) chroma=$(rd 0x0560004c)"

if [ "$PHASE" = scale ]; then
	# ratio = (source/output)*64 = 1.5*64 = 96 = 0x60
	wr 0x050000f0 0x63006060
	wr 0x05000210 0x63006060
	for r in 0x05000174 0x050001b4 0x05000274 0x050002b4; do wr "$r" 0x00600060; done
	# source size words
	for r in 0x05000224 0x05000444 0x05000544; do wr "$r" 0x04380780; done
	wr 0x05000804 0x002C0780          # (0x2c << 16) | 1920
	wr 0x0500080c 0x00140438          # (0x14 << 16) | 1080
	wr 0x05000844 0x07800030          # (1920 << 16) | 0x30
	wr 0x05000858 0x04380015          # (1080 << 16) | 0x15
	wr 0x0500085c 0x07800030
	# 0x178 / 0x1b8 -- THE PAIR THAT WAS MISSING.
	#
	# Traced in display.bin: PanelWinNode::update (0x8b1a48cc) writes 0x174 and
	# 0x178 as a PAIR, and 0x1b4/0x1b8 likewise, with an explicit hardcoded
	# 1080-source path:
	#
	#   0x8b1a4990  addiu $t0, $zero, 0x438   ; 1080 -> 0x1b8 low 16
	#   0x8b1a49a0  addiu $t0, $zero, 0x21c   ;  540 -> 0x178 low 16
	#
	# So 0x178/0x1b8 carry the source heights (chroma and luma), and the
	# firmware demonstrably supports a 1080 source -- which also retires the
	# "the scaler is upscale-only" guess.
	#
	# The earlier attempt wrote 0x174/0x1b4 but left 0x178/0x1b8 at their 720p
	# values (360/720) while everything else said 1080.  That mismatch is the
	# most likely cause of the black panel.
	#
	# Read-modify-write the low 16 bits only, exactly as the firmware's
	# `ins rt, rs, 0, 0x10` does; the high halves are not ours to invent.
	ins_low16() {
		_v=$(rd "$1")
		wr "$1" "$(printf '0x%08X' $(( (_v & 0xFFFF0000) | ($2 & 0xFFFF) )))"
	}
	ins_low16 0x05000178 $(( SRC_H / 2 ))   # chroma height, 540
	ins_low16 0x050001b8 $SRC_H             # luma height,  1080
	ins_low16 0x05000278 $(( SRC_H / 2 ))
	ins_low16 0x050002b8 $SRC_H
	say "heights: 0x178=$(rd 0x05000178) 0x1b8=$(rd 0x050001b8) 0x278=$(rd 0x05000278) 0x2b8=$(rd 0x050002b8)"

	# legacy override, kept only to reproduce the earlier failure
	if false; then
	#
	# Their low halves track source height (h/2 and h) but their high halves
	# differ between the two captured states (0x6002 vs 0xe002) in a way two
	# data points cannot explain.  Writing guessed values here produced a fully
	# BLACK panel, consistent with an output window pushed off-screen.  Leaving
	# them untouched isolates them from the ratio.
		:
	fi
	say "composition set for a ${SRC_W}x${SRC_H} source, ratio 0x00600060 (1.5x)"
else
	say "composition left at 1280x720 unity -- expect a top-left crop"
fi

# COMMIT.  0x05000840[31:16] is a SEQUENCE COUNTER, not a geometry word.
# PanelWinNode::update ends with:
#
#   lw    $v0, 0x138($s0)       ; the node's counter
#   lw    $a0, 0x840($v1)
#   addiu $v0, $v0, 1           ; INCREMENT
#   ins   $a0, $v0, 0x10, 0x10  ; into bits [31:16]
#   sw    $a0, 0x840($v1)
#
# so composition latches when that counter changes.  Nothing here ever bumped
# it, which is why the block kept using its latched 720p state and the panel
# stayed black however correct the other words were.
#
# This also corrects a misread: the captured 720p value 0x02d10015 has 0x2d1 =
# 721 in the high half, which looked like height+1 and is in fact just the
# counter's value at the moment of capture.
if [ "$PHASE" = scale ]; then
	_v=$(rd 0x05000840)
	_seq=$(( (((_v >> 16) & 0xFFFF) + 1) & 0xFFFF ))
	wr 0x05000840 "$(printf '0x%08X' $(( (_seq << 16) | (_v & 0xFFFF) )))"
	say "composition commit: 0x840 $_v -> $(rd 0x05000840)"
fi

wr 0x05140508 0x144C0000
sleep 0.2
wr 0x051c006c 0x39000000

say "ratio=$(rd 0x05000174) srcsize=$(rd 0x05000224) selector=$(rd 0x051c006c)"
say "=== HOLDING ${DWELL}s -- LOOK NOW ==="
i=0
while [ $i -lt $DWELL ]; do
	sleep 5; i=$((i + 5))
	say "  t=${i}s ratio=$(rd 0x05000174) Y0=$(rd 0x05600070) core=$(rd 0x0306101c)"
done
say "=== done ==="
