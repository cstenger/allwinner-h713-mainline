#!/bin/sh
# Offline test of install-hdmi-video.sh in a fake root (HDMI panel-source
# design 10.26, stage 5). System commands are stubs that log their calls;
# every refusal case also checks that the fake root's file tree did not
# change, so a guard test can never hide a write.
#
#   test-install-hdmi-video.sh BUNDLE_DIR
set -eu
BUNDLE=$(cd "${1:?BUNDLE_DIR}" && pwd)
W=$(mktemp -d)
trap 'rm -rf "$W"' EXIT
fails=0
pass() { echo "ok   $1"; }
fail() { echo "FAIL $1"; fails=$((fails + 1)); }

# --- stubs ---
mkdir -p "$W/bin"
cat > "$W/bin/systemctl" <<'EOF'
#!/bin/sh
echo "systemctl $*" >> "$H713_ROOT/calls"
if [ "$1" = show ]; then
	[ -f "$H713_ROOT/etc/systemd/system/$2" ] && echo loaded || echo not-found
fi
exit 0
EOF
cat > "$W/bin/udevadm" <<'EOF'
#!/bin/sh
echo "udevadm $*" >> "$H713_ROOT/calls"
EOF
cat > "$W/bin/systemd-analyze" <<'EOF'
#!/bin/sh
echo "systemd-analyze $*" >> "$H713_ROOT/calls"
EOF
cat > "$W/bin/modinfo" <<'EOF'
#!/bin/sh
echo "${FAKE_VERMAGIC:-6.18.38 SMP mod_unload aarch64}"
EOF
cat > "$W/bin/uname" <<'EOF'
#!/bin/sh
echo 6.18.38
EOF
cat > "$W/bin/gst-inspect-1.0" <<'EOF'
#!/bin/sh
[ "$1" = kmssink ] && [ -n "${FAKE_NO_KMSSINK:-}" ] && exit 1
exit 0
EOF
cat > "$W/bin/gst-launch-1.0" <<'EOF'
#!/bin/sh
exit 0
EOF
cat > "$W/bin/lsmod" <<'EOF'
#!/bin/sh
echo "Module Size Used by"
[ -n "${FAKE_LOADED:-}" ] && echo "h713_hdmi_v4l2 28672 0"
exit 0
EOF
chmod +x "$W/bin/"*
export PATH="$W/bin:$PATH"

fresh() {	# a fake board root with the signal and capture owners installed
	rm -rf "$W/root" "$W/bundle"
	mkdir -p "$W/root/proc/device-tree" "$W/root/etc/systemd/system"
	printf 'HY200 QZ713DF_A1\0' > "$W/root/proc/device-tree/model"
	touch "$W/root/etc/systemd/system/h713-hdmi-signal.service" \
		"$W/root/etc/systemd/system/h713-hdmi-capture.service"
	cp -a "$BUNDLE" "$W/bundle"
	export H713_ROOT="$W/root"
}
tree() { (cd "$W/root" && find . -path ./calls -prune -o -type f -print | sort | xargs -r sha256sum; find . | sort) | sha256sum; }
run() { sh "$W/bundle/install-hdmi-video.sh" "$@" > "$W/out" 2>&1; }
resum() { (cd "$W/bundle" && sha256sum h713-hdmi-v4l2.ko 71-h713-hdmi-in.rules h713-hdmi-ring.service \
	h713-hdmi-video.service install-hdmi-video.sh stage-hdmi-video.sh > SHA256SUMS); }
