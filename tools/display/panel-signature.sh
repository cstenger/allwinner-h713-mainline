#!/usr/bin/env bash
# Is there a downstream frame signature? RUNS ON THE HOST. READ-ONLY apart
# from ordinary KMS commits of a card on the primary plane.
#
#   panel-signature.sh                 every variant, then the analysis
#   panel-signature.sh analyse         re-run the analysis on saved samples
#
# For each card variant (letterbox-card --primary, CARD=...): commit it,
# sample comp/route/panel words several times (panel-signature-read.py), and
# release. panel-signature-analyse.py then finds words that are stable within
# a card, differ between cards, and are POSITION-sensitive (upright vs its
# software mirror, upright vs a 1-px shift) -- histograms and brightness
# averages are blind to a mirror, a CRC is not.
set -uo pipefail
BOARD=${BOARD:-192.168.4.1}
SSH="ssh -o ConnectTimeout=20 -o BatchMode=yes root@$BOARD"
SCP="scp -q -o ConnectTimeout=20 -o BatchMode=yes"
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
R=/root/tools/letterbox
OUT=${OUT:-$REPO/local/h713-lab/panel-signature-$(date +%Y%m%d)}
VARIANTS=${VARIANTS:-"upright x y xy shift upright black white grey red green blue upright"}
SAMPLES=${SAMPLES:-8}
mkdir -p "$OUT"

stop_card(){
	$SSH "p=\$(cat /tmp/letterbox-card.pid 2>/dev/null); [ -n \"\$p\" ] && kill -TERM \"\$p\" 2>/dev/null
	      pkill -x letterbox-card >/dev/null 2>&1; rm -f /tmp/letterbox-card.pid" >/dev/null 2>&1
	sleep 1
}

if [ "${1:-}" != analyse ]; then
	$SCP "$HERE/letterbox-card.c" "$HERE/panel-signature-read.py" "root@$BOARD:$R/" || exit 1
	$SSH "cd $R && cc -O2 -Wall -o letterbox-card letterbox-card.c \$(pkg-config --cflags --libs libdrm)" || exit 1
	i=0
	for v in $VARIANTS; do
		i=$((i + 1))
		stop_card
		$SSH "setsid env ARMED=yes CARD=$v $R/letterbox-card --primary 600 >/tmp/letterbox-card.log 2>&1 < /dev/null &
		      echo \$! > /tmp/letterbox-card.pid" >/dev/null 2>&1
		sleep 2
		sel=$($SSH 'busybox devmem 0x051c006c')
		lay=$($SSH 'cat /tmp/letterbox-card.layout 2>/dev/null' | awk '$1=="osd_src"{print $2}')
		src=$($SSH 'busybox devmem 0x05600178')
		if [ "$sel" != 0x29000000 ] || [ -z "$lay" ] ||
		   [ "$(printf %s "$src" | tr A-F a-f)" != "$(printf %s "$lay" | tr A-F a-f)" ]; then
			echo "variant $v: card not demonstrably on the panel (selector $sel, src $src, layout $lay)"
			stop_card; exit 1
		fi
		$SSH "python3 $R/panel-signature-read.py --samples $SAMPLES" > "$OUT/$(printf %02d $i)-$v.json" || exit 1
		echo "variant $v: $(wc -c < "$OUT/$(printf %02d $i)-$v.json") bytes"
	done
	stop_card
	$SSH 'tail -1 /tmp/letterbox-card.log'
fi
python3 "$HERE/panel-signature-analyse.py" "$OUT"
