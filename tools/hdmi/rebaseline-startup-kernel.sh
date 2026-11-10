#!/bin/sh
# Run on target after tools/install-kernel-fit.sh replaced the boot FIT.
# The startup integration pins the kernel it was validated with
# (/var/lib/h713-hdmi-startup/kernel.sha256); update-startup-script.sh
# refuses to run against any other FIT. Move that pin to the new FIT, and
# only to the one named: the FAT copy must match the expected checksum.
#   usage: rebaseline-startup-kernel.sh <expected-sha256-of-new-fit>
set -eu
S=${H713_HDMI_STATE:-/var/lib/h713-hdmi-startup}
FAT=${H713_BOOT_FAT:-/mnt/boot}
want=${1:?usage: $0 <expected-sha256>}
die() { echo "$*; nothing changed" >&2; exit 1; }
case $want in *[!0-9a-f]*|'') die 'expected checksum is not lowercase hex';; esac
[ ${#want} = 64 ] || die 'expected checksum is not sha256'
[ -f "$S/kernel.sha256" ] || die 'no startup kernel pin to move'
if [ -z "${H713_BOOT_FAT:-}" ]; then
  mountpoint -q "$FAT" || mount -t vfat /dev/mmcblk0p2 "$FAT"
  [ "$(findmnt -n -o SOURCE "$FAT")" = /dev/mmcblk0p2 ] || die 'boot FAT not mounted from mmcblk0p2'
fi
got=$(sha256sum "$FAT/h713-kernel.fit" | cut -d' ' -f1)
[ "$got" = "$want" ] || die "boot FIT is $got, not the expected $want"
old=$(cut -d' ' -f1 "$S/kernel.sha256")
[ "$old" != "$want" ] || { echo 'startup kernel pin already current'; exit 0; }
stamp=$(date +%Y%m%dT%H%M%S)
cp -a "$S/kernel.sha256" "$S/kernel.sha256.$stamp"
echo "$want  $FAT/h713-kernel.fit" > "$S/kernel.sha256.new"
sync
mv "$S/kernel.sha256.new" "$S/kernel.sha256"
sync
sha256sum -c --quiet "$S/kernel.sha256"
echo "startup kernel pin moved $old -> $want; previous kept as kernel.sha256.$stamp"
