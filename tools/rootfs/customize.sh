#!/bin/sh
# Customize an extracted Debian rootfs without executing target binaries.
# Usage: customize.sh ROOTFS SSH_PUBLIC_KEY_FILE DEBIAN_MIRROR DEBIAN_SUITE
set -eu

R=$1
SSH_KEY=$2
DEBIAN_MIRROR=$3
DEBIAN_SUITE=$4

[ -d "$R/etc" ] || { echo "error: invalid rootfs: $R" >&2; exit 1; }
[ -s "$SSH_KEY" ] || { echo "error: missing SSH public key: $SSH_KEY" >&2; exit 1; }

printf '%s\n' h713-arm64 > "$R/etc/hostname"
cat > "$R/etc/hosts" <<EOF
127.0.0.1	localhost
127.0.1.1	h713-arm64
EOF

# UDISK is factory GPT partition 26. systemd-growfs expands this deliberately
# small image to the full partition on first boot.
printf '%s\n' \
  '/dev/mmcblk0p26  /  ext4  defaults,noatime,x-systemd.growfs  0  1' \
  > "$R/etc/fstab"

mkdir -p "$R/etc/network"
cat > "$R/etc/network/interfaces" <<EOF
auto lo
iface lo inet loopback
allow-hotplug eth0
iface eth0 inet dhcp
EOF

# Replace mmdebstrap's host-visible bootstrap keyring path with a target-local
# deb822 source. The installed debian-archive-keyring package owns this keyring.
rm -f "$R/etc/apt/sources.list"
install -d -m 0755 "$R/etc/apt/sources.list.d"
cat > "$R/etc/apt/sources.list.d/debian.sources" <<EOF
Types: deb
URIs: $DEBIAN_MIRROR
Suites: $DEBIAN_SUITE
Components: main
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
EOF

# Root has no usable password. SSH permits only the explicitly supplied key;
# the physical serial console remains available through autologin.
shadow_tmp="$R/etc/.shadow.h713"
awk -F: 'BEGIN { OFS=FS } $1 == "root" { $2="!" } { print }' \
  "$R/etc/shadow" > "$shadow_tmp"
cat "$shadow_tmp" > "$R/etc/shadow"
rm -f "$shadow_tmp"

install -d -m 0700 "$R/root/.ssh"
install -m 0600 "$SSH_KEY" "$R/root/.ssh/authorized_keys"

install -d -m 0755 "$R/etc/ssh/sshd_config.d"
cat > "$R/etc/ssh/sshd_config.d/10-h713.conf" <<EOF
PermitRootLogin prohibit-password
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
AuthenticationMethods publickey
X11Forwarding no
EOF

# Never clone host keys or machine identity across images. Generate missing
# host keys before ssh.service on every boot; ssh-keygen -A is idempotent and
# avoids relying on ConditionFirstBoot ordering while /etc/machine-id is being
# initialized.
rm -f "$R"/etc/ssh/ssh_host_*
rm -f "$R/etc/machine-id" "$R/var/lib/dbus/machine-id"
: > "$R/etc/machine-id"
rm -f "$R/var/lib/systemd/random-seed"

systemd_dir="$R/etc/systemd/system"
install -d -m 0755 \
  "$systemd_dir/getty.target.wants" \
  "$systemd_dir/multi-user.target.wants" \
  "$systemd_dir/ssh.service.wants" \
  "$systemd_dir/serial-getty@ttyS0.service.d"
ln -sfn /usr/lib/systemd/system/serial-getty@.service \
  "$systemd_dir/getty.target.wants/serial-getty@ttyS0.service"
ln -sfn /usr/lib/systemd/system/ssh.service \
  "$systemd_dir/multi-user.target.wants/ssh.service"
cat > "$systemd_dir/h713-ssh-host-keys.service" <<EOF
[Unit]
Description=Generate missing SSH host keys
Before=ssh.service

[Service]
Type=oneshot
ExecStart=/usr/bin/ssh-keygen -A
RemainAfterExit=yes
EOF
ln -sfn ../h713-ssh-host-keys.service \
  "$systemd_dir/ssh.service.wants/h713-ssh-host-keys.service"
ln -sfn /dev/null "$systemd_dir/systemd-networkd-wait-online.service"

cat > "$systemd_dir/serial-getty@ttyS0.service.d/autologin.conf" <<EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin root --noclear %I \$TERM
EOF

# Load the AIC8800 WiFi/BT modules at boot. bsp registers the SDIO glue and
# powers the chip; fdrv (WiFi) and btlpm (BT) depend on it, so ordering matters.
install -d -m 0755 "$R/etc/modules-load.d"
cat > "$R/etc/modules-load.d/aic8800.conf" <<EOF
aic8800_bsp
aic8800_fdrv
aic8800_btlpm
EOF

