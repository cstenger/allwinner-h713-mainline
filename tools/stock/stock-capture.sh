#!/system/bin/sh
# Capture register and interrupt state on STOCK Android, over adb, with no
# root. RUNS ON THE TARGET under the vendor stack, from /data/local/tmp/cap.
#
# Built for the 2026-09-29 vendor session, which asks four questions no other
# instrument can answer, because each needs the vendor driving the hardware:
#
#   AV1   Which CCU bits does stock set while it hardware-decodes AV1? Our CCU
#         lacks the "av1" module clock, and a gated sunxi CCU register reads
#         zero, so it cannot be found on our stack by reading. With stock
#         playing, it is running. Also: the AV1 block's live registers, and
#         its core ID (low 16 bits vs 0xb16c picks the register-file variant).
#   VP9   Does stock decode VP9 on the Google block, a Hantro path, or in
#         software? The H6 Hantro VP9 block is absent from the H713 CCU, but
#         the Google block's control classes are named VP9DecEControl.
#   HDMI  Which interrupt ticks per captured frame? Found from /proc/interrupts
#         deltas -- NOT by reading capture-domain registers, which have locked
#         this board (docs/hdmi-production-roadmap.md, gate 2).
#   IR    Which keylayout does stock bind to the receiver, i.e. which NEC
#         address our remote uses, and does the bench board have a receiver?
#
# SAFETY. A read of an unpowered block has wedged this SoC before (0x06940000,
# 0x07091000). The AV1 and VE blocks are therefore read ONLY when all three of
# these hold at the moment of the read, and the script records which one
# failed otherwise:
#
#   PPU status of the domain has bits[17:16] = 01 (powered)
#     -- decode validated against genpd on our stack, 2026-09-29
#   its CCU bus-clock gate is set
#   its CCU reset is deasserted
#
# Never add 0x069xxxxx or 0x0709xxxx to anything here.
#
# Added for the 2026-10-01 scaling/letterbox/rotation session
# (docs/vendor-capture-plan.md):
#
#   DISPLAY  The display windows read safely under stock on 2026-08-31
#            (docs/reference/stock-firmware-blocks-4sample-2026-08-31.txt),
#            plus the panel block 0x051c0000. That block is exactly 1 KiB:
#            sized on our Linux 2026-10-01, everything from +0x400 reads zero.
#            Always on while the panel is lit, so not gated.
#   ELOG     The MIPS firmware's DRAM log, raw, for tools/mips/elog-parse.py
#            on the host. Only populated when the display_cfg.xml the vendor
#            loaded has elog mode 2 (buf) -- "fw" proves which one it got.
#   FW       Which display.bin and display_cfg.xml the running firmware holds,
#            read back from DRAM (it copies its cfg to 0x4be01000).
#
#   usage:  stock-capture.sh snap    <label>        registers + interrupts + CPU
#           stock-capture.sh display <label>        display blocks + VideoInfo
#           stock-capture.sh elog    <label>        MIPS elog buffer, raw (2 MiB)
#           stock-capture.sh fw      <label>        firmware text + loaded cfg, raw
#           stock-capture.sh play    <label> [sec]  snap+display+elog, irq window,
#                                                   snap+display+elog again
#           stock-capture.sh logs    <label>        logcat and codec state
#           stock-capture.sh ir      <label> <sec>  input binding + key events
#           stock-capture.sh irq     <label> <sec>  two interrupt snapshots <sec> apart

T=${T:-/data/local/tmp/cap}
R=$T/hidtvreg-read
RAW=$T/hidtvreg-raw
OUT=$T/out

# The display windows. Each is one page, which is all hidtvreg-read reads per
# call. Never add 0x069xxxxx or 0x0709xxxx here.
DISPLAY_BLOCKS="05000000:400 05040000:400 050c0000:400 05140000:400 05180000:400 051c0000:100 05600000:80"
AFBD_VIDEOINFO="05600098 0560009c 056000a0 056000a4"	# per-slot VideoInfo pointers
ELOG_BASE=4b270000 ELOG_BYTES=200000
CFG_BASE=4be01000 CFG_BYTES=2000	# display_cfg.xml as the firmware received it
FW_TEXT=4b110000 FW_BYTES=10000		# = display.bin[0x10000:0x20000], 1:1 from 0x4b100000

