#!/usr/bin/env bash
# Letterbox Phase 1: can the display show a picture smaller than the panel,
# placed where the recipe says? RUNS ON THE HOST. See docs/letterbox-plan.md
# (Phase 1) and docs/reference/letterbox-recipe-2026-10-04.md.
#
# One axis per step, each a single write sequence with a timed restore:
#
#   z   1280x720 at (0,0),     stride 1280   NO-OP: every value rewritten as
#                                            it is -- exercises source off/on,
#                                            the NR bracket and the restore.
#                                            Run first; the card should blink
#                                            and come back identical.
#   a   1280x536 at (0,0),     stride 1280   height only
#   b   1280x536 at (0,92),    stride 1280   + vertical offset
#   c    852x480 at (214,120), stride  864   width + horizontal offset
#
# PIECES:
#   letterbox-card     (target) holds a native 1280x720 control card on the
#                      video plane through KMS, with the step cards pre-rendered
#                      in the same buffer object; writes /tmp/letterbox-card.layout
#   letterbox-recipe.py (host) every register and value, from the firmware model
#   letterbox-apply.py (target) preflight, firmware-ordered writes, hold,
#                      restore -- detached, so a dropped ssh cannot strand a step
#
# USAGE, in this order:
#   letterbox-test.sh prep          copy the tools, build letterbox-card on the board
#   letterbox-test.sh card          control card up; fresh baseline; compare to the
#                                   stored one; recipe self-test against it
#   letterbox-test.sh plan  z|a|b|c dry run: preflight and every write, no writes
#   letterbox-test.sh step  z|a|b|c the real thing: PRE_S countdown, HOLD_S window,
#                                   restore; prints the executor's log
#   letterbox-test.sh all           ONE "ready" runs everything: card up + checks,
#                                   LEAD_S to get into position, then z a b c back to
#                                   back (GAP_S of control card between, HOLD_S each),
#                                   then the plane is released -- the console coming
#                                   back is the operator's cue to stop recording
#   letterbox-test.sh plan  all     dry run of the whole sequence (card must be up)
#   letterbox-test.sh bisect        like `all`, but step b repeated with ONE vertical
#                                   candidate changed per window (BISECT_VARIANTS);
#                                   `plan bisect` dry-runs it
#
# BISECT (2026-10-04): the first run clipped the BOTTOM of every vertically
# offset picture (b lost 73 of 536 lines, c 89 of 480; a and all horizontal
# placement were right). Each variant below is step b with one change; the
# window that shows the whole card names the register:
#   b0  as recipe (reproduces the clip)
#   b1  proc+050[15:0]  = H+dy           V line-enable length reaches the end
#   b2  proc+050        = [27, H+dy]     ... and its start left unshifted
#   b3  lvds+040/0a8[31:16] = H+dy       panel video window height
#   b4  comp+840[31:16] = H+1+dy, comp+80c[15:0] = H+dy   NR fetch heights
# Every variant ends at or before the native configuration's last line
# (timing 742/747), so none asks for more lines than native video does.
# SET 1 (above) was ALL NEGATIVE (2026-10-05): every window clipped alike.
# BISECT_SET=2 (default) reverts ONE dy-shifted field per window to native:
#   b0  as recipe          b1  vblender border overlay left native (no bars)
#   b2  comp+80c y native  b3  comp+858 y native     b4  comp+840 y native
# SET 2 (2026-10-05): overlay not the clip (b1: zero borders -> garbage above
# the picture, card green-tinted, same clip); comp+840 y = fetch start (b4:
# card scrolls); comp+858 y moves the window END (b3: end 555 -> 535).
# BISECT_SET=3: line counts -- b1 chan-B LineNumber H+dy, b2/b3 comp+858
# [31:16] = H / 720+dy, b4 AFBD budgets H+dy.
#   letterbox-test.sh phase3        like `all`, for Phase 3 (proc MAGNIFIES a small
#                                   card up to its destination): z then
#                                   s1 s2 s3 s4 s4h s5 (below); `plan phase3` dry-runs
#
# PHASE 3 STEPS (source in memory -> destination on the panel):
#   s1   640x360 -> 1280x720 at (0,0)     2x both axes, whole panel
#   s2   852x480 -> 1278x720 at (0,0)     1.5x, non-integer, stride 864
#   s3   720x576 ->  960x720 at (160,0)   unequal ratios (1.333 H, 1.25 V) +
#                                         pillarbox: circles about 7% WIDE
#   s4   352x288 ->  880x720 at (200,0)   2.5x + pillarbox, 200-px bars
#   s4h  s4 with proc+038[31:16] = 1280-880+16 = 416: the firmware writes
#        out.w < X ? X - out.w + 16 : 16 there, X unknown (node+0x90); live 16.
#        Same picture as s4 means the field does not matter here.
#   s5   640x360 ->  960x540 at (160,90)  magnified AND placed on both axes
#   letterbox-test.sh phase3b       the Phase 3 bisect (p0 p1 p2 p3 q3 q5 q1, below)
#   letterbox-test.sh mirror        WP5 Phase 1 (docs/mirror-plan.md), ONE "ready":
#                                   video card up + checks (stock self-test too),
#                                   LEAD_S, video steps z h v hv ch abv, then the
#                                   holder switches to the PRIMARY card (OSD route)
#                                   and runs pv php pho, then the plane is released.
#                                   `plan mirror` dry-runs both halves
#   letterbox-test.sh card-primary  the RGB card on the primary plane + its gates
#
# MIRROR STEPS (hardware mirror, recipe --mirror; expected on the glass):
#   h    native, mirror 1 (H)        left/right swapped, nothing shifted
#   v    native, mirror 2 (V)        top/bottom swapped
#   hv   native, mirror 3            rotated 180
#   ch   852x480 at client (0,0), H  at (428,0), mirrored: bars L428 R0
#   abv  1280x536 at client (0,0), V at (0,184), flipped, NO magenta at its top
#   pv   primary card, OSD ctrl [3:2]=2           top/bottom swapped?
#   php  primary card, panel 0x051c00a0[0]=1      left/right swapped? all 4 edges?
#   pho  primary card, OSD ctrl [3:2]=1           left/right swapped?
#   letterbox-test.sh show  z|a|b|c|s1..s5 each recipe register now: old / NEW / ???
#   letterbox-test.sh restore       emergency: put back /tmp/letterbox-saved.json
#   letterbox-test.sh off           release the plane (console returns)
#
# OPERATOR: prompt BEFORE `step`, in its own turn, and wait for "ready". The
# window opens PRE_S seconds after launch and stays open HOLD_S seconds.
# HANDHELD VIDEO, no tripod: start recording before "ready", keep the whole
# panel in frame, hold still through the switch in and out, stop a few seconds
# after the control card returns. letterbox-measure.py rectifies each step
# frame on the control-card frames either side of it (tens of ms apart), so
# the hand only has to be steady across the transitions. Look for: card intact
# (circles round, diagonals straight, no shear); where it sits; bar colour vs
# the card's black; any MAGENTA (padding the display should never show).
#
# HAZARDS:
#   * Confirm the U-Boot logo was visible at boot -- "logo published" prints on
#     a black boot too. A wedge needs a power cycle with serial AND USB
#     unplugged, board off >= 1 min. Warm reboots kill this display.
#   * Never `pkill -f` here: the remote command line contains the pattern.
#   * The step refuses unless every register still reads the baseline's value.
set -uo pipefail

