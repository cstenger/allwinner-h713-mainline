#!/usr/bin/env bash
# Does one kind of DDC transaction from the source leave the board's EDID slave
# NAKing? Run with sudo on the source PC while the projector shows the desktop:
#
#   sudo bash tools/hdmi/host-ddc-wedge-probe.sh [BUS]
#
# Only standard HDMI DDC addresses are touched, one at a time. After each probe
# the EDID header at 0x50 is read again; the first probe after which it NAKs is
# the trigger. Stops at the first NAK. Reads only, except one standard E-DDC
# segment-pointer write (0x30 <- 0) as the last step.
set -u
BUS=${1:-1}
edid() { i2cget -y "$BUS" 0x50 0x08 b 2>/dev/null; }   # byte 8: manufacturer ID high byte (0x20 here)
check() {
	local v; v=$(edid)
	printf '%-28s edid[8]=%s\n' "$1" "${v:-NAK}"
	[ "$v" = 0x20 ] || { echo "EDID stopped answering after: $1"; exit 3; }
}
check "baseline"
check "baseline again"
i2cget -y "$BUS" 0x50 >/dev/null 2>&1;         check "0x50 receive-byte (no offset)"
i2cget -y "$BUS" 0x37 >/dev/null 2>&1;         check "0x37 DDC/CI read"
i2cget -y "$BUS" 0x3a 0x40 b >/dev/null 2>&1;  check "0x3a HDCP Bcaps read"
i2cget -y "$BUS" 0x3a 0x00 b >/dev/null 2>&1;  check "0x3a HDCP Bksv read"
i2cget -y "$BUS" 0x54 0x01 b >/dev/null 2>&1;  check "0x54 SCDC sink version read"
i2cget -y "$BUS" 0x30 >/dev/null 2>&1;         check "0x30 segment pointer read"
i2cset -y "$BUS" 0x30 0x00 >/dev/null 2>&1;    check "0x30 segment pointer write 0"
i2cget -y "$BUS" 0x50 0x80 b >/dev/null 2>&1;  check "0x50 offset 0x80 (block 1)"
echo "no probe wedged the EDID slave"
