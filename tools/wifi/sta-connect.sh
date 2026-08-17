#!/bin/bash
# Put the board on a real network as a STATION, instead of being an AP.
# RUNS ON THE TARGET.
#
# The image bakes in a boot hotspot (hostapd + dnsmasq own wlan0, and the STA
# wpa_supplicant unit is masked so they cannot fight over it), which is right
# for a projector and wrong for bring-up: a serial console moves files at
# 10.8 KB/s, and an ssh session moves them at wire speed. This script trades
# one for the other until the next reboot, which restores the hotspot.
#
# It runs the supplicant as a bare process rather than via systemd on purpose —
# the unit is masked in this image, and unmasking it would outlive the session.
#
#   usage: ./sta-connect.sh SSID PASSPHRASE [interface]
#
# ⚠ Sustained transfers over this link have wedged the board hard enough to
# take the serial console with them (2026-08-16, during an `apt-get update`).
# Keep the serial console attached and logging while you use it, and do not
# put anything on the WiFi path that you cannot afford to restart.

set -eu

SSID=${1:?usage: sta-connect.sh SSID PASSPHRASE [interface]}
PSK=${2:?usage: sta-connect.sh SSID PASSPHRASE [interface]}
IFACE=${3:-wlan0}
CONF=/etc/wpa_supplicant/wpa-sta-$IFACE.conf

echo "==> stopping the boot hotspot"
systemctl stop h713-hotspot.service 2>/dev/null || true
pkill -x hostapd 2>/dev/null || true
pkill -x dnsmasq 2>/dev/null || true
pkill -f "wpa_supplicant.*$IFACE" 2>/dev/null || true
sleep 1

echo "==> $IFACE: AP -> managed"
ip link set "$IFACE" down
iw dev "$IFACE" set type managed
ip link set "$IFACE" up

# The hotspot's address is still on the interface at this point and will
# happily coexist with the DHCP lease, quietly adding a second subnet to every
# routing decision. Drop it.
ip -4 addr flush dev "$IFACE"

echo "==> associating with $SSID"
umask 077
# wpa_passphrase emits the plaintext as a #psk= comment; strip it so the
# credential exists on disk only in its hashed form.
wpa_passphrase "$SSID" "$PSK" | grep -v '#psk' > "$CONF"
wpa_supplicant -B -i "$IFACE" -c "$CONF" -f /var/log/wpa-sta.log

for i in $(seq 20); do
  sleep 1
  iw dev "$IFACE" link 2>/dev/null | grep -q "^Connected" && break
done
iw dev "$IFACE" link | head -3

echo "==> DHCP"
dhclient -1 "$IFACE"
ip -br addr show "$IFACE"
ip route | head -3