BOARD=${BOARD:-192.168.4.1}
SSH="ssh -o ConnectTimeout=20 -o BatchMode=yes root@$BOARD"
SCP="scp -q -o ConnectTimeout=20 -o BatchMode=yes"
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
R=/root/tools/letterbox
REF=${REF:-$REPO/docs/reference/letterbox-baseline-2026-10-04/native-720p.txt}
OUT=${OUT:-$REPO/local/h713-lab/letterbox-phase1-$(date +%Y%m%d)}
DWELL_S=${DWELL_S:-3600}
PRE_S=${PRE_S:-5}
HOLD_S=${HOLD_S:-10}
LEAD_S=${LEAD_S:-30}
GAP_S=${GAP_S:-5}
TAIL_S=${TAIL_S:-5}
SEQUENCE="z a b c"
SEQUENCE_P3="z s1 s2 s3 s4 s4h s5"
SEQUENCE_P3B="p0 p1 p2 p3 q3 q5 q1"
SEQUENCE_MV="z h v hv ch abv"
SEQUENCE_MP="pv php pho"
STOCK=${STOCK:-$REPO/local/h713-lab/stock-capture-20261001/out}
FRESH=$OUT/native-card.txt

say(){ printf '%s\n' "$*"; }

step_params(){
	OUTSZ=; VARIANT=; MIRROR=0; REFLECT=
	case "${1:-}" in
	s1)  SIZE=640x360; OUTSZ=1280x720; AT=0,0;    PITCH=640; REGION=s640; return ;;
	s2)  SIZE=852x480; OUTSZ=1278x720; AT=0,0;    PITCH=864; REGION=c;    return ;;
	s3)  SIZE=720x576; OUTSZ=960x720;  AT=160,0;  PITCH=720; REGION=s720; return ;;
	s4)  SIZE=352x288; OUTSZ=880x720;  AT=200,0;  PITCH=352; REGION=s352; return ;;
	s4h) SIZE=352x288; OUTSZ=880x720;  AT=200,0;  PITCH=352; REGION=s352
	     VARIANT="proc 0x038 16 16 416"; return ;;
	s5)  SIZE=640x360; OUTSZ=960x540;  AT=160,90; PITCH=640; REGION=s640; return ;;
	# PHASE 3 BISECT (2026-10-05): the first phase3 run cut every magnified
	# picture after H PANEL lines (s4 showed source lines 0..~115 = 288/2.5,
	# then flat white). Something downstream of the fetch still counts source
	# lines. Each variant changes NR's vertical window fields to the
	# DESTINATION height; the window that shows the whole card names it.
	#   p0  s4 as recipe (reproduces the cut)
	#   p1  s4, comp+858[31:16] = OH        (NR output window end; Phase 1's field)
	#   p2  s4, p1 + comp+840[31:16] = OH+1 (fetch window h) + comp+80c[15:0] = OH
	#   p3  s4, comp+840/80c only           (ranks: is p1 alone enough?)
	#   q3/q5/q1  s3/s5/s1 with p1          (generality: another ratio, both offsets, 2x)
	p0) step_params s4; return ;;
	p1) step_params s4; VARIANT="comp 0x858 16 16 720"; return ;;
	p2) step_params s4; VARIANT="comp 0x858 16 16 720; comp 0x840 16 16 721; comp 0x80c 0 16 @720"; return ;;
	p3) step_params s4; VARIANT="comp 0x840 16 16 721; comp 0x80c 0 16 @720"; return ;;
	q3) step_params s3; VARIANT="comp 0x858 16 16 720"; return ;;
	q5) step_params s5; VARIANT="comp 0x858 16 16 540"; return ;;
	q1) step_params s1; VARIANT="comp 0x858 16 16 720"; return ;;
	esac
	case "${1:-}" in
	z) SIZE=1280x720; AT=0,0;     PITCH=1280; REGION=native ;;
	a) SIZE=1280x536; AT=0,0;     PITCH=1280; REGION=ab ;;
	b) SIZE=1280x536; AT=0,92;    PITCH=1280; REGION=ab ;;
	c) SIZE=852x480;  AT=214,120; PITCH=864;  REGION=c  ;;
	# WP5 mirror steps; AT is the CLIENT position, the recipe maps it
	h)   SIZE=1280x720; AT=0,0; PITCH=1280; REGION=native; MIRROR=1 ;;
	v)   SIZE=1280x720; AT=0,0; PITCH=1280; REGION=native; MIRROR=2 ;;
	hv)  SIZE=1280x720; AT=0,0; PITCH=1280; REGION=native; MIRROR=3 ;;
	ch)  SIZE=852x480;  AT=0,0; PITCH=864;  REGION=c;      MIRROR=1 ;;
	abv) SIZE=1280x536; AT=0,0; PITCH=1280; REGION=ab;     MIRROR=2 ;;
	*) say "step must be z, a, b, c, s1..s5, s4h or h v hv ch abv"; exit 2 ;;
	esac
}

