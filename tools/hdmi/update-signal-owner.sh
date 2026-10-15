#!/bin/sh
# Run on target from a complete build-startup.py bundle. Replaces ONLY the
# signal owner files (signal module, DDC helper, wrapper, the shutdown hold
# guard and its systemd-shutdown copy, the fresh-install script) plus this
# script and SHA256SUMS. Refuses unless every other installed file is
# byte-identical to the bundle, so the U-Boot script, receiver/audio modules, units and firmware
# are never touched. A loaded owner keeps running its in-memory module; the
# new files take effect on the next cold boot. Never stops or starts units.
set -eu
cd "$(dirname "$0")"
I=${H713_HDMI_INSTALL:-/usr/lib/h713-hdmi}
S=${H713_HDMI_STATE:-/var/lib/h713-hdmi-startup}
M=${H713_HDMI_SYSMODULE:-/sys/module}
H=${H713_HDMI_SHUTDOWN_HOOKS:-/usr/lib/systemd/system-shutdown}
SCOPE='h713-hdmi-signal.ko h713-ddc-pins.ko h713-hdmi-signal.py h713-hdmi-hold-guard install-startup.sh update-signal-owner.sh'
in_scope() { case " $SCOPE " in *" $1 "*) return 0;; esac; return 1; }
die() { echo "$*; nothing changed" >&2; exit 1; }
[ -n "${H713_HDMI_INSTALL:-}" ] || [ "$(id -u)" = 0 ] || die 'run as root'
sha256sum -c --quiet SHA256SUMS || die 'bundle checksum mismatch'
[ -d "$I" ] && [ -d "$S" ] && [ -d "$H" ] || die 'no installed startup generation'
# Out-of-scope files must match their own record; scope files may be from an
# interrupted earlier run, which this run simply completes.
(cd "$I" && awk -v scope=" $SCOPE " 'index(scope, " " $2 " ") == 0' SHA256SUMS | sha256sum -c --quiet) ||
  die 'installed generation fails its own checksums'
# A failed owner is retaining holds for a cold cycle; leave its files alone.
if [ -d "$M/h713_hdmi_signal" ]; then
  [ "$(cat "$M/h713_hdmi_signal/parameters/failed")" = N ] || die 'loaded signal owner has failed'
fi
awk '{print $2}' SHA256SUMS | while read -r f; do
  in_scope "$f" && continue
  [ "$f" = SHA256SUMS ] && continue
  cmp -s "$f" "$I/$f" || { echo "installed $f differs from bundle; refusing signal-owner-only update; nothing changed" >&2; exit 1; }
done
current=1
for f in $SCOPE; do cmp -s "$f" "$I/$f" 2>/dev/null || current=0; done
cmp -s h713-hdmi-hold-guard "$H/h713-hdmi-hold-guard" 2>/dev/null || current=0
if [ $current = 1 ] && cmp -s SHA256SUMS "$I/SHA256SUMS"; then echo 'Signal owner already current'; exit 0; fi
B=$(mktemp -d "$S/signal-owner.$(date +%Y%m%dT%H%M%S).XXXXXX")
for f in $SCOPE SHA256SUMS; do [ ! -e "$I/$f" ] || cp -a "$I/$f" "$B/"; done
[ ! -e "$H/h713-hdmi-hold-guard" ] || cp -a "$H/h713-hdmi-hold-guard" "$B/shutdown-hook.h713-hdmi-hold-guard"
for f in $SCOPE; do
  mode=0644; case $f in *.sh|h713-hdmi-hold-guard) mode=0755;; esac
  [ ! -e "$I/$f" ] || mode=$(stat -c %a "$I/$f")
  install -m $mode "$f" "$I/$f.new"
  sync
  cmp "$f" "$I/$f.new"
  mv "$I/$f.new" "$I/$f"
done
# Executed by systemd-shutdown; a copy, so it never depends on the bundle path.
install -m 0755 h713-hdmi-hold-guard "$H/h713-hdmi-hold-guard.new"
sync
cmp h713-hdmi-hold-guard "$H/h713-hdmi-hold-guard.new"
mv "$H/h713-hdmi-hold-guard.new" "$H/h713-hdmi-hold-guard"
install -m 0644 SHA256SUMS "$I/SHA256SUMS.new"
sync
mv "$I/SHA256SUMS.new" "$I/SHA256SUMS"
sync
(cd "$I" && sha256sum -c --quiet SHA256SUMS)
echo "Signal owner updated for the next cold boot; previous files kept in $B"
