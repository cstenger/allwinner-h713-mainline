#!/bin/sh
# Approved target staging only. All negative playback tests are read-only checks/dry runs.
set -eu
cd /run/h713-playback-policy
grep -q 'HY200 QZ713DF_A1' /proc/device-tree/model
test -e /proc/device-tree/chosen/h713,hdmi-boot-v1
sha256sum -c SHA256SUMS
cc -O2 -Wall -Wextra -Werror -o gst-plane-play gst-plane-play.c \
  $(pkg-config --cflags --libs gstreamer-1.0 gstreamer-video-1.0)
python3 - <<'PY'
from pathlib import Path
import struct
header = Path('gst-plane-play').read_bytes()[:20]
assert header[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<H', header, 18)[0] == 183
print('PASS: compiled player is little-endian ELF64 AArch64')
PY
test "$(./gst-plane-play --playback-policy-version)" = hdmi-priority-v1
export PATH=/run/h713-playback-policy:$PATH
touch dummy.mp4
refuses() {
    if "$@" > refusal.txt 2>&1; then
        echo 'FAIL: local playback check unexpectedly allowed' >&2
        exit 1
    else
        result=$?
    fi
    test "$result" = 1
    grep -q 'HDMI has priority' refusal.txt
    cat refusal.txt
}
refuses ./gst-plane-play --check-playback-policy
for route in auto plane gpu; do
    refuses bash ./h713-play --dry-run --route="$route" dummy.mp4
done
sh hdmi-video/install-hdmi-video.sh --dry-run --update
sha256sum gst-plane-play h713-play
echo 'PASS: target compile, policy refusal on all launcher routes and video installer dry run'