check_gates(){
	local bad=0 ctrl sel y lay
	ctrl=$($SSH 'busybox devmem 0x05600010' 2>/dev/null)
	sel=$($SSH 'busybox devmem 0x051c006c' 2>/dev/null)
	y=$($SSH 'busybox devmem 0x05600070' 2>/dev/null)
	lay=$($SSH 'cat /tmp/letterbox-card.layout 2>/dev/null' | awk '$1=="slot_y"{print $2}')
	[ "$ctrl" = "0x03000013" ] || { say "  GATE FAIL video source $ctrl (want 0x03000013)"; bad=1; }
	[ "$sel" = "0x39000000" ] || { say "  GATE FAIL selector $sel (want 0x39000000 = video)"; bad=1; }
	[ -n "$lay" ] || { say "  GATE FAIL no /tmp/letterbox-card.layout (card not up)"; bad=1; }
	[ "$(printf '%s' "$y" | tr 'A-F' 'a-f')" = "$(printf '%s' "$lay" | tr 'A-F' 'a-f')" ] ||
		{ say "  GATE FAIL Y slot $y is not the card's ($lay)"; bad=1; }
	return $bad
}

recipe_json(){	# step -> $OUT/step-<x>.json, from the fresh baseline
	step_params "$1"
	[ -s "$FRESH" ] || { say "no fresh baseline: run 'card' first"; exit 1; }
	python3 "$HERE/letterbox-recipe.py" --live "$FRESH" "$SIZE" "$AT" \
		--pitch "$PITCH" ${OUTSZ:+--out "$OUTSZ"} --mirror "$MIRROR" \
		${REFLECT:+--reflect "$REFLECT"} --json "$OUT/step-$1.json" \
		> "$OUT/step-$1.recipe.txt" ||
		{ cat "$OUT/step-$1.recipe.txt"; say "recipe refused"; exit 1; }
	if [ -n "$VARIANT" ]; then	# one field changed on top of the recipe
		python3 - "$OUT/step-$1.json" "$VARIANT" <<-'EOF' || exit 1
		# "blk off lsb width val; ..."  val "@N" = a REL field's value for a
		# height of N: native value + N - 720 (all rel heights here are
		# live + h - 720)
		import json, sys
		path, spec = sys.argv[1], sys.argv[2]
		doc = json.load(open(path))
		for change in spec.split(";"):
		    blk, off, lsb, width, val = change.split()
		    off, lsb, width = int(off, 0), int(lsb, 0), int(width, 0)
		    m = ((1 << width) - 1) << lsb
		    for r in doc["regs"]:
		        if r["block"] == blk and r["off"] == off:
		            if val.startswith("@"):
		                v = ((r["old"] & m) >> lsb) + int(val[1:]) - 720
		            else:
		                v = int(val, 0)
		            r["new"] = (r["new"] & ~m) | (v << lsb)
		            r["notes"] = r["notes"] + [f"VARIANT [{lsb + width - 1}:{lsb}]={v}"]
		            print(f"  variant {blk}+{off:03x}[{lsb + width - 1}:{lsb}] = {v}")
		            break
		    else:
		        sys.exit(f"{blk}+{off:03x} not in the recipe")
		json.dump(doc, open(path, "w"), indent=1)
		EOF
	fi
	$SCP "$OUT/step-$1.json" "root@$BOARD:$R/step-$1.json" || exit 1
}

