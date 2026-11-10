#!/bin/sh
# Board-only consumer installation; never restarts the signal or capture owner.
set -eu
update=0
case "${1-}" in
    '') ;;
    --update) update=1 ;;
    *) echo 'Usage: install-speaker.sh [--update]' >&2; exit 2 ;;
esac
cd "$(dirname "$0")"
[ "$(id -u)" = 0 ]
grep -q 'HY200 QZ713DF_A1' /proc/device-tree/model
sha256sum -c SHA256SUMS
command -v cc >/dev/null
pkg-config --exists gstreamer-1.0
command -v gst-launch-1.0 >/dev/null
gst-inspect-1.0 alsasrc >/dev/null
gst-inspect-1.0 alsasink >/dev/null
command -v pw-loopback >/dev/null
command -v pw-dump >/dev/null
command -v pw-cli >/dev/null
id media >/dev/null
test -S /run/user/1000/pipewire-0
[ -f /etc/systemd/system/h713-hdmi-signal.service ]
[ -f /etc/systemd/system/h713-hdmi-capture.service ]
target=/usr/lib/h713-hdmi-speaker
# Updates are explicit and require the old installed generation to verify.
if [ -e "$target/SHA256SUMS" ]; then
    (cd "$target"; sha256sum -c SHA256SUMS)
    cmp "$target/h713-hdmi-speaker.service" /etc/systemd/system/h713-hdmi-speaker.service
    if [ "$update" = 0 ]; then cmp SHA256SUMS "$target/SHA256SUMS"; fi
fi
stage=$(mktemp -d /tmp/h713-speaker-install.XXXXXX)
trap 'rm -rf "$stage"' EXIT HUP INT TERM
cc -O2 -Wall -Wextra -Werror alsa-ctl.c -o "$stage/alsa-ctl"
cc -O2 -Wall -Wextra -Werror hdmi-speaker.c -o "$stage/hdmi-speaker" $(pkg-config --cflags --libs gstreamer-1.0)
python3 -m py_compile pipewire-speaker.py
systemd-analyze verify "$PWD/h713-hdmi-speaker.service"
if [ -e "$target/SHA256SUMS" ] && [ "$update" = 1 ]; then
    install -d -m 0755 /var/lib/h713-hdmi-speaker
    backup=$(mktemp -d /var/lib/h713-hdmi-speaker/backup.XXXXXX)
    cp -a "$target/." "$backup/"
    echo "Speaker rollback backup: $backup"
fi
# Stop only the old speaker consumer; stopping a transient unit collects it.
if [ "$(systemctl show h713-hdmi-speaker.service -p LoadState --value)" != not-found ]; then
    systemctl stop h713-hdmi-speaker.service
fi
install -d -m 0755 "$target"
install -m 0755 "$stage/alsa-ctl" "$target/alsa-ctl"
install -m 0755 "$stage/hdmi-speaker" "$target/hdmi-speaker"
install -m 0755 enable-mixer.sh "$target/enable-mixer.sh"
install -m 0755 pipewire-speaker.py "$target/pipewire-speaker.py"
install -m 0644 alsa-ctl.c hdmi-speaker.c SHA256SUMS install-speaker.sh h713-hdmi-speaker.service "$target/"
install -m 0644 h713-hdmi-speaker.service /etc/systemd/system/h713-hdmi-speaker.service
systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/h713-hdmi-speaker.service
systemctl enable --now h713-hdmi-speaker.service
sha256sum "$target/alsa-ctl" "$target/enable-mixer.sh" /etc/systemd/system/h713-hdmi-speaker.service
echo 'Persistent speaker consumer installed; HDMI backend ownership unchanged.'
