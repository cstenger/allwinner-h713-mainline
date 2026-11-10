#!/bin/sh
# Run on target from a complete build-startup.py bundle. Replaces ONLY the
# U-Boot script (FAT h713-hdmi.scr plus the installed .scr/.cmd/SHA256SUMS).
# Refuses unless every other installed file is byte-identical to the bundle,
# so modules, units and firmware owned by running services are never touched.
set -eu
cd "$(dirname "$0")"
[ "$(id -u)" = 0 ]
I=/usr/lib/h713-hdmi
S=/var/lib/h713-hdmi-startup
sha256sum -c --quiet SHA256SUMS
[ -d "$I" ] && [ -f "$S/kernel.sha256" ]
mountpoint -q /mnt/boot || mount -t vfat /dev/mmcblk0p2 /mnt/boot
[ "$(findmnt -n -o SOURCE /mnt/boot)" = /dev/mmcblk0p2 ]
sha256sum -c --quiet "$S/kernel.sha256"
# The FAT script must be the installed generation, not something foreign.
cmp "$I/h713-hdmi.scr" /mnt/boot/h713-hdmi.scr
awk '{print $2}' SHA256SUMS | while read -r f; do
  case "$f" in h713-hdmi.scr|h713-hdmi.cmd|update-startup-script.sh) continue;; esac
  cmp "$f" "$I/$f" || { echo "installed $f differs from bundle; refusing script-only update" >&2; exit 1; }
done
if cmp -s h713-hdmi.scr /mnt/boot/h713-hdmi.scr; then echo 'Startup script already current'; exit 0; fi
stamp=$(date +%Y%m%dT%H%M%S)
cp -a "$I/h713-hdmi.scr" "$S/h713-hdmi.scr.$stamp"
cp -a "$I/h713-hdmi.cmd" "$S/h713-hdmi.cmd.$stamp"
cp h713-hdmi.scr /mnt/boot/h713-hdmi.scr.new
sync
cmp h713-hdmi.scr /mnt/boot/h713-hdmi.scr.new
mv /mnt/boot/h713-hdmi.scr.new /mnt/boot/h713-hdmi.scr
sync
cmp h713-hdmi.scr /mnt/boot/h713-hdmi.scr
install -m 0644 h713-hdmi.scr h713-hdmi.cmd SHA256SUMS "$I/"
[ -e update-startup-script.sh ] && install -m 0755 update-startup-script.sh "$I/"
(cd "$I" && sha256sum -c --quiet SHA256SUMS)
sha256sum -c --quiet "$S/kernel.sha256"
echo "Startup script updated; previous generation kept as $S/h713-hdmi.scr.$stamp"