follow(){	# follow the detached executor by pid until it exits or the deadline
	local deadline=$(( $(date +%s) + $1 )) alive=
	while [ "$(date +%s)" -lt "$deadline" ]; do
		alive=$($SSH 'p=$(cat /tmp/letterbox-apply.pid 2>/dev/null); [ -n "$p" ] && kill -0 "$p" 2>/dev/null && echo y')
		[ "$alive" = y ] || return 0
		sleep 3
	done
	say "*** executor still running after the deadline -- check the board"
	return 1
}

bisect_json(){	# step b's recipe + one-change variants, and their sequence file
	recipe_json b
	python3 - "$OUT/step-b.json" "$OUT" "${BISECT_SET:-2}" <<-'EOF' || exit 1
	import copy, json, sys
	base, out = json.load(open(sys.argv[1])), sys.argv[2]
	H, dy = base["picture"]["h"], base["picture"]["dy"]
	def setf(doc, blk, off, lsb, width, val):
	    for r in doc["regs"]:
	        if r["block"] == blk and r["off"] == off:
	            m = ((1 << width) - 1) << lsb
	            r["new"] = (r["new"] & ~m) | (val << lsb)
	            r["notes"] = r["notes"] + [f"BISECT [{lsb + width - 1}:{lsb}]={val}"]
	            return
	    sys.exit(f"{blk}+{off:03x} not in the recipe")
	def native(blk, off, lsb, width):        # the field's value before the recipe
	    for r in base["regs"]:
	        if r["block"] == blk and r["off"] == off:
	            return (r["old"] >> lsb) & ((1 << width) - 1)
	sets = {
	    # set 1 (2026-10-05, all NEGATIVE): extend vertical lengths/heights
	    "1": {
	        "b0": [],
	        "b1": [("proc", 0x050, 0, 16, H + dy)],
	        "b2": [("proc", 0x050, 0, 16, H + dy), ("proc", 0x050, 16, 16, 27)],
	        "b3": [("lvds", 0x040, 16, 16, H + dy), ("lvds", 0x0a8, 16, 16, H + dy)],
	        "b4": [("comp", 0x840, 16, 16, H + 1 + dy), ("comp", 0x80c, 0, 16, H + dy)],
	    },
	    # set 3 (after set 2: the output window ends early; line counts?)
	    "3": {
	        "b0": [],
	        "b1": [("comp", 0x2b8, 0, 16, H + dy), ("comp", 0x278, 0, 16, (H + dy) // 2)],
	        "b2": [("comp", 0x858, 16, 16, H)],
	        "b3": [("comp", 0x858, 16, 16, 720 + dy)],
	        "b4": [("afbd", 0x030, 16, 13, H + dy), ("afbd", 0x048, 16, 13, H + dy),
	               ("afbd", 0x04c, 16, 13, (H + dy) // 2)],
	    },
	    # set 2: put ONE dy-shifted field back to its native value
	    "2": {
	        "b0": [],
	        "b1": [("vblend", 0x000, 0, 32, native("vblend", 0x000, 0, 32)),
	               ("vblend", 0x004, 0, 32, native("vblend", 0x004, 0, 32))],
	        "b2": [("comp", 0x80c, 16, 16, native("comp", 0x80c, 16, 16))],
	        "b3": [("comp", 0x858, 0, 16, native("comp", 0x858, 0, 16))],
	        "b4": [("comp", 0x840, 0, 16, native("comp", 0x840, 0, 16))],
	    },
	}
	variants = sets[sys.argv[3]]
	seq = []
	for name, changes in variants.items():
	    doc = copy.deepcopy(base)
	    for c in changes:
	        setf(doc, *c)
	    json.dump(doc, open(f"{out}/step-{name}.json", "w"), indent=1)
	    seq.append({"name": name, "recipe": f"/root/tools/letterbox/step-{name}.json", "region": "ab"})
	    print(f"  {name}: " + (", ".join(f"{b}+{o:03x}[{l + w - 1}:{l}]={v}" for b, o, l, w, v in changes) or "as recipe"))
	json.dump(seq, open(f"{out}/sequence-bisect.json", "w"))
	EOF
	for v in b0 b1 b2 b3 b4; do
		$SCP "$OUT/step-$v.json" "root@$BOARD:$R/step-$v.json" || exit 1
	done
	$SCP "$OUT/sequence-bisect.json" "root@$BOARD:$R/sequence-bisect.json" || exit 1
}

sequence_json(){	# recipes for every step + the sequence file, on the board
	local st items=
	for st in ${1:-$SEQUENCE}; do
		recipe_json "$st"
		items="$items${items:+,}{\"name\": \"$st\", \"recipe\": \"$R/step-$st.json\", \"region\": \"$REGION\"}"
	done
	printf '[%s]\n' "$items" > "$OUT/sequence.json"
	$SCP "$OUT/sequence.json" "root@$BOARD:$R/sequence.json" || exit 1
}

osd_sequence_json(){	# the primary-route steps (no recipe: OSD/panel bits)
	cat > "$OUT/sequence-primary.json" <<-'EOF'
	[{"name": "pv", "kind": "osd", "osd_bits": {"lsb": 2, "width": 2, "value": 2}, "panel_h": 0},
	 {"name": "php", "kind": "osd", "osd_bits": null, "panel_h": 1},
	 {"name": "pho", "kind": "osd", "osd_bits": {"lsb": 2, "width": 2, "value": 1}, "panel_h": 0}]
	EOF
	$SCP "$OUT/sequence-primary.json" "root@$BOARD:$R/sequence-primary.json" || exit 1
}

check_primary_gates(){
	local bad=0 sel ctrl src lay
	sel=$($SSH 'busybox devmem 0x051c006c' 2>/dev/null)
	ctrl=$($SSH 'busybox devmem 0x05600140' 2>/dev/null)
	src=$($SSH 'busybox devmem 0x05600178' 2>/dev/null)
	lay=$($SSH 'cat /tmp/letterbox-card.layout 2>/dev/null' | awk '$1=="osd_src"{print $2}')
	[ "$sel" = "0x29000000" ] || { say "  GATE FAIL selector $sel (want 0x29000000 = RGB)"; bad=1; }
	[ "$ctrl" = "0x03001901" ] || { say "  GATE FAIL OSD ctrl $ctrl (want 0x03001901)"; bad=1; }
	[ -n "$lay" ] || { say "  GATE FAIL no primary layout (card not up)"; bad=1; }
	[ "$(printf '%s' "$src" | tr 'A-F' 'a-f')" = "$(printf '%s' "$lay" | tr 'A-F' 'a-f')" ] ||
		{ say "  GATE FAIL OSD source $src is not the card's ($lay)"; bad=1; }
	return $bad
}

bring_primary(){
	say "== primary (RGB) card up =="
	$SSH "p=\$(cat /tmp/letterbox-card.pid 2>/dev/null); [ -n \"\$p\" ] && kill -TERM \"\$p\" 2>/dev/null
	      pkill -x letterbox-card >/dev/null 2>&1; sleep 1; rm -f /tmp/letterbox-card.pid
	      setsid env ARMED=yes $R/letterbox-card --primary $DWELL_S >/tmp/letterbox-card.log 2>&1 < /dev/null &
	      echo \$! > /tmp/letterbox-card.pid" >/dev/null 2>&1
	sleep 2
	$SSH 'cat /tmp/letterbox-card.log'
	check_primary_gates || { say "REFUSING: the primary card is not demonstrably on the panel."; return 1; }
	say "  primary gates OK"
}

bring_card(){
	say "== control card up =="
	$SSH "p=\$(cat /tmp/letterbox-card.pid 2>/dev/null); [ -n \"\$p\" ] && kill -TERM \"\$p\" 2>/dev/null
	      pkill -x letterbox-card >/dev/null 2>&1; sleep 1; rm -f /tmp/letterbox-card.pid
	      setsid env ARMED=yes $R/letterbox-card $DWELL_S >/tmp/letterbox-card.log 2>&1 < /dev/null &
	      echo \$! > /tmp/letterbox-card.pid" >/dev/null 2>&1
	sleep 2
	$SSH 'cat /tmp/letterbox-card.log'
	check_gates || { say "REFUSING: the control card is not demonstrably on the panel."; return 1; }
	say "  gates OK"
	$SSH "python3 $R/letterbox-baseline.py" > "$FRESH" || { say "baseline failed"; return 1; }
	say "  fresh baseline: $FRESH ($(wc -l < "$FRESH") words)"
	python3 "$HERE/letterbox-recipe.py" --live "$FRESH" --self-test \
		$([ -d "$STOCK" ] && printf -- '--stock %s' "$STOCK") || return 1
	# Every register the recipe touches must read what the reference did.
	python3 "$HERE/letterbox-recipe.py" --live "$FRESH" 852x480 214,120 \
		--pitch 864 --json "$OUT/touched.json" > /dev/null || return 1
	python3 - "$OUT/touched.json" "$REF" "$FRESH" <<-'EOF' || return 1
	import json, sys
	regs = json.load(open(sys.argv[1]))["regs"]
	def load(p):
	    return {int(l.split()[1], 16): l.split()[2] for l in open(p)}
	ref, fresh = load(sys.argv[2]), load(sys.argv[3])
	bad = [(r["addr"], ref.get(r["addr"]), fresh.get(r["addr"])) for r in regs
	       if ref.get(r["addr"]) != fresh.get(r["addr"])]
	for a, x, y in bad:
	    print(f"  DRIFT {a:#010x} reference {x} now {y}")
	print(f"  {len(regs) - len(bad)}/{len(regs)} recipe registers match the reference baseline")
	sys.exit(1 if bad else 0)
	EOF
}


mkdir -p "$OUT"
case "${1:-}" in
prep)
	$SSH "mkdir -p $R" || exit 1
	$SCP "$HERE/letterbox-card.c" "$HERE/letterbox-apply.py" \
	     "$HERE/letterbox-baseline.py" "root@$BOARD:$R/" || exit 1
	$SSH "cd $R && cc -O2 -Wall -o letterbox-card letterbox-card.c \$(pkg-config --cflags --libs libdrm)" ||
		{ say "build failed"; exit 1; }
	$SSH "python3 -m py_compile $R/letterbox-apply.py $R/letterbox-baseline.py" || exit 1
	say "tools in $BOARD:$R, letterbox-card built"
	;;

card)
	bring_card || exit 1
	say "  control card up; film each step handheld (see the header)"
	;;

card-primary)
	bring_primary || exit 1
	say "  primary card up; 'off' puts the console back"
	;;

plan)
	if [ "${2:-}" = mirror ]; then
		bring_card || exit 1
		sequence_json "$SEQUENCE_MV"
		$SSH "python3 $R/letterbox-apply.py --sequence $R/sequence.json --dry-run" |
			grep -E 'step |preflight|REFUSED|SEQUENCE|dry run|V-mirror|panel|ctl'
		osd_sequence_json
		bring_primary || exit 1
		$SSH "python3 $R/letterbox-apply.py --sequence $R/sequence-primary.json --dry-run" |
			grep -E 'step |preflight|REFUSED|SEQUENCE|dry run|would write'
		"$0" off
		exit 0
	fi
	if [ "${2:-}" = bisect ]; then
		bisect_json
		check_gates || { say "REFUSING: gates are not satisfied. Run 'card' first."; exit 1; }
		$SSH "python3 $R/letterbox-apply.py --sequence $R/sequence-bisect.json --dry-run" |
			grep -E 'step |preflight|REFUSED|SEQUENCE|dry run|BISECT'
		exit 0
	fi
	if [ "${2:-}" = all ] || [ "${2:-}" = phase3 ] || [ "${2:-}" = phase3b ]; then
		case $2 in
		phase3)  sequence_json "$SEQUENCE_P3" ;;
		phase3b) sequence_json "$SEQUENCE_P3B" ;;
		*)       sequence_json ;;
		esac
		check_gates || { say "REFUSING: gates are not satisfied. Run 'card' first."; exit 1; }
		$SSH "python3 $R/letterbox-apply.py --sequence $R/sequence.json --dry-run" |
			grep -E 'step |preflight|REFUSED|SEQUENCE|dry run'
		exit 0
	fi
	recipe_json "${2:-}"
	check_gates || { say "REFUSING: gates are not satisfied. Run 'card' first."; exit 1; }
	$SSH "python3 $R/letterbox-apply.py --recipe $R/step-$2.json --region $REGION --dry-run"
	;;