# AIC8800 Bluetooth: attach the HCI UART on ttyS1 (H4, 1.5 Mbaud). Use NO host
# flow control — mainline dw-apb-uart RTS/CTS blocks the controller (HCI cmd
# timeout), whereas 'noflow' works. hciattach returns 0 even when the controller
# is mute, so the loop verifies 'hciconfig hci0 up' and retries, which also
# absorbs the cold-boot timing before the BT firmware is ready on the UART.
install -d -m 0755 "$R/usr/local/sbin"
cat > "$R/usr/local/sbin/h713-bt-attach" <<'EOS'
#!/bin/sh
# Bring up the AIC8800 Bluetooth controller (hci0) on UART1.
rfkill unblock bluetooth 2>/dev/null || true
modprobe hci_uart 2>/dev/null || true
i=0
while [ "$i" -lt 10 ]; do
	i=$((i + 1))
	pkill -x hciattach 2>/dev/null || true
	hciattach /dev/ttyS1 any 1500000 noflow || true
	if hciconfig hci0 up 2>/dev/null && hciconfig hci0 2>/dev/null | grep -q "UP RUNNING"; then
		exit 0
	fi
	sleep 2
done
exit 1
EOS
chmod 0755 "$R/usr/local/sbin/h713-bt-attach"
cat > "$systemd_dir/h713-bt-attach.service" <<EOF
[Unit]
Description=AIC8800 Bluetooth HCI attach (ttyS1, H4, noflow)
After=systemd-modules-load.service
Wants=systemd-modules-load.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/sbin/h713-bt-attach

[Install]
WantedBy=multi-user.target
EOF
ln -sfn ../h713-bt-attach.service \
  "$systemd_dir/multi-user.target.wants/h713-bt-attach.service"

# Optional boot WiFi hotspot (AP). Enabled only when the build passed
# HOTSPOT_ENABLED=1 (i.e. local/hotspot.conf existed). A dedicated AP owns wlan0
# and DHCP, so mask the STA supplicant and the default dnsmasq.
if [ "${HOTSPOT_ENABLED:-0}" = 1 ]; then
  install -d -m 0755 "$R/etc/hostapd"
  cat > "$R/etc/hostapd/hotspot.conf" <<EOF
interface=wlan0
driver=nl80211
ssid=$HOTSPOT_SSID
hw_mode=g
channel=$HOTSPOT_CHANNEL
auth_algs=1
wpa=2
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
wpa_passphrase=$HOTSPOT_PASSPHRASE
EOF
  chmod 0600 "$R/etc/hostapd/hotspot.conf"
  cat > "$R/etc/default/h713-hotspot" <<EOF
HOTSPOT_IP=$HOTSPOT_IP
HOTSPOT_DHCP_START=$HOTSPOT_DHCP_START
HOTSPOT_DHCP_END=$HOTSPOT_DHCP_END
EOF
  install -d -m 0755 "$R/usr/local/sbin"
  cat > "$R/usr/local/sbin/h713-hotspot-up" <<'EOS'
#!/bin/sh
# Bring up the H713 WiFi hotspot (AP) on wlan0: hostapd + a DHCP-only dnsmasq.
CONF=/etc/hostapd/hotspot.conf
[ -f "$CONF" ] || exit 0
HOTSPOT_IP=192.168.4.1; HOTSPOT_DHCP_START=192.168.4.10; HOTSPOT_DHCP_END=192.168.4.100
[ -f /etc/default/h713-hotspot ] && . /etc/default/h713-hotspot
rfkill unblock wifi 2>/dev/null || true
i=0; while [ ! -e /sys/class/net/wlan0 ] && [ "$i" -lt 30 ]; do i=$((i + 1)); sleep 1; done
pkill -x hostapd 2>/dev/null || true
ip link set wlan0 down 2>/dev/null || true
ip addr flush dev wlan0 2>/dev/null || true
hostapd -B "$CONF" || exit 1
ip addr add "${HOTSPOT_IP}/24" dev wlan0
exec dnsmasq --keep-in-foreground --interface=wlan0 --bind-interfaces \
  --except-interface=lo \
  --dhcp-range="${HOTSPOT_DHCP_START},${HOTSPOT_DHCP_END},255.255.255.0,12h" \
  --dhcp-authoritative --port=0
EOS
  chmod 0755 "$R/usr/local/sbin/h713-hotspot-up"
  cat > "$systemd_dir/h713-hotspot.service" <<EOF
[Unit]
Description=H713 WiFi hotspot (hostapd + dnsmasq on wlan0)
After=systemd-modules-load.service
Wants=systemd-modules-load.service

[Service]
Type=simple
ExecStart=/usr/local/sbin/h713-hotspot-up
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
  ln -sfn ../h713-hotspot.service \
    "$systemd_dir/multi-user.target.wants/h713-hotspot.service"
  ln -sfn /dev/null "$systemd_dir/wpa_supplicant.service"
  ln -sfn /dev/null "$systemd_dir/dnsmasq.service"
  echo "[customize] boot hotspot enabled: SSID=$HOTSPOT_SSID ch=$HOTSPOT_CHANNEL ip=$HOTSPOT_IP"
fi

echo "[customize] configured key-only SSH, ttyS0 autologin, AIC8800 autoload + BT attach"
