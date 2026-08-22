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

# Quiet the WiFi driver for production. aic8800_fdrv's aicwf_dbg_level defaults
# to LOGERROR|LOGINFO|LOGDEBUG|LOGTRACE|LOGFW (0x40F); the DEBUG/TRACE bits flood
# the serial console under load (per-command rwnx_send_msg / rwnx_fill_station_info
# spam). Keep errors only. Flags (aicwf_debug.h): ERROR=0x1 INFO=0x2 TRACE=0x4
# DEBUG=0x8 FW=0x400. It stays a live knob: raise it for debugging via
# echo N > /sys/module/aic8800_fdrv/parameters/aicwf_dbg_level  and read it back
# from `journalctl -k` (kernel log), not the console (e.g. 0x403 adds firmware logs).
install -d -m 0755 "$R/etc/modprobe.d"
cat > "$R/etc/modprobe.d/aic8800.conf" <<EOF
options aic8800_fdrv aicwf_dbg_level=0x1
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

# AIC8800 WiFi firmware-crash notifier (log only -- no auto-recovery). Under
# heavy load the vendor fdrv can time out on its firmware command handshake
# ("cmd timed-out / wlan error reset flow"), mark its cmd queue CRASHED, and
# fire a KOBJ_CHANGE uevent with DHDISDOWN=1. There is NO safe in-place
# recovery: unbinding+reloading the SDIO stack races the mmc/driver core into a
# NULL-deref Oops (bench-observed), and the chip only comes back cleanly on a
# full boot. So this handler just records the fault clearly (journal + console);
# WiFi and BT (same combo chip) stay down until the operator reboots the device.
install -d -m 0755 "$R/usr/local/sbin"
cat > "$R/usr/local/sbin/h713-wifi-crashlog" <<'WIFICRASHLOG'
#!/bin/sh
# h713-wifi-crashlog: record an AIC8800 WiFi firmware crash (DHDISDOWN).
#
# The vendor driver (aic8800_fdrv) times out on its firmware command->confirm
# handshake under load, prints "cmd timed-out / wlan error reset flow", marks
# its command queue CRASHED, and fires a KOBJ_CHANGE uevent with DHDISDOWN=1
# (rwnx_cmds.c: aic8800_start_system_reset_flow). There is no reliable in-place
# recovery from userspace -- unbinding+reloading the SDIO stack races the mmc
# driver core into a kernel Oops -- so this handler only logs the fault. WiFi
# and BT (the same combo chip) stay down until the device is rebooted.
TAG=h713-wifi-crashlog
MSG="AIC8800 WiFi firmware crashed (DHDISDOWN) -- WiFi/BT are down until the device is rebooted"
logger -t "$TAG" -- "$MSG" 2>/dev/null || true
printf '%s: %s\n' "$TAG" "$MSG" > /dev/kmsg 2>/dev/null || true
WIFICRASHLOG
chmod 0755 "$R/usr/local/sbin/h713-wifi-crashlog"

# udev fires the notifier on the driver's DHDISDOWN=1 uevent. The unit is
# triggered on demand (no [Install]/enable); systemd coalesces repeats.
install -d -m 0755 "$R/etc/udev/rules.d"
cat > "$R/etc/udev/rules.d/70-h713-wifi-crashlog.rules" <<'EOF'
# AIC8800 firmware crash -> aic8800_fdrv sends KOBJ_CHANGE with DHDISDOWN=1.
ACTION=="change", ENV{DHDISDOWN}=="1", TAG+="systemd", ENV{SYSTEMD_WANTS}+="h713-wifi-crashlog.service"
EOF
cat > "$systemd_dir/h713-wifi-crashlog.service" <<EOF
[Unit]
Description=Log an AIC8800 WiFi firmware crash (DHDISDOWN); no auto-recovery
# Launched by udev (70-h713-wifi-crashlog.rules); not started at boot.

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/h713-wifi-crashlog
EOF