step)
	recipe_json "${2:-}"
	check_gates || { say "REFUSING: gates are not satisfied. Run 'card' first."; exit 1; }
	say "== step $2: $SIZE${OUTSZ:+ -> $OUTSZ} at ($AT) stride $PITCH; window opens in ${PRE_S}s, holds ${HOLD_S}s =="
	$SSH "rm -f /tmp/letterbox-apply.log /tmp/letterbox-apply.pid
	      setsid python3 $R/letterbox-apply.py --recipe $R/step-$2.json --region $REGION \
	          --pre $PRE_S --hold $HOLD_S > /tmp/letterbox-apply.log 2>&1 < /dev/null &
	      echo \$! > /tmp/letterbox-apply.pid" >/dev/null 2>&1
	# Follow by pid, not pgrep -f (the waiter would match itself).
	follow $(( PRE_S + HOLD_S + 60 ))
	$SSH 'cat /tmp/letterbox-apply.log' | tee "$OUT/step-$2.log"
	if grep -q '^.*RESTORED' "$OUT/step-$2.log"; then
		check_gates && say "  native card back on the plane"
		say "  measure: tools/display/letterbox-measure.py VIDEO $2=$SIZE@$AT --out $OUT/step-$2"
	elif grep -q 'nothing was written' "$OUT/step-$2.log"; then
		say "  refused before writing; the board is untouched"
	else
		say "*** NOT RESTORED -- run: letterbox-test.sh restore"
		exit 1
	fi
	;;

