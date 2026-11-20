#!/usr/bin/env bash
# Stress the U-Boot UMS write path and locate corruption (HY200_QZ713_V2).
#
#   sudo [PASSES=N] [MAXKB=K] [SIZE_MIB=M] tools/ums-stress.sh /dev/sdX
#
# The board exports its eMMC with `ums 0 mmc 1`. The test area is the unused
# tail of super (partition 9): from 640 MiB (the root image ends at 556 MiB)
# for SIZE_MIB (default 1280, max 1408). Nothing else on the device is
# touched; the root image in front of it is checked unchanged at the end.
#
# Each pass writes fresh random data with O_DIRECT (dd bs=4M), reads it back
# with O_DIRECT, and lists every differing 4 KiB page with its offset inside
# the SCSI command (max_sectors_kb, default as the kernel set it; MAXKB=K
# overrides it for the run). A bad page is read a second time: the same wrong
# bytes mean the medium holds them (a write fault), different bytes mean the
# read path. The USB controller and the setting are logged with the results
# in local/recovery/ums-stress/.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
dev=${1:?DEV}
passes=${PASSES:-3}; size_mib=${SIZE_MIB:-1280}; off_mib=640
say() { printf '[ums-stress] %s\n' "$*"; }
die() { say "FAIL: $*"; exit 1; }

[ "$(id -u)" = 0 ] || die "run as root"
[ -b "$dev" ] || die "$dev is not a block device"
[ "$size_mib" -le 1408 ] || die "SIZE_MIB max 1408 (super is 2048 MiB)"
python3 "$ROOT/tools/board-guard.py" --expect hy200-qz713-v2 --dev "$dev" || die "board guard refused $dev"
name=${dev##*/}
super=$(lsblk -lnpo NAME "$dev" | grep -E "^${dev}p?9\$") || die "no partition 9"
[ "$(lsblk -no PARTLABEL "$super")" = super ] || die "partition 9 is not super"
[ "$(cat "/sys/class/block/${super##*/}/start")" = $((0x92400)) ] || die "super not at LBA 0x92400"
findmnt -rno SOURCE | grep -q "^/dev/${name}" && die "something on $dev is mounted"

q=/sys/block/$name/queue/max_sectors_kb
orig_kb=$(cat "$q")
[ -z "${MAXKB:-}" ] || echo "$MAXKB" > "$q"
cmd_kb=$(cat "$q")
trap 'echo "$orig_kb" > "$q" 2>/dev/null || true' EXIT

usbdev=$(readlink -f "/sys/block/$name" | grep -o '/usb[0-9]*/[0-9-]*' | head -1)
bus=${usbdev#/usb}; bus=${bus%%/*}
hc=$(basename "$(readlink -f "/sys/bus/usb/devices/usb$bus/..")")
hcname=$(lspci -s "$hc" 2>/dev/null | cut -d' ' -f2-)
out="$ROOT/local/recovery/ums-stress"; mkdir -p "$out"
log="$out/$(date +%Y%m%d-%H%M%S)-bus${bus}-${cmd_kb}k.log"
exec > >(tee "$log") 2>&1
say "device $dev on usb$bus, controller $hc ($hcname)"
say "max_sectors_kb $cmd_kb (was $orig_kb); test area super+${off_mib} MiB, ${size_mib} MiB; $passes passes"

root_sha=$(dd if="$super" bs=1M count=556 iflag=direct status=none | sha256sum | cut -c1-16)
tmp=$(mktemp -d /dev/shm/ums-stress.XXXXXX); trap 'echo "$orig_kb" > "$q" 2>/dev/null || true; rm -rf "$tmp"' EXIT
total_bad=0
for p in $(seq 1 "$passes"); do
  head -c $((size_mib << 20)) /dev/urandom > "$tmp/pat"
  t0=$(date +%s)
  dd if="$tmp/pat" of="$super" bs=4M seek=$((off_mib / 4)) oflag=direct conv=fsync status=none
  t1=$(date +%s)
  dd if="$super" of="$tmp/back" bs=4M skip=$((off_mib / 4)) count=$((size_mib / 4)) iflag=direct status=none
  t2=$(date +%s)
  bad=$(python3 -I - "$tmp/pat" "$tmp/back" "$super" "$off_mib" "$cmd_kb" "$out" "$p" <<'EOF'
import os, sys, zlib
pat, back, superdev, off_mib, cmd_kb, out, p = sys.argv[1:]
off = int(off_mib) << 20; cmd = int(cmd_kb) << 10
a = open(pat, 'rb').read(); b = open(back, 'rb').read()
bad = [i for i in range(0, len(a), 4096) if a[i:i+4096] != b[i:i+4096]]
fd = os.open(superdev, os.O_RDONLY | os.O_DIRECT)
import mmap
buf = mmap.mmap(-1, 4096)
for i in bad:
    os.preadv(fd, [buf], off + i)
    again = bytes(buf)
    kind = 'MEDIUM (same bytes on re-read)' if again == b[i:i+4096] else (
           'READ PATH (re-read is correct)' if again == a[i:i+4096] else 'UNSTABLE (re-read differs again)')
    found = a.find(b[i:i+256])
    src = f'from pattern +{found:#x}' if found >= 0 else 'not from this pattern'
    print(f'  bad page: area+{i:#x} (super+{off+i:#x}), {(off+i) % cmd:#x} into a {cmd >> 10} KiB command, '
          f'{kind}, {src}', file=sys.stderr)
    open(f'{out}/pass{p}-page-{off+i:#x}.bin', 'wb').write(b[i:i+4096])
print(len(bad))
EOF
)
  total_bad=$((total_bad + bad))
  say "pass $p: write $((size_mib / (t1 - t0 > 0 ? t1 - t0 : 1))) MiB/s, read $((size_mib / (t2 - t1 > 0 ? t2 - t1 : 1))) MiB/s, bad 4 KiB pages: $bad"
done
root_after=$(dd if="$super" bs=1M count=556 iflag=direct status=none | sha256sum | cut -c1-16)
[ "$root_sha" = "$root_after" ] && say "root image region unchanged" || say "WARNING: root image region CHANGED ($root_sha -> $root_after)"
say "total bad pages: $total_bad over $((passes * size_mib)) MiB; log $log"
