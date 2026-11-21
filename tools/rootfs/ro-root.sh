#!/usr/bin/env bash
# Turn a customised rootfs tree into a read-only root image
# (docs/lpddr3-bringup-plan.md, Phase 4 stage 2). Run by tools/rootfs/build.sh
# --root-layout ro after customize.sh.
#
#   H713_RAUC_KEYRING=CA_PEM tools/rootfs/ro-root.sh TREE
#
# The image (EROFS) is mounted read-only from its root slot (root_a or root_b). One
# writable data partition (UDISK, ext4) carries everything that changes:
#
#   /data                the data partition itself (media, user files)
#   /etc                 overlay: image /etc below, /data/overlay/etc above
#   /var                 overlay: image /var below, /data/overlay/var above
#   /tmp                 tmpfs (systemd tmp.mount), capped
#
# /etc must be writable before systemd starts (machine-id, ssh host keys), so
# the mounts are made by /usr/lib/h713/preinit, which the kernel runs as init=
# and which then execs systemd. If the data partition cannot be mounted the
# board still boots, on a volatile tmpfs /data, and says so on the console.
set -euo pipefail
R=${1:?TREE}
[ -d "$R/etc" ] || { echo "ro-root: $R is not a rootfs tree" >&2; exit 1; }

install -d -m 0755 "$R/data" "$R/usr/lib/h713"

cat > "$R/usr/lib/h713/preinit" <<'EOF'
#!/bin/sh
# Early mounts for the read-only root (tools/rootfs/ro-root.sh). Runs as PID 1
# before systemd: kernel command line init=/usr/lib/h713/preinit.
#   h713.data=DEV    data partition: a /dev path or PARTUUID=/PARTLABEL=/UUID=
#                    (default /dev/mmcblk0p26)
PATH=/usr/sbin:/usr/bin
say() { echo "h713-preinit: $*" > /dev/kmsg 2>/dev/null || echo "h713-preinit: $*"; }

mount -t proc -o nosuid,nodev,noexec proc /proc
data=/dev/mmcblk0p26
for arg in $(cat /proc/cmdline); do
	case "$arg" in h713.data=*) data=${arg#h713.data=} ;; esac
done
# PARTUUID=, PARTLABEL=, UUID=, LABEL=: resolve by scanning /proc/partitions.
case "$data" in
*=*) data=$(findfs "$data" 2>/dev/null) || { say "cannot resolve h713.data"; data=/nonexistent; } ;;
esac

# rootwait covered the root device only; the data partition is on the same
# eMMC, but wait briefly in case its node is not there yet.
n=0
while [ ! -b "$data" ] && [ "$n" -lt 50 ]; do sleep 0.1; n=$((n + 1)); done

volatile=
if [ -b "$data" ]; then
	# -p repairs only what is safe without asking; exit codes 0-1 mean the
	# filesystem is usable. A clean journal makes this near-instant.
	e2fsck -p "$data" > /dev/kmsg 2>&1
	rc=$?
	[ "$rc" -le 1 ] || say "e2fsck $data exited $rc"
	mount -t ext4 -o noatime "$data" /data || volatile=1
else
	say "no data partition $data"
	volatile=1
fi
if [ -n "$volatile" ]; then
	say "data partition unavailable: /data, /etc changes and /var are VOLATILE this boot"
	mount -t tmpfs -o mode=0755,size=64M h713-volatile /data
fi

mkdir -p /data/overlay/etc/upper /data/overlay/etc/work
mount -t overlay h713-etc \
	-o lowerdir=/etc,upperdir=/data/overlay/etc/upper,workdir=/data/overlay/etc/work /etc ||
	say "/etc overlay failed: /etc is read-only"

# /var is an overlay too, not a copy: the image's /var (package database,
# shipped state) stays underneath and is updated with the image; only what
# changes at runtime lands on /data.
mkdir -p /data/overlay/var/upper /data/overlay/var/work
mount -t overlay h713-var \
	-o lowerdir=/var,upperdir=/data/overlay/var/upper,workdir=/data/overlay/var/work /var ||
	say "/var overlay failed: /var is read-only"

umount /proc
exec /sbin/init "$@"
EOF
chmod 0755 "$R/usr/lib/h713/preinit"

# Root is mounted read-only by the kernel and stays that way; there is no
# filesystem to check or grow. The data partition is not in fstab: preinit
# mounted it before systemd, which picks the mounts up from mountinfo.
printf '%s\n' \
  '# Read-only root (tools/rootfs/ro-root.sh). /data, /etc and /var are mounted' \
  '# by /usr/lib/h713/preinit before systemd starts.' \
  '/dev/root  /  auto  ro,noatime  0  0' \
  > "$R/etc/fstab"

systemd_dir="$R/etc/systemd/system"
rm -f "$systemd_dir/multi-user.target.wants/h713-rootfs-grow-once.service" \
  "$systemd_dir/h713-rootfs-grow-once.service"

# /tmp: tmpfs from systemd's tmp.mount (Debian 13 default), capped below its
# 50 % default so a runaway writer cannot take half the 1 GiB of RAM.
install -d -m 0755 "$systemd_dir/tmp.mount.d"
cat > "$systemd_dir/tmp.mount.d/h713-size.conf" <<'EOF'
[Mount]
Options=mode=1777,strictatime,nosuid,nodev,size=256M,nr_inodes=1m
EOF
if [ ! -e "$R/usr/lib/systemd/system/tmp.mount" ]; then
  echo "ro-root: the image has no tmp.mount" >&2; exit 1
