#!/bin/sh
set -eu
backup=/root/panel-initial-state-trial/proper-before-1867.bin
expected=cf1941d6f94441e55607f96ca83239b1c895b9b92166ccf2d6914aac46001423
[ "$(wc -c < "$backup")" -eq 955904 ]
[ "$(sha256sum "$backup" | cut -d ' ' -f1)" = "$expected" ]
dd if="$backup" of=/dev/mmcblk0 bs=512 seek=4828160 count=1867 conv=fsync,notrunc status=progress
[ "$(dd if=/dev/mmcblk0 bs=512 skip=4828160 count=1867 iflag=direct status=none | sha256sum | cut -d ' ' -f1)" = "$expected" ]
echo 'PASS: previous stage-2 U-Boot proper restored and verified; reboot separately'