# Load the scanout carveout exporter at boot. Unlike cedrus and panfrost, which
# udev autoloads off their DT compatibles, this module is a plain misc device
# with no device table -- modinfo shows no alias at all -- so nothing will ever
# load it on its own, and everything that presents a frame through
# /dev/scanout-dmabuf fails without it. Its defaults are the working carveout
# (0x6c100000, 8 MiB = both buffers), so no options are needed.
install -d -m 0755 "$R/etc/modules-load.d"
cat > "$R/etc/modules-load.d/h713-video.conf" <<EOF
sunxi_scanout_dmabuf
EOF

# WiFi baseline capture tool. Shipped in the image because it has to run ON the
# board and STA WiFi cannot currently carry a file to it -- without this it
# would have to be pasted over an 11 KB/s serial console every time.
if [ -n "${WIFI_BASELINE_SRC:-}" ] && [ -f "${WIFI_BASELINE_SRC}" ]; then
  install -d -m 0755 "$R/usr/local/sbin"
  install -m 0755 "$WIFI_BASELINE_SRC" "$R/usr/local/sbin/wifi-baseline"
  echo "[customize] installed /usr/local/sbin/wifi-baseline"
fi

# Optional boot WiFi hotspot (AP). Enabled only when the build passed
# HOTSPOT_ENABLED=1 (i.e. local/hotspot.conf existed). A dedicated AP owns wlan0
# and DHCP, so mask the STA supplicant and the default dnsmasq.
if [ "${HOTSPOT_ENABLED:-0}" = 1 ]; then
  install -d -m 0755 "$R/etc/hostapd"
  # Band/width. The AIC8800D80 is a 1x1 dual-band VHT80 part, but the AP used to
  # be emitted as plain 802.11g -- 20 MHz, no HT, 54 Mbit/s -- which capped file
  # transfer at about 1.3 MB/s in and 2.4 MB/s out against an SDIO bus measured
  # at 24.4 MB/s. Measured on hardware, 128 MiB each way, SHA-256 exact and zero
  # SDIO faults in every case:
  #
  #   2.4 GHz 11g (old)   1.33 MB/s in   2.37 MB/s out
  #   2.4 GHz HT40        4.85 MB/s in   7.65 MB/s out
  #   5 GHz   VHT80      13.25 MB/s in  14.41 MB/s out
  #
  # HOTSPOT_BAND picks between them. 5 GHz is much faster and removes the
  # long-standing in/out asymmetry, but has shorter range, excludes 2.4-only
  # clients, and carries stricter regulatory obligations -- which matters here
  # because regulatory.db is not installed and the stack falls back to
  # permissive rules. 2.4 GHz HT40 is the conservative default.
  #
  # MAX-MPDU-11454 is NOT supported by this driver (it reports max 1, i.e.
  # 7991); asking for it makes hostapd fail with "Unable to setup interface".
  case "${HOTSPOT_BAND:-2.4}" in
    5)
      _hw=a
      _chan=${HOTSPOT_CHANNEL_5G:-36}
      # 80 MHz centre index: 42 covers channels 36-48 (UNII-1, non-DFS).
      _modes="ieee80211n=1
ieee80211ac=1
ht_capab=[HT40+][SHORT-GI-20][SHORT-GI-40]
vht_capab=[SHORT-GI-80][MAX-MPDU-7991]
vht_oper_chwidth=1
vht_oper_centr_freq_seg0_idx=${HOTSPOT_VHT_SEG0:-42}"
      ;;
    *)
      _hw=g
      _chan=$HOTSPOT_CHANNEL
      _modes="ieee80211n=1
ht_capab=[HT40+][SHORT-GI-20][SHORT-GI-40][MAX-AMSDU-7935]"
      ;;
  esac
  cat > "$R/etc/hostapd/hotspot.conf" <<EOF
interface=wlan0
driver=nl80211
ssid=$HOTSPOT_SSID
hw_mode=$_hw
channel=$_chan
$_modes
wmm_enabled=1
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

echo "[customize] configured key-only SSH, ttyS0 autologin, AIC8800 autoload + BT attach, scanout-dmabuf autoload"
