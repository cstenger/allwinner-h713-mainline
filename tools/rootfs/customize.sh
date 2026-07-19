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

# Never clone host keys or machine identity across images. Debian's
# sshd-keygen.service creates host keys during the first boot.
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
ln -sfn /usr/lib/systemd/system/sshd-keygen.service \
  "$systemd_dir/ssh.service.wants/sshd-keygen.service"
ln -sfn /dev/null "$systemd_dir/systemd-networkd-wait-online.service"

cat > "$systemd_dir/serial-getty@ttyS0.service.d/autologin.conf" <<EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin root --noclear %I \$TERM
EOF

echo "[customize] configured key-only SSH and ttyS0 root autologin"