fi
install -d -m 0755 "$systemd_dir/local-fs.target.wants"
ln -sfn /usr/lib/systemd/system/tmp.mount "$systemd_dir/local-fs.target.wants/tmp.mount"

# systemd needs device units for the partitions it tracks mounts on: the root
# (super, or root_a/root_b once the GPT is split) and the data partition.
cat > "$R/etc/udev/rules.d/99-zz-h713-unused-partitions.rules" <<'EOF'
SUBSYSTEM=="block", KERNEL=="mmcblk0*", ENV{ID_PART_ENTRY_NAME}!="linux|UDISK|super|root_a|root_b", TAG-="systemd"
EOF

# A/B with RAUC (U-Boot patch 0012, bootmeth_rauc): U-Boot takes one attempt
# from the slot it boots and passes rauc.slot=A|B; RAUC reads and writes the
# U-Boot environment (BOOT_ORDER, BOOT_<slot>_LEFT) with Debian's fw_setenv,
# marks the booted slot good, and installs updates into the other slot. Two
# environment copies, 64 KiB each, in the GPT partition "empty".
cat > "$R/etc/fw_env.config" <<'EOF'
# U-Boot environment of the HY200_QZ713_V2 (redundant; U-Boot patch 0012):
# disk offsets 0x93d80000 and 0x93d90000, i.e. 8 MiB into GPT partition
# "empty". Named by partition, with offsets below 2 GiB, because libubootenv
# (0.3.5 in Debian 13, unchanged on upstream master) stores lseek()'s off_t
# result in an int in fileread()/filewrite(): any offset >= 2^31 wraps
# negative and fails before read()/write() (traced on the board 2026-11-20).
/dev/disk/by-partlabel/empty	0x800000	0x10000
/dev/disk/by-partlabel/empty	0x810000	0x10000
EOF
# Remove the older image's config if repacking an existing read-only root.
rm -f "$R/etc/rauc/system.conf"
install -m 0644 "${H713_RAUC_KEYRING:?Set H713_RAUC_KEYRING to the public CA file}" \
  "$R/usr/lib/h713/rauc-keyring.pem"
cat > "$R/usr/lib/h713/rauc-system.conf" <<'EOF'
# RAUC on the HY200_QZ713_V2 projector: a slot is a boot partition (vfat: the
# kernel FIT and boot.scr) and its read-only root (EROFS image).
[system]
compatible=hy200-qz713-v2
bootloader=uboot
data-directory=/data/rauc
bundle-formats=verity

# Bundles must be signed by a certificate that chains to this CA
# (tools/keys/make-dev-keys.sh, tools/v2-rauc-bundle.sh). The keyring sits
# on the read-only root, not in /etc: /etc is an overlay whose upper layer
# lives on /data, where a stale copy could shadow the image's keyring.
[keyring]
path=/usr/lib/h713/rauc-keyring.pem
# The signer certificate carries extendedKeyUsage codeSigning.
check-purpose=codesign
# The RTC loses its calendar on power loss. Offline updates use the CMS
# signing time for certificate validity; it is supplied by the signer.
use-bundle-signing-time=true

[slot.rootfs.0]
device=/dev/disk/by-partlabel/root_a
type=raw
bootname=A

[slot.rootfs.1]
device=/dev/disk/by-partlabel/root_b
type=raw
bootname=B

[slot.boot.0]
device=/dev/disk/by-partlabel/boot_a
type=vfat
parent=rootfs.0

[slot.boot.1]
device=/dev/disk/by-partlabel/boot_b
type=vfat
parent=rootfs.1
EOF
# Mark the booted slot good once the system is up. Debian ships RAUC as rauc
# (CLI) + rauc-service (D-Bus service) with no mark-good unit; this is the
# same unit Yocto's meta-rauc provides: `rauc status mark-good`.
if [ ! -x "$R/usr/bin/rauc" ] || [ ! -e "$R/usr/lib/systemd/system/rauc.service" ]; then
  echo "ro-root: the image lacks rauc / rauc-service" >&2; exit 1
fi
# Pin the daemon to the config shipped with this slot, even if /etc contains
# a config left over from a previous image.
install -d -m 0755 "$R/usr/lib/systemd/system/rauc.service.d"
cat > "$R/usr/lib/systemd/system/rauc.service.d/h713-config.conf" <<'EOF'
[Service]
ExecStart=
ExecStart=/usr/bin/rauc --conf=/usr/lib/h713/rauc-system.conf --mount=/run/rauc/mnt service
EOF
cat > "$systemd_dir/rauc-mark-good.service" <<'EOF'
[Unit]
Description=RAUC: mark the booted slot good
ConditionKernelCommandLine=rauc.slot
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/usr/bin/rauc status mark-good

[Install]
WantedBy=multi-user.target
EOF
ln -sfn ../rauc-mark-good.service \
  "$systemd_dir/multi-user.target.wants/rauc-mark-good.service"

# Nothing in the image may be written at runtime; the machine id is created
# on the data partition (through the /etc overlay) on first boot.
test -f "$R/etc/machine-id" && test ! -s "$R/etc/machine-id"
echo "ro-root: read-only root layout applied to $R"
