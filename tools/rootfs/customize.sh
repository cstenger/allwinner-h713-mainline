#!/bin/sh
# mmdebstrap customize-hook: $1 = rootfs dir (runs inside the unshare namespace).
set -e
R="$1"

# --- files (no chroot needed) ---
echo h713-arm64 > "$R/etc/hostname"
cat > "$R/etc/hosts" <<EOF
127.0.0.1	localhost
127.0.1.1	h713-arm64
EOF
# root filesystem lives on the eMMC UDISK partition
echo "/dev/mmcblk0p26  /  ext4  defaults,noatime,x-systemd.growfs  0  1" > "$R/etc/fstab"

# bring up eth via DHCP if present (harmless if no NIC)
mkdir -p "$R/etc/network"
cat > "$R/etc/network/interfaces" <<EOF
auto lo
iface lo inet loopback
allow-hotplug eth0
iface eth0 inet dhcp
EOF

# --- logic needing the target's own tools (aarch64 via qemu binfmt) ---
chroot "$R" sh -c '
set -e
echo "root:root" | chpasswd
systemctl enable serial-getty@ttyS0.service
systemctl enable ssh.service 2>/dev/null || true
# do not wait forever for network at boot
systemctl mask systemd-networkd-wait-online.service 2>/dev/null || true
'
echo "[customize] done"
