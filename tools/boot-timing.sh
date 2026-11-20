#!/usr/bin/env bash
# Time repeated reboots of a board over its UART (root-filesystem comparison,
# docs/lpddr3-bringup-plan.md Phase 4 stage 2).
#
#   LOG=uart.log tools/boot-timing.sh LABEL [N]
#
# The board must be at a root shell on the UART, and a UART logger
# (tools/serial/soak-capture.py) must be writing LOG with its "[HH:MM:SS T+ s]"
# prefixes. Each round sends `systemctl reboot`, waits for the autologin, then
# asks for the root filesystem type and `systemd-analyze`. Round 0 is a
# warm-up (first boot after an image change does one-time work) and is
# recorded but marked. N measured rounds follow (default 5).
#
# Per round, from the logger's clock: U-Boot banner -> "Starting kernel",
# U-Boot banner -> autologin, and systemd's kernel / userspace / total. Results
# go to local/recovery/boot-timing/LABEL.csv, with a summary (mean, min, max of
# the measured rounds) at the end.
set -uo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
label=${1:?LABEL}; n=${2:-5}
tty=${TTY:-/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0}
log=${LOG:?LOG=the UART logger output}
out="$ROOT/local/recovery/boot-timing"; mkdir -p "$out"
csv="$out/$label.csv"
say() { printf '[boot-timing %s] %s\n' "$label" "$*" >&2; }
send() { printf '%s\n' "$1" > "$tty"; }
since() { tail -c +"$(($1 + 1))" "$log" | tr '\r' '\n'; }
tplus() { sed -n 's/^\[[0-9:]* T+ *\([0-9.]*\)\].*/\1/p' | head -1; }

[ -e "$tty" ] || { say "no UART $tty"; exit 1; }
[ -f "$log" ] || { say "no logger output $log"; exit 1; }
echo "label,round,warmup,rootfs,uboot_to_kernel_s,uboot_to_login_s,kernel_s,userspace_s,total_s" > "$csv"

for r in $(seq 0 "$n"); do
	n0=$(stat -c %s "$log")
	send "systemctl reboot"
	ok=
	for _ in $(seq 1 240); do
		sleep 0.5
		if since "$n0" | grep -aq 'login: root (automatic login)'; then ok=1; break; fi
	done
	[ -n "$ok" ] || { say "round $r: no autologin within 120 s"; exit 1; }
	sleep 3
	res=
	for _ in $(seq 1 30); do
		n1=$(stat -c %s "$log")
		send 'echo BT $(findmnt -no FSTYPE /) $(systemd-analyze 2>&1 | head -1)'
		sleep 2
		res=$(since "$n1" | grep -a '^\[.*\] BT .*Startup finished' | head -1)
		[ -n "$res" ] && break
		sleep 2
	done
	[ -n "$res" ] || { say "round $r: systemd-analyze never reported a finished boot"; exit 1; }
	text=$(since "$n0")
	t_ub=$(grep -a 'U-Boot 20' <<<"$text" | tplus)
	t_sk=$(grep -a 'Starting kernel' <<<"$text" | tplus)
	t_li=$(grep -a 'login: root (automatic login)' <<<"$text" | tplus)
	fs=$(sed -n 's/.* BT \([a-z0-9]*\) .*/\1/p' <<<"$res")
	ks=$(sed -n 's/.*in \([0-9.]*\)s (kernel).*/\1/p; s/.*= \([0-9.]*\)s (kernel).*/\1/p' <<<"$res" | head -1)
	[ -n "$ks" ] || ks=$(grep -ao '[0-9.]*s (kernel)' <<<"$res" | grep -o '^[0-9.]*')
	us=$(grep -ao '[0-9.]*s (userspace)' <<<"$res" | grep -o '^[0-9.]*')
	tot=$(grep -ao '= [0-9.]*s' <<<"$res" | grep -o '[0-9.]*')
	u2k=$(awk -v a="$t_ub" -v b="$t_sk" 'BEGIN{ if (a == "" || b == "") print ""; else printf "%.1f", b - a }')
	u2l=$(awk -v a="$t_ub" -v b="$t_li" 'BEGIN{ if (a == "" || b == "") print ""; else printf "%.1f", b - a }')
	warm=$([ "$r" = 0 ] && echo yes || echo no)
	echo "$label,$r,$warm,$fs,$u2k,$u2l,$ks,$us,$tot" >> "$csv"
	say "round $r$([ "$r" = 0 ] && echo ' (warm-up)'): root $fs, U-Boot->kernel ${u2k}s, U-Boot->login ${u2l}s, systemd ${ks}s + ${us}s = ${tot}s"
done

awk -F, 'NR > 1 && $3 == "no" {
	for (i = 5; i <= 9; i++) { s[i] += $i; if (!(i in mn) || $i < mn[i]) mn[i] = $i; if ($i > mx[i]) mx[i] = $i }
	c++; fs = $4 }
END {
	split("U-Boot->kernel,U-Boot->login,kernel,userspace,total", nm, ",")
	printf "%s (%s), %d measured rounds: mean [min..max] s\n", lbl, fs, c
	for (i = 5; i <= 9; i++) printf "  %-15s %6.2f [%.2f..%.2f]\n", nm[i - 4], s[i] / c, mn[i], mx[i]
}' lbl="$label" "$csv" | tee "$out/$label.summary" >&2
