#!/usr/bin/env bash
# Turn a customised rootfs tree into a read-only root image
# (docs/lpddr3-bringup-plan.md, Phase 4 stage 2). Run by tools/rootfs/build.sh
# --root-layout ro after customize.sh.
#
#   tools/rootfs/ro-root.sh TREE
#
# The image is mounted read-only (EROFS, SquashFS or ext4 ro) from super. One
# writable data partition (UDISK, ext4) carries everything that changes:
#
#   /data                the data partition itself (media, user files)
#   /etc                 overlay: image /etc below, /data/overlay/etc above
#   /var                 bind of /data/var, seeded from the image on first boot
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

# First boot (or after a data wipe): seed /var from the image. Copy to a
# temporary name and rename, so an interrupted copy is redone, not used.
if [ ! -d /data/var ]; then
	rm -rf /data/var.seed
	cp -a /var /data/var.seed && mv /data/var.seed /data/var && say "seeded /data/var from the image"
fi
[ -d /data/var ] && mount --bind /data/var /var || say "/var bind failed: /var is read-only"

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
# (super) and the data partition, by either name it carries.
cat > "$R/etc/udev/rules.d/99-zz-h713-unused-partitions.rules" <<'EOF'
SUBSYSTEM=="block", KERNEL=="mmcblk0*", ENV{ID_PART_ENTRY_NAME}!="linux|UDISK|super", TAG-="systemd"
EOF

# Nothing in the image may be written at runtime; the machine id is created
# on the data partition (through the /etc overlay) on first boot.
test -f "$R/etc/machine-id" && test ! -s "$R/etc/machine-id"
echo "ro-root: read-only root layout applied to $R"