CCU_VE_BGR=0200169c	# bit0 bus_ve  bit1 bus_av1  bit2 bus_ve3; resets bit16+
CCU_MBUS=02001804	# bit4 mbus_av1
PPU=07001000		# status for domain d at +0x24 + d*0x80

die() { echo "stock-capture: $*" >&2; exit 1; }
[ -x "$R" ] || die "missing $R -- adb push hidtvreg-read first"

# One register, as a decimal number. hidtvreg-read prints "aaaaaaaa 0xVVVVVVVV".
reg() {
	set -- $($R "$1" 1 2>/dev/null)
	case "$2" in
	0x*) printf '%d\n' "$2" ;;	# printf, not $((16#..)): portable to any sh
	*) echo -1 ;;
	esac
}

bit() { [ "$1" -ge 0 ] && [ $(( ($1 >> $2) & 1 )) -eq 1 ]; }

ppu_on() {  # domain index
	base=$(printf '%d' "0x$PPU")
	s=$(reg "$(printf '%08x' $((base + 36 + $1 * 128)))")	# +0x24 + d*0x80
	[ "$s" -ge 0 ] && [ $(( (s >> 16) & 3 )) -eq 1 ]
}

# gated_read <name> <domain> <gate-bit> <reset-bit> <address> <words> <dir>
gated_read() {
	name=$1 dom=$2 gbit=$3 rbit=$4 addr=$5 words=$6 dir=$7
	bgr=$(reg $CCU_VE_BGR)
	if ! ppu_on "$dom"; then
		echo "SKIPPED $name: PPU domain $dom not powered" > "$dir/$name.txt"
	elif ! bit "$bgr" "$gbit"; then
		echo "SKIPPED $name: bus gate bit $gbit clear (bgr=$bgr)" > "$dir/$name.txt"
	elif ! bit "$bgr" "$rbit"; then
		echo "SKIPPED $name: reset bit $rbit asserted (bgr=$bgr)" > "$dir/$name.txt"
	else
		$R "$addr" "$words" > "$dir/$name.txt" 2>&1
	fi
}

cmd_snap() {
	d=$OUT/$1; mkdir -p "$d" || die "cannot create $d"
	cat /proc/uptime > "$d/uptime"
	cat /proc/interrupts > "$d/interrupts"
	# Always-on blocks, safe at any time: the whole CCU page, and the PPU.
	$R 02001000 400 > "$d/ccu.txt" 2>&1
	$R $PPU 100 > "$d/ppu.txt" 2>&1
	# Gated blocks. AV1 is PPU domain 4 (bus bit 1, reset bit 17); the VE is
	# domain 3 (bus bit 0, reset bit 16).
	gated_read av1 4 1 17 01c0d000 400 "$d"
	gated_read ve  3 0 16 01c0e000 400 "$d"
	top -b -n 1 -m 12 > "$d/top.txt" 2>&1
	echo "snap $1: $(grep -c . "$d/ccu.txt") CCU words; av1: $(head -c 60 "$d/av1.txt")"
}

cmd_display() {
	label=$1	# the loop below reuses the positional parameters
	d=$OUT/$label; mkdir -p "$d" || die "cannot create $d"
	cat /proc/uptime > "$d/uptime-display"
	: > "$d/display.txt"
	for b in $DISPLAY_BLOCKS; do
		$R "${b%%:*}" "${b##*:}" >> "$d/display.txt" 2>&1
	done
	# VideoInfo descriptors: follow each slot pointer, but only into DRAM
	# (0x40000000-0x7fffffff), and each distinct pointer once. Range-checked
	# on the hex digits, not arithmetically: mksh integers are 32-bit signed,
	# so 0x80000000 is negative there.
	: > "$d/videoinfo.txt"
	seen=
	for p in $AFBD_VIDEOINFO; do
		set -- $($R "$p" 1 2>/dev/null)
		a=$(echo "${2#0x}" | tr 'A-F' 'a-f')
		case "$a" in [4-7][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ;; *) continue ;; esac
		case " $seen " in *" $a "*) continue ;; esac
		seen="$seen $a"
		echo "== $p -> $a" >> "$d/videoinfo.txt"
		$R "$a" 48 >> "$d/videoinfo.txt" 2>&1
	done
	echo "display $label: $(grep -c '^0' "$d/display.txt") words; AFBD src $(grep '^05600030' "$d/display.txt"); videoinfo ->$seen"
}

