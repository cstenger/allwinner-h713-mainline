#!/bin/sh
# Approved installation; full video installer owns its own backup and restart sequence.
set -eu
cd /run/h713-playback-policy
test -e /proc/device-tree/chosen/h713,hdmi-boot-v1
sha256sum -c SHA256SUMS
sha256sum -c - <<'SUMS'
89504302309cc3a1be528c5701f20ef928670a6ac5a5e82f299164d2357f77aa  /usr/local/bin/h713-play
367d797fbba23ada77c4db441d7a470236cece21ec08416835f0cd06a6ccf622  /usr/local/bin/gst-plane-play
582d16ac58f325c92b8abafb6d6072fda6fda353515f96ea146de3ae97b0b14e  /usr/lib/h713-hdmi-video/h713-hdmi-v4l2.ko
SUMS
test "$(./gst-plane-play --playback-policy-version)" = hdmi-priority-v1
sh hdmi-video/install-hdmi-video.sh --dry-run --update
install -d -m 0700 /var/lib/h713-playback-policy
backup=$(mktemp -d /var/lib/h713-playback-policy/backup.XXXXXX)
cp -a /usr/local/bin/h713-play /usr/local/bin/gst-plane-play "$backup/"
stat -c '%n %U:%G %a %s' /usr/local/bin/h713-play /usr/local/bin/gst-plane-play > "$backup/metadata.txt"
sha256sum /etc/default/h713-hdmi-speaker > "$backup/speaker-defaults.sha256"
(cd "$backup" && sha256sum h713-play gst-plane-play > SHA256SUMS)
cp SHA256SUMS "$backup/prepared-SHA256SUMS"
echo "$backup" > playback-backup-path.txt
echo "Playback backup: $backup"
player_tmp=$(mktemp /usr/local/bin/.gst-plane-play.policy.XXXXXX)
launcher_tmp=$(mktemp /usr/local/bin/.h713-play.policy.XXXXXX)
trap 'rm -f "$player_tmp" "$launcher_tmp"' EXIT HUP INT TERM
install -m 0755 gst-plane-play "$player_tmp"
install -m 0755 h713-play "$launcher_tmp"
chmod --reference=/usr/local/bin/gst-plane-play "$player_tmp"
chown --reference=/usr/local/bin/gst-plane-play "$player_tmp"
chmod --reference=/usr/local/bin/h713-play "$launcher_tmp"
chown --reference=/usr/local/bin/h713-play "$launcher_tmp"
mv -f "$player_tmp" /usr/local/bin/gst-plane-play
mv -f "$launcher_tmp" /usr/local/bin/h713-play
cmp gst-plane-play /usr/local/bin/gst-plane-play
cmp h713-play /usr/local/bin/h713-play
test "$(/usr/local/bin/gst-plane-play --playback-policy-version)" = hdmi-priority-v1
if /usr/local/bin/gst-plane-play --check-playback-policy > installed-refusal.txt 2>&1; then
    echo 'FAIL: installed ownership check unexpectedly allowed' >&2
    exit 1
else
    test "$?" = 1
fi
grep -q 'HDMI has priority' installed-refusal.txt
cat installed-refusal.txt
for route in auto plane gpu; do
    if /usr/local/bin/h713-play --dry-run --route="$route" dummy.mp4 > installed-refusal.txt 2>&1; then
        echo 'FAIL: installed launcher unexpectedly allowed' >&2
        exit 1
    else
        test "$?" = 1
    fi
    grep -q 'HDMI has priority' installed-refusal.txt
    cat installed-refusal.txt
done
sh hdmi-video/install-hdmi-video.sh --update
sha256sum -c "$backup/speaker-defaults.sha256"
echo 'PASS: installed playback guard and restarted HDMI video/ring; speaker calibration unchanged'