refuses() {	# NAME PATTERN ARGS...: must exit nonzero, print PATTERN, write nothing
	name=$1 pat=$2
	shift 2
	before=$(tree)
	if run "$@"; then fail "$name: accepted"; return; fi
	grep -q "$pat" "$W/out" || { fail "$name: wrong reason: $(tail -1 "$W/out")"; return; }
	[ "$(tree)" = "$before" ] || { fail "$name: wrote files"; return; }
	pass "$name"
}
installed_ok() {
	for f in usr/lib/h713-hdmi-video/h713-hdmi-v4l2.ko etc/systemd/system/h713-hdmi-ring.service \
		 etc/systemd/system/h713-hdmi-video.service etc/udev/rules.d/71-h713-hdmi-in.rules; do
		cmp -s "$W/root/$f" "$W/bundle/$(basename "$f")" || return 1
	done
	grep -q 'systemctl enable --now h713-hdmi-ring.service' "$W/root/calls" &&
		! grep -q 'enable.*h713-hdmi-video' "$W/root/calls"
}

fresh
before=$(tree)
if run --dry-run && grep -q 'dry run OK: would install' "$W/out" && [ "$(tree)" = "$before" ]; then
	pass "dry run on a clean board writes nothing"
else fail "dry run: $(cat "$W/out")"; fi

if run && installed_ok; then pass "first install: files match the bundle, ring enabled, video not enabled"
else fail "first install: $(tail -3 "$W/out")"; fi

if run && installed_ok; then pass "identical reinstall accepted"; else fail "identical reinstall"; fi

echo '# changed' >> "$W/bundle/h713-hdmi-video.service"; resum
refuses "different generation without --update" 'use --update'
refuses "plain dry run of a different generation" 'use --update' --dry-run
if run --dry-run --update && grep -q 'replace the installed generation' "$W/out"; then pass "dry run of --update sees the replacement"
else fail "dry run update: $(tail -1 "$W/out")"; fi
old_unit=$(sha256sum < "$W/root/etc/systemd/system/h713-hdmi-video.service")
if run --update && installed_ok && b=$(ls -d "$W/root/var/lib/h713-hdmi-video/backup."*) &&
   [ "$(sha256sum < "$b/h713-hdmi-video.service")" = "$old_unit" ]; then
	pass "--update installs and backs up the previous generation"
else fail "--update: $(tail -3 "$W/out")"; fi

echo '# tampered' >> "$W/root/etc/systemd/system/h713-hdmi-ring.service"
refuses "installed unit differs from its recorded copy" 'differs from its recorded copy' --update

fresh
FAKE_VERMAGIC='6.18.39 SMP mod_unload aarch64' refuses "module built for another kernel" 'vermagic'
FAKE_NO_KMSSINK=1 refuses "kmssink missing" 'kmssink missing'
FAKE_LOADED=1 refuses "bench bridge loaded, nothing installed" 'rmmod it first'
mkdir -p "$W/root/run/udev/rules.d"; touch "$W/root/run/udev/rules.d/71-h713-hdmi-in.rules"
refuses "runtime staging present" 'unstage'
fresh
echo x >> "$W/bundle/h713-hdmi-v4l2.ko"
refuses "corrupted bundle" 'bundle checksums'
fresh
rm "$W/root/etc/systemd/system/h713-hdmi-capture.service"
refuses "capture owner not installed" 'capture owner'
fresh
printf 'Other board\0' > "$W/root/proc/device-tree/model"
refuses "another board" 'not the HY200'

fresh
run
if run --remove && [ ! -e "$W/root/usr/lib/h713-hdmi-video" ] &&
   [ ! -e "$W/root/etc/systemd/system/h713-hdmi-ring.service" ] &&
   [ ! -e "$W/root/etc/systemd/system/h713-hdmi-video.service" ] &&
   [ ! -e "$W/root/etc/udev/rules.d/71-h713-hdmi-in.rules" ] &&
   grep -q 'systemctl disable --now h713-hdmi-ring.service' "$W/root/calls"; then
	pass "--remove disables and removes everything"
else fail "--remove: $(tail -2 "$W/out")"; fi

echo "installer test $([ $fails = 0 ] && echo passed || echo "FAILED ($fails)")"
[ "$fails" = 0 ]
