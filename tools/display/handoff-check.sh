#!/bin/sh
# Does the U-Boot display frame survive into Linux?  Runs ON THE TARGET.
#
# U-Boot brings the panel up, publishes a frame and hands off without tearing
# down. Milestone 2b only ever established that Linux reaches userspace; it
# never checked that the picture is still there, and it passed before any of the
# framebuffer fixes existed. This reads back the registers that would have to
# survive for the image to survive, and says which ones did not.
#
# Expected values are the ones U-Boot printed on the 2026-08-07 project-0x34
# run. They are properties of that configuration, not of this script: if the
# panel config changes, re-take them from the "OSD state after post-quiesce
# re-assert" dump rather than editing them to match whatever is read.
#
# Usage:
#   handoff-check.sh              once
#   handoff-check.sh -w [SECS]    re-read every SECS (default 5) until Ctrl-C,
#                                 reporting only when something changes
#
# Needs /dev/mem. CONFIG_STRICT_DEVMEM permits MMIO and denies RAM, which is
# exactly the access this wants, so it works on the shipping config.

set -u

regs() {
	# addr|expected|what        (pipe-separated: descriptions contain spaces)
	cat <<'EOF'
0x058c0014|b8002300|display PLL, N+1=36 -- the original fault
0x0525c000|02f80550|mixer H/V total, 1360x760
0x0524c000|00fc0202|DE/OSD control
0x0528008c|00000000|layer X origin -- 123 here was the framebuffer fault
0x05280084|02d00500|layer size
0x05600140|03001901|AFBD control
0x05600170|00001400|AFBD stride, 5120 bytes
0x05600178|6c100000|AFBD source address, the front buffer
0x05140054|40000080|display route
0x051c0014|18000005|LVDS PHY
0x051c0028|1f300030|LVDS PHY mid
0x05700000|fff11111|TVTOP
EOF
}

read_reg() {
	# od seeks by byte offset and prints one little-endian word.
	od -An -tx4 -N4 -j "$(printf '%d' "$1")" /dev/mem 2>/dev/null | tr -d ' \n'
}

snapshot() {
	regs | while IFS='|' read -r addr want what; do
		[ -n "$addr" ] || continue
		printf '%s=%s\n' "$addr" "$(read_reg "$addr")"
	done
}

report() {
	bad=0
	unread=0
	total=0
	printf '%-12s %-10s %-10s %s\n' REGISTER EXPECTED READ WHAT
	# A pipe would run the loop in a subshell and lose the counters, so feed
	# it from a here-doc via a temporary instead.
	regs > /tmp/.hc_regs.$$
	while IFS='|' read -r addr want what; do
		[ -n "$addr" ] || continue
		total=$((total + 1))
		got=$(read_reg "$addr")
		if [ -z "$got" ]; then
			got=UNREADABLE
			unread=$((unread + 1))
			mark="?"
		elif [ "$got" = "$want" ]; then
			mark=""
		else
			mark="<-- CHANGED"
			bad=$((bad + 1))
		fi
		printf '%-12s %-10s %-10s %s %s\n' "$addr" "$want" "$got" "$what" "$mark"
	done < /tmp/.hc_regs.$$
	rm -f /tmp/.hc_regs.$$

	echo
	if [ "$unread" -gt 0 ]; then
		echo "$unread of $total unreadable -- /dev/mem denied or absent."
		echo "This says nothing until that is fixed. Do not read the rest as a pass."
		return 2
	fi
	if [ "$bad" -eq 0 ]; then
		echo "All $total registers hold their U-Boot values: the display STATE survived."
		echo "Whether the PICTURE survived is a separate question and only the panel"
		echo "can answer it. Look at it before recording a pass."
	else
		echo "$bad of $total changed since U-Boot."
	fi
	return 0
}

if [ "${1:-}" = "-w" ]; then
	iv=${2:-5}
	echo "watching every ${iv}s; reports only on change. Ctrl-C to stop."
	report
	prev=$(snapshot)
	t=0
	while :; do
		sleep "$iv"
		t=$((t + iv))
		cur=$(snapshot)
		if [ "$cur" != "$prev" ]; then
			echo
			echo "=== CHANGED at t+${t}s after this script started ==="
			report
			prev=$cur
		fi
	done
else
	report
fi
