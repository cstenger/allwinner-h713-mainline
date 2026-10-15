#!/bin/sh
# Run on target from the complete build-startup.py bundle. Installs but does
# not start capture or change U-Boot environment. Safe under the bench service.
set -eu
cd "$(dirname "$0")"
[ "$(id -u)" = 0 ]
[ "$(uname -r)" = 6.18.38 ]
grep -q 'HY200 QZ713DF_A1' /proc/device-tree/model
sha256sum -c SHA256SUMS
for module in h713-hdmi-receiver.ko h713-hdmi-audio.ko h713-hdmi-signal.ko h713-ddc-pins.ko; do
  set -- $(modinfo -F vermagic "$module")
  [ "$1" = 6.18.38 ]
done
# Do not replace an installed generation while its service owns hardware.
[ ! -e /usr/lib/h713-hdmi ] || { echo 'Existing startup installation; refusing replacement' >&2; exit 1; }
mkdir -p /mnt/boot
mountpoint -q /mnt/boot || mount -t vfat /dev/mmcblk0p2 /mnt/boot
[ "$(findmnt -n -o SOURCE /mnt/boot)" = /dev/mmcblk0p2 ]
[ "$(stat -c %s /mnt/boot/h713-kernel.fit)" = 7789216 ]
[ ! -e /mnt/boot/h713-hdmi.scr ]
[ ! -e /etc/systemd/system/h713-hdmi-capture.service ]
# The original FIT is untouched. Rollback state is outside the small boot FAT.
install -d -m 0755 /var/lib/h713-hdmi-startup /usr/lib/h713-hdmi
sha256sum /mnt/boot/h713-kernel.fit > /var/lib/h713-hdmi-startup/kernel.sha256
cp -a . /usr/lib/h713-hdmi/
chmod -R go-w /usr/lib/h713-hdmi
install -m 0644 h713-hdmi-capture.service /etc/systemd/system/h713-hdmi-capture.service
install -m 0644 h713-hdmi-signal.service /etc/systemd/system/h713-hdmi-signal.service
install -m 0755 h713-hdmi-hold-guard /usr/lib/systemd/system-shutdown/h713-hdmi-hold-guard
systemd-analyze verify /etc/systemd/system/h713-hdmi-capture.service /etc/systemd/system/h713-hdmi-signal.service
cp h713-hdmi.scr /mnt/boot/h713-hdmi.scr.new
sync
cmp h713-hdmi.scr /mnt/boot/h713-hdmi.scr.new
mv /mnt/boot/h713-hdmi.scr.new /mnt/boot/h713-hdmi.scr
sync
cmp h713-hdmi.scr /mnt/boot/h713-hdmi.scr
sha256sum -c /var/lib/h713-hdmi-startup/kernel.sha256
# Enable only; the current bench runtime unit must retain ownership this boot.
systemctl enable h713-hdmi-capture.service h713-hdmi-signal.service
echo 'Installed. Activate only after saving the guarded U-Boot environment and a physical cold cycle.'
