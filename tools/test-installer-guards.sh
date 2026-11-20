#!/usr/bin/env bash
# End-to-end check that the installers refuse the wrong board before writing.
#
#   tools/test-installer-guards.sh
#
# Puts fake `fastboot` and `ssh` first on PATH. They answer as the bench or
# the projector (identity from boards/*/board.env, boot0 synthesised) and log
# every call that would write. Each installer must refuse the projector with
# no write logged, and get past the guard on the bench (positive control).
# Touches no board. The UMS tools (split-udisk.sh, reclaim-android.sh) need a
# root block device and are covered by tools/test-board-guard.py's --dev cases.
set -uo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin"
fails=0

# Synthetic stock boot0 images (type/clock as in each board.env).
python3 -I - "$T" <<'EOF'
import struct, sys
for name, typ, clk in (('a1', 3, 624), ('v2', 7, 720)):
    d = bytearray(32768)
    d[4:12] = b'eGON.BT0'
    struct.pack_into('<I', d, 16, 32768)
    struct.pack_into('<I', d, 0x14, 0x30)
    struct.pack_into('<II', d, 0x38, clk, typ)
    struct.pack_into('<I', d, 12, 0x5F0A6C39)
    struct.pack_into('<I', d, 12, sum(struct.unpack('<8192I', d)) & 0xffffffff)
    open(f'{sys.argv[1]}/boot0-{name}.bin', 'wb').write(d)
EOF

cat > "$T/bin/fastboot" <<'EOF'
#!/usr/bin/env bash
if [ "$1" = getvar ] && [ "$2" = serialno ]; then
	echo "serialno: $FAKE_SERIAL" >&2; exit 0
fi
echo "fastboot $*" >> "$FAKE_LOG"; exit 0
EOF
cat > "$T/bin/ssh" <<'EOF'
#!/usr/bin/env bash
cmd=${*: -1}
case "$cmd" in
*device-tree/compatible*) printf '%s\0allwinner,sun50i-h713\0' "$FAKE_COMPAT" ;;
*"dd if=/dev/mmcblk0"*)
	skip=$(sed -n 's/.*skip=\([0-9]*\).*/\1/p' <<<"$cmd")
	if [ "$skip" = 16 ]; then cat "$FAKE_BOOT0"; else head -c 512 /dev/zero; fi ;;
*) echo "ssh $cmd" >> "$FAKE_LOG"; exit 1 ;;   # anything else counts as a write attempt
esac
EOF
chmod +x "$T/bin/fastboot" "$T/bin/ssh"
export PATH="$T/bin:$PATH" FAKE_LOG="$T/log"

as_board() {  # a1|v2
	local id; [ "$1" = a1 ] && id=hy200-qz713df-a1 || id=hy200-qz713-v2
	FAKE_SERIAL=$(sed -n 's/^UBOOT_SERIAL=//p' "$ROOT/boards/$id/board.env")
	FAKE_COMPAT=$(sed -n 's/^DT_COMPATIBLE=//p' "$ROOT/boards/$id/board.env")
	FAKE_BOOT0="$T/boot0-$1.bin"
	export FAKE_SERIAL FAKE_COMPAT FAKE_BOOT0
	: > "$FAKE_LOG"
}

expect() {  # name  board  want(refused|passed)  cmd...
	local name=$1 board=$2 want=$3; shift 3
	as_board "$board"
	"$@" > "$T/out" 2>&1; local rc=$?
	local writes; writes=$(wc -l < "$FAKE_LOG")
	local refused=no; grep -q 'REFUSED' "$T/out" && refused=yes
	local ok=no
	if [ "$want" = refused ]; then
		[ "$refused" = yes ] && [ "$writes" -eq 0 ] && [ "$rc" -ne 0 ] && ok=yes
	else
		grep -q 'confirmed' "$T/out" && [ "$refused" = no ] && ok=yes
	fi
	printf '%s %-50s board=%s rc=%s writes=%s\n' "$([ $ok = yes ] && echo PASS || echo FAIL)" "$name" "$board" "$rc" "$writes"
	[ $ok = yes ] || { fails=$((fails + 1)); sed 's/^/    | /' "$T/out" | tail -8; }
}

FIT="$ROOT/build/out/h713-kernel.fit"
KO=$(find "$ROOT"/build/linux-*/drivers/staging/media/sunxi/cedrus -name sunxi-cedrus.ko -print -quit 2>/dev/null)

expect "flash-standalone.sh refuses the projector" v2 refused "$ROOT/tools/flash-standalone.sh" "$FIT"
expect "flash-standalone.sh passes the bench"       a1 passed  "$ROOT/tools/flash-standalone.sh" "$FIT"
expect "boot-switch.sh install refuses the projector" v2 refused "$ROOT/tools/boot-switch.sh" install --via fastboot
expect "boot-switch.sh install passes the bench"      a1 passed  "$ROOT/tools/boot-switch.sh" install --via fastboot
expect "boot-switch.sh install refuses V2 even if H713_BOARD=v2" v2 refused env H713_BOARD=hy200-qz713-v2 "$ROOT/tools/boot-switch.sh" install --via fastboot
expect "install-kernel-fit.sh refuses the projector" v2 refused "$ROOT/tools/install-kernel-fit.sh" "$FIT"
expect "install-kernel-fit.sh passes the bench"      a1 passed  "$ROOT/tools/install-kernel-fit.sh" "$FIT"
expect "install-kernel-fit.sh H713_BOARD=v2 passes V2" v2 passed env H713_BOARD=hy200-qz713-v2 "$ROOT/tools/install-kernel-fit.sh" "$FIT"
if [ -n "$KO" ]; then
	expect "install-kernel-module.sh refuses the projector" v2 refused "$ROOT/tools/install-kernel-module.sh" "$KO" sunxi-cedrus
	expect "install-kernel-module.sh passes the bench"      a1 passed  "$ROOT/tools/install-kernel-module.sh" "$KO" sunxi-cedrus
else
	echo "SKIP install-kernel-module.sh (no built sunxi-cedrus.ko)"
fi

[ "$fails" -eq 0 ] && echo "all installer guard checks passed" || echo "$fails installer guard check(s) FAILED"
exit $((fails > 0))