cmd_elog() {
	d=$OUT/$1; mkdir -p "$d" || die "cannot create $d"
	[ -x "$RAW" ] || die "missing $RAW -- adb push hidtvreg-raw first"
	cat /proc/uptime > "$d/uptime-elog"
	$RAW $ELOG_BASE $ELOG_BYTES > "$d/elog.bin" || echo "elog $1: hidtvreg-raw FAILED"
	echo "elog $1: $(wc -c < "$d/elog.bin") bytes"
}

cmd_fw() {
	d=$OUT/$1; mkdir -p "$d" || die "cannot create $d"
	[ -x "$RAW" ] || die "missing $RAW -- adb push hidtvreg-raw first"
	$RAW $CFG_BASE $CFG_BYTES > "$d/cfg.bin"
	$RAW $FW_TEXT $FW_BYTES > "$d/fw-text.bin"
	# The two lines that decide whether there is an elog at all.
	echo "fw $1: loaded cfg says: $(tr -d '\000' < "$d/cfg.bin" | grep -E "<(mode|level) val" | tr -s ' ' | tr '\n' ' ')"
}

# One playback state: two full samples separated by the interrupt window, so
# "what moves per frame" and "which interrupt ticks" come from the same 5 s.
cmd_play() {
	cmd_snap "$1-1" && cmd_display "$1-1" && cmd_elog "$1-1"
	cmd_irq "$1-irq" "${2:-5}"
	cmd_snap "$1-2" && cmd_display "$1-2" && cmd_elog "$1-2"
}

cmd_logs() {
	d=$OUT/$1; mkdir -p "$d" || die "cannot create $d"
	logcat -d > "$d/logcat-full.txt" 2>&1
	grep -iE "omx|cedar|av1|vp9|awvp9|awav1|vdecoder|MediaCodec|ACodec|hwdec|soft" \
		"$d/logcat-full.txt" > "$d/logcat-codec.txt"
	dumpsys media.player > "$d/dumpsys-media-player.txt" 2>&1
	echo "logs $1: $(wc -l < "$d/logcat-codec.txt") codec-related lines"
}

cmd_irq() {
	d=$OUT/$1; mkdir -p "$d" || die "cannot create $d"
	cat /proc/uptime > "$d/uptime-a"; cat /proc/interrupts > "$d/interrupts-a"
	sleep "${2:-5}"
	cat /proc/uptime > "$d/uptime-b"; cat /proc/interrupts > "$d/interrupts-b"
	echo "irq $1: two snapshots ${2:-5} s apart"
}

cmd_ir() {
	d=$OUT/$1; mkdir -p "$d" || die "cannot create $d"
	dumpsys input > "$d/dumpsys-input.txt" 2>&1
	getevent -p > "$d/getevent-devices.txt" 2>&1
	echo "press remote keys now, for ${2:-20} s"
	timeout "${2:-20}" getevent -lt > "$d/getevent-keys.txt" 2>&1
	echo "ir $1: $(grep -c EV_KEY "$d/getevent-keys.txt") key events"
}

case "$1" in
snap)    cmd_snap "${2:?label}" ;;
display) cmd_display "${2:?label}" ;;
elog)    cmd_elog "${2:?label}" ;;
fw)      cmd_fw "${2:?label}" ;;
play)    cmd_play "${2:?label}" "$3" ;;
logs)    cmd_logs "${2:?label}" ;;
irq)     cmd_irq "${2:?label}" "$3" ;;
ir)      cmd_ir "${2:?label}" "$3" ;;
*) sed -n '2,62p' "$0"; exit 2 ;;
esac
