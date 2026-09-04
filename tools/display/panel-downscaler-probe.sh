#!/usr/bin/env bash
# Is the PANEL down-scaler at 0x051c0124 live on our path? RUNS ON THE HOST.
#
# WHY THIS IS NOT scaler-probe.sh AGAIN. That script probes 0x05000000, which
# static analysis has since pinned as NRWinNode's scaler -- the SOURCE stage of
# the MIPS window layer, in a part of the pipeline we do not own. Every write to
# it has been inert and the visible ratio test came back negative.
#
# This is a DIFFERENT block. PanelWinNode::WriteDownScalerRatio (0x8b1a58c0 in
# display.bin) programs a down-scaler at 0x051c0124-0x051c0138 -- inside the
# LVDS window, which our KMS driver already maps and already writes: the plane
# selector at 0x051c006c is ours, and its effect on the panel was established
# causally. So unlike 0x05000000, this block is demonstrably in our path with
# the MIPS parked. Full derivation:
# docs/reference/mips-wce-window-layer-2026-09-04.md
#
# THE DECODE, from the firmware, cross-checked against a stock Android capture
# (docs/reference/stock-osd-lvds-coupled-2026-08-31.txt) on all five registers:
#
#   0x051c0124  bits [26:25] = 3            enable        stock: 0x06000000
#   0x051c0128  bits [15:0]  = width                      stock: 0x00000500  1280
#   0x051c012c  bits [15:0]  = height                     stock: 0x000002D0   720
#   0x051c0130  = (width << 16) | height                  stock: 0x050002D0
#   0x051c0138  bits [21:0]  = ratio, 16.16 fixed point   stock: 0x08010000  unity
#
# WHAT PHASE 1 SETTLES. Nobody has ever read these on our board -- patch 0078
# maps <0x051c0000 0x100>, 0x24 bytes short, and no h713_disp dump block reaches
# them. So "is this configured on a U-Boot-initialised pipeline, or is it
# stock-only state?" is currently unknown and costs one devmem loop.
#
# WHAT A NULL MEANS, stated before the run so it cannot be reinterpreted after:
#   * enable clear, ratio zero -> U-Boot never programs it. Says nothing about
#     whether it works; phase 3 still applies, it just has more to set up.
#   * enable set, ratio unity  -> U-Boot leaves it exactly as stock does, and
#     phase 3 is a one-register change.
#   * writes do not stick       -> gated with the MIPS parked, same wall as
#     0x05000000, and this route closes too.
#
# SAFETY. Phases 1 and 2 are read-only. Phase 3 (--visible) writes ONE register
# on live display hardware, holds it for a dwell, restores it and verifies the
# restore; a failed restore aborts and is reported as the serious result it is.
# The script refuses to run with the display MIPS alive: live MIPS plus real
# Cedrus/DECD traffic is a reproducible whole-SoC hard lock with no watchdog.
#
# PHASE 3 NEEDS AN OPERATOR WATCHING THE PANEL. This block has the same problem
# 0x05000000 has -- at unity, an inline pass-through configured to do nothing is
# indistinguishable by register read from a block that is not in the path. Only
# eyes decide. Ask, end the turn, wait for "ready", then run.
#
#   usage: tools/display/panel-downscaler-probe.sh              # read-only
#          tools/display/panel-downscaler-probe.sh --visible    # WATCH THE PANEL
#          BOARD=192.168.4.1 HOLD=8 RATIO=0x018000 ... --visible
set -uo pipefail

BOARD=${BOARD:-192.168.4.1}
SSH="ssh -o ConnectTimeout=8 root@$BOARD"
HOLD=${HOLD:-8}
# 0x018000 = 1.5 in 16.16 -- the 1080->720 ratio, i.e. the case this whole
# thread is about. Overridable so a sweep does not need an edit.
RATIO=${RATIO:-0x00018000}
DO_VISIBLE=0
rc=0

for arg in "$@"; do
	case "$arg" in
	--visible) DO_VISIBLE=1 ;;
	*) echo "unknown argument: $arg" >&2; exit 2 ;;
	esac
done

# 0x0120 and 0x0134 are in the window because the firmware's BYPASS path writes
# them (0x0120 bits [26:24] = 2), so they are part of the same control group
# even though the enable path leaves them alone.
OFFS="0120 0124 0128 012c 0130 0134 0138 013c"

say() { printf '%s\n' "$*"; }
rule() { printf '%s\n' "------------------------------------------------------------"; }