all|bisect|phase3|phase3b)
	mode=$1
	bring_card || exit 1
	if [ "$mode" = bisect ]; then
		say "== bisect: step b x5 variants, one go =="
		bisect_json; seqfile=$R/sequence-bisect.json; n=5
	elif [ "$mode" = phase3 ]; then
		say "== phase 3, one go: $SEQUENCE_P3 =="
		sequence_json "$SEQUENCE_P3"; seqfile=$R/sequence.json; n=7
	elif [ "$mode" = phase3b ]; then
		say "== phase 3 bisect, one go: $SEQUENCE_P3B =="
		sequence_json "$SEQUENCE_P3B"; seqfile=$R/sequence.json; n=7
	else
		say "== all steps, one go: $SEQUENCE =="
		sequence_json; seqfile=$R/sequence.json; n=4
	fi
	check_gates || { say "REFUSING: gates are not satisfied."; exit 1; }
	total=$(( LEAD_S + n * HOLD_S + (n - 1) * GAP_S ))
	say "== launching: first window in ${LEAD_S}s, about ${total}s in all; the console returns at the end =="
	$SSH "rm -f /tmp/letterbox-apply.log /tmp/letterbox-apply.pid
	      setsid python3 $R/letterbox-apply.py --sequence $seqfile \
	          --pre $LEAD_S --gap $GAP_S --hold $HOLD_S > /tmp/letterbox-apply.log 2>&1 < /dev/null &
	      echo \$! > /tmp/letterbox-apply.pid" >/dev/null 2>&1
	follow $(( total + 120 ))
	log=$OUT/$mode.log
	$SSH 'cat /tmp/letterbox-apply.log' > "$log"
	grep -E 'step |REFUSED|WINDOW|RECHECK|RESTORE|SEQUENCE|\*\*\*' "$log"
	say "  full log: $log"
	if grep -q 'RESTORE INCOMPLETE' "$log"; then
		say "*** NOT RESTORED -- plane left as is. Run: letterbox-test.sh restore"
		exit 1
	fi
	sleep "$TAIL_S"
	$SSH "p=\$(cat /tmp/letterbox-card.pid 2>/dev/null); [ -n \"\$p\" ] && kill -TERM \"\$p\" 2>/dev/null
	      rm -f /tmp/letterbox-card.pid" >/dev/null 2>&1
	say "  plane released (console back = stop recording)"
	grep -q 'SEQUENCE COMPLETE' "$log" || { say "*** sequence did not complete -- see the log"; exit 1; }
	say "  measure: tools/display/letterbox-measure.py VIDEO --out $OUT/measure"
	;;

