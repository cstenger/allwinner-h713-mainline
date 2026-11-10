#!/bin/sh
# Run on target from a build-readvertise.py bundle. Installs the HPD re-advertise
# owner: replaces the signal module, adds h713-hdmi-readvertise.py and its unit,
# rewrites only those SHA256SUMS entries, and retires the 0 ms start-delay and
# re-advertise bench drop-ins. Refuses unless every other installed file matches
# its own checksum and the installed signal module is the pinned predecessor (or
# already this one). Never starts or stops units; takes effect on the next boot.
set -eu
cd "$(dirname "$0")"
I=${H713_HDMI_INSTALL:-/usr/lib/h713-hdmi}
S=${H713_HDMI_STATE:-/var/lib/h713-hdmi-startup}
M=${H713_HDMI_SYSMODULE:-/sys/module}
U=${H713_SYSTEMD_UNITS:-/etc/systemd/system}
SYSTEMCTL=${H713_SYSTEMCTL:-systemctl}
# The signal module installed 2026-10-14 (update-signal-owner.sh, commit 7f0ee60).
PREVIOUS=0a6987ced911cc12f2a36ff2a9550e397c1c0f5889f4b65e8453b298cefe4497
SCOPE='h713-hdmi-signal.ko h713-hdmi-readvertise.py h713-hdmi-readvertise.service'
UNIT=h713-hdmi-readvertise.service
DROPINS=$U/h713-hdmi-signal.service.d
RETIRE='90-start-delay.conf 95-readvertise-bench.conf'
in_scope() { case " $SCOPE " in *" $1 "*) return 0;; esac; return 1; }
die() { echo "$*; nothing changed" >&2; exit 1; }
[ -n "${H713_HDMI_INSTALL:-}" ] || [ "$(id -u)" = 0 ] || die 'run as root'
sha256sum -c --quiet SHA256SUMS || die 'bundle checksum mismatch'
[ -d "$I" ] && [ -d "$S" ] && [ -d "$U" ] || die 'no installed startup generation'
# Scope entries may be from an interrupted earlier run, which this run completes.
(cd "$I" && awk -v scope=" $SCOPE " 'index(scope, " " $2 " ") == 0' SHA256SUMS | sha256sum -c --quiet) ||
  die 'installed generation fails its own checksums'
installed=$(sha256sum "$I/h713-hdmi-signal.ko" | cut -d' ' -f1)
[ "$installed" = "$PREVIOUS" ] || cmp -s h713-hdmi-signal.ko "$I/h713-hdmi-signal.ko" ||
  die 'installed signal module is not the pinned predecessor'
# A failed owner is retaining holds for a cold cycle; leave its files alone.
if [ -d "$M/h713_hdmi_signal" ]; then
  [ "$(cat "$M/h713_hdmi_signal/parameters/failed")" = N ] || die 'loaded signal owner has failed'
fi
sums() {
  awk -v scope=" $SCOPE " 'index(scope, " " $2 " ") == 0' "$I/SHA256SUMS"
  for f in $SCOPE; do sha256sum "$f"; done
}
current=1
for f in $SCOPE; do cmp -s "$f" "$I/$f" 2>/dev/null || current=0; done
cmp -s $UNIT "$U/$UNIT" 2>/dev/null || current=0
for d in $RETIRE; do [ ! -e "$DROPINS/$d" ] || current=0; done
sums | sort -k2 | cmp -s - "$I/SHA256SUMS" || current=0
if [ $current = 1 ]; then echo 'Re-advertise owner already current'; exit 0; fi
B=$(mktemp -d "$S/readvertise.$(date +%Y%m%dT%H%M%S).XXXXXX")
cp -a "$I/SHA256SUMS" "$B/"
for f in $SCOPE; do [ ! -e "$I/$f" ] || cp -a "$I/$f" "$B/"; done
[ ! -e "$U/$UNIT" ] || cp -a "$U/$UNIT" "$B/unit.$UNIT"
for d in $RETIRE; do [ ! -e "$DROPINS/$d" ] || cp -a "$DROPINS/$d" "$B/dropin.$d"; done
for f in $SCOPE; do
  install -m 0644 "$f" "$I/$f.new"
  sync
  cmp "$f" "$I/$f.new"
  mv "$I/$f.new" "$I/$f"
done
install -m 0644 $UNIT "$U/$UNIT.new"
sync
cmp $UNIT "$U/$UNIT.new"
mv "$U/$UNIT.new" "$U/$UNIT"
sums | sort -k2 > "$I/SHA256SUMS.new"
sync
mv "$I/SHA256SUMS.new" "$I/SHA256SUMS"
(cd "$I" && sha256sum -c --quiet SHA256SUMS)
for d in $RETIRE; do rm -f "$DROPINS/$d"; done
sync
$SYSTEMCTL daemon-reload
$SYSTEMCTL enable $UNIT
echo "Re-advertise owner installed for the next boot; previous files kept in $B"