read_block() {
	local cmd=""
	for off in $OFFS; do
		cmd+="printf '051c%s ' $off; busybox devmem 0x051c$off 32; "
	done
	$SSH "$cmd" 2>&1
}

# ---------------------------------------------------------------- preflight
rule
say "PREFLIGHT"
if ! $SSH true 2>/dev/null; then
	say "  cannot reach root@$BOARD -- is the board up?"
	exit 1
fi
say "  kernel: $($SSH 'uname -r' 2>/dev/null)"

# The MIPS reset status register. 1 means the core is running, and this script
# must not run in that state.
mips=$($SSH 'busybox devmem 0x0306101c 32' 2>/dev/null)
say "  MIPS reset status 0x0306101c: ${mips:-<unreadable>}"
case "$mips" in
"" ) say "  REFUSING: could not read the MIPS state."; exit 1 ;;
*0x00000000 ) say "  MIPS is parked -- safe to proceed." ;;
* ) say "  REFUSING: the MIPS is alive. Live MIPS + our traffic hard-locks the SoC."; exit 1 ;;
esac

# ------------------------------------------------------- phase 1: the read
rule
say "PHASE 1 -- the panel down-scaler control group, read-only"
say "  (stock Android idle, for comparison: 0124=0x06000000 0128=0x00000500"
say "   012c=0x000002D0 0130=0x050002D0 0138=0x08010000)"
say ""
before=$(read_block)
say "$before"

en=$($SSH 'busybox devmem 0x051c0124 32' 2>/dev/null)
ratio=$($SSH 'busybox devmem 0x051c0138 32' 2>/dev/null)
say ""
say "  enable field 0x051c0124[26:25] = $(( ( ${en:-0} >> 25 ) & 3 ))   (3 = enabled)"
say "  ratio  field 0x051c0138[21:0]  = $(printf '0x%06x' $(( ${ratio:-0} & 0x3fffff )))   (0x010000 = unity)"

# ------------------------------------- phase 2: is anything moving at all?
rule
say "PHASE 2 -- resample after 3 s; anything that moves at idle is not config"
sleep 3
after=$(read_block)
if [ "$before" = "$after" ]; then
	say "  no register changed. Consistent with a configuration block."
else
	say "  CHANGED:"
	diff <(printf '%s\n' "$before") <(printf '%s\n' "$after") | sed 's/^/    /'
fi

if [ "$DO_VISIBLE" -eq 0 ]; then
	rule
	say "Read-only phases done. Re-run with --visible, operator watching, to"
	say "set a non-unity ratio. That is the only test that decides."
	exit 0
fi

# --------------------------------------------- phase 3: the visible ratio
rule
say "PHASE 3 -- VISIBLE. Writing ratio $RATIO to 0x051c0138[21:0] for ${HOLD}s."
say "  Watch the panel. A change in picture size is the result; no change is"
say "  also a result and means this block is not acting on our raster."

orig=$($SSH 'busybox devmem 0x051c0138 32' 2>/dev/null)
if [ -z "$orig" ]; then
	say "  could not read 0x051c0138 -- aborting without writing."
	exit 1
fi
new=$(( ( orig & ~0x3fffff ) | ( RATIO & 0x3fffff ) ))
say "  0x051c0138: $orig -> $(printf '0x%08x' $new)"

$SSH "busybox devmem 0x051c0138 32 $(printf '0x%08x' $new)" >/dev/null 2>&1
got=$($SSH 'busybox devmem 0x051c0138 32' 2>/dev/null)
say "  readback: ${got:-<unreadable>}"
if [ "$(( ${got:-0} ))" -ne "$new" ]; then
	say "  WRITE DID NOT STICK -- the field is gated with the MIPS parked."
	say "  That is itself the answer; restoring anyway."
	rc=1
fi

sleep "$HOLD"

$SSH "busybox devmem 0x051c0138 32 $orig" >/dev/null 2>&1
restored=$($SSH 'busybox devmem 0x051c0138 32' 2>/dev/null)
say "  restored to: ${restored:-<unreadable>}"
if [ "$restored" != "$orig" ]; then
	say "  RESTORE FAILED. 0x051c0138 is not back at $orig. Do not power-cycle"
	say "  before recording this; a failed restore on live display hardware is"
	say "  a more important result than the ratio test."
	exit 2
fi

rule
say "Done. Record what the operator saw, including 'no change'."
exit $rc