mirror)
	bring_card || exit 1
	sequence_json "$SEQUENCE_MV"
	osd_sequence_json
	check_gates || { say "REFUSING: gates are not satisfied."; exit 1; }
	nv=6; np=3
	total=$(( LEAD_S + (nv + np) * HOLD_S + (nv + np - 1) * GAP_S + 5 ))
	# ONE detached job on the board: video half, holder switch, primary half.
	# The primary half runs only if the video half completed and restored.
	cat > "$OUT/mirror-run.sh" <<-EOF
	#!/bin/sh
	python3 $R/letterbox-apply.py --sequence $R/sequence.json --pre $LEAD_S --gap $GAP_S --hold $HOLD_S || exit \$?
	p=\$(cat /tmp/letterbox-card.pid 2>/dev/null); [ -n "\$p" ] && kill -TERM "\$p" 2>/dev/null
	sleep 2
	setsid env ARMED=yes $R/letterbox-card --primary $DWELL_S >/tmp/letterbox-card.log 2>&1 < /dev/null &
	echo \$! > /tmp/letterbox-card.pid
	sleep 2
	cat /tmp/letterbox-card.log
	python3 $R/letterbox-apply.py --sequence $R/sequence-primary.json --pre $GAP_S --gap $GAP_S --hold $HOLD_S
	EOF
	$SCP "$OUT/mirror-run.sh" "root@$BOARD:$R/mirror-run.sh" || exit 1
	say "== mirror, one go: $SEQUENCE_MV | holder switch | $SEQUENCE_MP; first window in ${LEAD_S}s, about ${total}s in all; the console returns at the end =="
	$SSH "rm -f /tmp/letterbox-apply.log /tmp/letterbox-apply.pid
	      setsid sh $R/mirror-run.sh > /tmp/letterbox-apply.log 2>&1 < /dev/null &
	      echo \$! > /tmp/letterbox-apply.pid" >/dev/null 2>&1
	follow $(( total + 120 ))
	log=$OUT/mirror.log
	$SSH 'cat /tmp/letterbox-apply.log' > "$log"
	grep -E 'step |REFUSED|WINDOW|RECHECK|RESTORE|SEQUENCE|WATCH|OSD ctrl|\*\*\*' "$log"
	say "  full log: $log"
	if grep -q 'RESTORE INCOMPLETE' "$log"; then
		say "*** NOT RESTORED -- holder left as is. Run: letterbox-test.sh restore"
		exit 1
	fi
	sleep "$TAIL_S"
	"$0" off >/dev/null
	say "  plane released (console back = stop recording)"
	[ "$(grep -c 'SEQUENCE COMPLETE' "$log")" -eq 2 ] ||
		{ say "*** a sequence did not complete -- see the log"; exit 1; }
	say "  measure: tools/display/letterbox-measure.py VIDEO --mirror --out $OUT/measure"
	;;

show)
	recipe_json "${2:-}"
	$SSH "python3 $R/letterbox-apply.py --show $R/step-$2.json"
	;;

restore)
	$SSH "python3 $R/letterbox-apply.py --restore /tmp/letterbox-saved.json" | tee -a "$OUT/restore.log"
	;;

off)
	$SSH "p=\$(cat /tmp/letterbox-card.pid 2>/dev/null); [ -n \"\$p\" ] && kill -TERM \"\$p\" 2>/dev/null
	      pkill -x letterbox-card >/dev/null 2>&1; rm -f /tmp/letterbox-card.pid" >/dev/null 2>&1
	sleep 1
	$SSH 'tail -2 /tmp/letterbox-card.log'
	say "plane released"
	;;

*)
	sed -n '2,/^set -uo/p' "$0" | sed '$d; s/^# \{0,1\}//'
	exit 2
	;;
esac
