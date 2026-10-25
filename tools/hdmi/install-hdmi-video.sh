#!/bin/sh
# Install HDMI-in on the panel (HDMI panel-source design 10.26, stage 5).
# Board-only; never restarts the signal or capture owner.
#
#   sh install-hdmi-video.sh             first install (or an identical reinstall)
#   sh install-hdmi-video.sh --update    replace an installed generation, backing it
#                                        up under /var/lib/h713-hdmi-video
#   sh install-hdmi-video.sh --dry-run [--update]
#                                        every check of that mode, no writes
#   sh install-hdmi-video.sh --remove    stop, disable and remove (backups kept)
#
# Installs the bridge module and copies under /usr/lib/h713-hdmi-video, the
# two units in /etc/systemd/system and the rule in /etc/udev/rules.d, then
# enables and starts h713-hdmi-ring.service. h713-hdmi-video.service is not
# enabled: the udev rule pulls it in while the signal is locked or holding.
# H713_ROOT prefixes every path (offline tests only).
set -eu
mode=install
dry=0
for arg in "$@"; do
    case "$arg" in
        --update) mode=update ;;
        --dry-run) dry=1 ;;
        --remove) mode=remove ;;
        *) echo 'Usage: install-hdmi-video.sh [--dry-run] [--update] | --remove' >&2; exit 2 ;;
    esac
done
[ "$mode" != remove ] || [ "$dry" = 0 ] || { echo 'install-hdmi-video: --remove has no dry run' >&2; exit 2; }
cd "$(dirname "$0")"
R=${H713_ROOT:-}
target=$R/usr/lib/h713-hdmi-video
units=$R/etc/systemd/system
rules=$R/etc/udev/rules.d
backups=$R/var/lib/h713-hdmi-video
die() { echo "install-hdmi-video: $*" >&2; exit 1; }
say() { echo "install-hdmi-video: $*"; }

[ "$(id -u)" = 0 ] || [ -n "$R" ] || die 'run as root'
grep -q 'HY200 QZ713DF_A1' "$R/proc/device-tree/model" || die 'not the HY200 board'

if [ "$mode" = remove ]; then
    systemctl disable --now h713-hdmi-ring.service 2>/dev/null || true
    systemctl stop h713-hdmi-video.service 2>/dev/null || true
    rm -f "$units/h713-hdmi-ring.service" "$units/h713-hdmi-video.service" \
        "$rules/71-h713-hdmi-in.rules"
    rm -rf "$target"
    systemctl daemon-reload
    udevadm control --reload
    lsmod | grep -q '^h713_hdmi_v4l2 ' && die 'bridge still loaded after removal'
    say "removed; console only. Backups kept in $backups"
    exit 0
fi

sha256sum -c --quiet SHA256SUMS || die 'bundle checksums'
for f in h713-hdmi-v4l2.ko 71-h713-hdmi-in.rules h713-hdmi-ring.service \
         h713-hdmi-video.service install-hdmi-video.sh; do
    grep -q "  $f\$" SHA256SUMS || die "SHA256SUMS lacks $f"
done
kernel=$(uname -r)
case "$(modinfo -F vermagic ./h713-hdmi-v4l2.ko)" in
    "$kernel "*) ;;
    *) die "module vermagic does not match the running kernel $kernel" ;;
esac
command -v gst-launch-1.0 >/dev/null || die 'gst-launch-1.0 missing'
gst-inspect-1.0 v4l2src >/dev/null || die 'v4l2src missing'
gst-inspect-1.0 kmssink >/dev/null || die 'kmssink missing'
[ -f "$units/h713-hdmi-signal.service" ] || die 'signal owner not installed'
[ -f "$units/h713-hdmi-capture.service" ] || die 'capture owner not installed'
for f in "$R/run/udev/rules.d/71-h713-hdmi-in.rules" \
         "$R/run/systemd/system/h713-hdmi-ring.service" \
         "$R/run/systemd/system/h713-hdmi-video.service"; do
    [ ! -e "$f" ] || die "runtime staging present ($f): run stage-hdmi-video.sh unstage"
done
installed=0
if [ -e "$target/SHA256SUMS" ]; then
    installed=1
    (cd "$target" && sha256sum -c --quiet SHA256SUMS) || die 'installed generation fails its checksums'
    for f in h713-hdmi-ring.service h713-hdmi-video.service; do
        cmp -s "$target/$f" "$units/$f" || die "installed $f differs from its recorded copy"
    done
    cmp -s "$target/71-h713-hdmi-in.rules" "$rules/71-h713-hdmi-in.rules" ||
        die 'installed rule differs from its recorded copy'
    if [ "$mode" != update ] && ! cmp -s SHA256SUMS "$target/SHA256SUMS"; then
        die 'a different generation is installed: use --update'
    fi
elif lsmod | grep -q '^h713_hdmi_v4l2 '; then
    die 'the bridge is loaded but not installed (a bench run?): rmmod it first'
fi

if [ "$dry" = 1 ]; then
    say "dry run OK: would $([ $installed = 1 ] && echo 'replace the installed generation' || echo 'install') into $target, $units, $rules"
    exit 0
fi

if [ "$installed" = 1 ] && [ "$mode" = update ]; then
    install -d -m 0755 "$backups"
    backup=$(mktemp -d "$backups/backup.XXXXXX")
    cp -a "$target/." "$backup/"
    say "previous generation backed up to $backup"
fi
# Stop the old consumer first (the console returns), then the bridge.
for u in h713-hdmi-video.service h713-hdmi-ring.service; do
    if [ "$(systemctl show "$u" -p LoadState --value)" != not-found ]; then
        systemctl stop "$u"
    fi
done
install -d -m 0755 "$target" "$units" "$rules"
install -m 0644 h713-hdmi-v4l2.ko 71-h713-hdmi-in.rules h713-hdmi-ring.service \
    h713-hdmi-video.service SHA256SUMS "$target/"
install -m 0755 install-hdmi-video.sh "$target/"
[ ! -f stage-hdmi-video.sh ] || install -m 0755 stage-hdmi-video.sh "$target/"
install -m 0644 h713-hdmi-ring.service h713-hdmi-video.service "$units/"
install -m 0644 71-h713-hdmi-in.rules "$rules/"
systemctl daemon-reload
udevadm control --reload
systemd-analyze verify "$units/h713-hdmi-ring.service" "$units/h713-hdmi-video.service"
systemctl enable --now h713-hdmi-ring.service
sha256sum "$target/h713-hdmi-v4l2.ko" "$units/h713-hdmi-ring.service" \
    "$units/h713-hdmi-video.service" "$rules/71-h713-hdmi-in.rules"
say 'installed; the panel follows the HDMI signal. Revert: sh /usr/lib/h713-hdmi-video/install-hdmi-video.sh --remove'
