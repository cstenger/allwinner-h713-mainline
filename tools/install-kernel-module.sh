#!/usr/bin/env bash
# Install one freshly built in-tree module on the board, and reload it. RUNS ON THE HOST.
#
# WHY THIS EXISTS, and it is not convenience. cedrus, the AFBD KMS driver and
# the scanout exporter are MODULES: a patch to any of them does not reach the
# board by flashing a kernel FIT, because the FIT carries only the Image. That
# is easy to forget and expensive to forget -- this board was found running a
# sunxi-cedrus.ko that predated two patches which had been in
# patches/kernel/series for weeks, with /sys/module/sunxi_cedrus/ carrying no
# parameters directory at all, which is what gave it away.
#
# It also means a module fix can be tested WITHOUT a reboot, which is the
# cheaper and safer loop: the only route to this board is its own WiFi AP, so a
# kernel that fails to bring up the network is a trip to the bench.
#
# The reload is only attempted when nothing has the device open. A module in
# use is left installed but not loaded, and the script says so rather than
# forcing anything.
#
#   usage: tools/install-kernel-module.sh <tree-or-ko-path> [module-name]
#          tools/install-kernel-module.sh build/linux-6.18.38-<hash> sunxi-cedrus
#          tools/install-kernel-module.sh path/to/sunxi-cedrus.ko
set -euo pipefail

SRC=${1:?usage: install-kernel-module.sh <tree-or-ko-path> [module-name]}
NAME=${2:-sunxi-cedrus}
BOARD=${BOARD:-192.168.4.1}
SSH="ssh -o ConnectTimeout=5 root@$BOARD"
STAMP=$(date +%Y%m%d-%H%M%S)

if [ -d "$SRC" ]; then
	KO=$(find "$SRC" -name "$NAME.ko" -print -quit)
	[ -n "$KO" ] || { echo "error: no $NAME.ko under $SRC" >&2; exit 1; }
else
	KO=$SRC
fi
[ -r "$KO" ] || { echo "error: cannot read $KO" >&2; exit 1; }

MOD=${NAME//-/_}
sum=$(md5sum "$KO" | cut -d' ' -f1)
echo "==> $KO ($(stat -c%s "$KO") bytes, md5 $sum) -> $BOARD as $MOD"

# vermagic must match the RUNNING kernel, not the one that happens to be on the
# FAT. Checking here turns a silent "module verification failed" at modprobe
# time into a refusal with both strings side by side.
want=$($SSH 'uname -r')
have=$(modinfo -F vermagic "$KO" 2>/dev/null | awk '{print $1}')
[ "$have" = "$want" ] || {
	echo "error: module is for $have, board runs $want" >&2
	exit 1
}

scp -o ConnectTimeout=5 "$KO" "root@$BOARD:/tmp/$NAME.ko.new" >/dev/null

$SSH "set -e
	got=\$(md5sum /tmp/$NAME.ko.new | cut -d' ' -f1)
	[ \"\$got\" = '$sum' ] || { echo 'error: upload corrupted'; exit 1; }

	dst=\$(modinfo -n $MOD 2>/dev/null || true)
	if [ -z \"\$dst\" ]; then
		echo 'error: $MOD is not in the board module tree; refusing to guess a path'
		exit 1
	fi

	cp \"\$dst\" /root/\$(basename \$dst).$STAMP.bak
	echo \"    backed up \$dst -> /root/\$(basename \$dst).$STAMP.bak\"
	cp /tmp/$NAME.ko.new \"\$dst\"
	rm -f /tmp/$NAME.ko.new
	depmod -a

	if lsmod | grep -q '^$MOD '; then
		users=\$(awk '/^$MOD /{print \$3}' /proc/modules)
		if [ \"\$users\" != '0' ]; then
			echo \"    installed, NOT reloaded: $MOD is in use by \$users\"
			exit 0
		fi
		rmmod $MOD
	fi
	modprobe $MOD
	sleep 1
	# Record what is installed so drift is detectable. A stale module that
	# still loads is this project's most expensive silent failure.
	sed -i '/^kernel_module_/d' /etc/h713-video-stack 2>/dev/null || true
	{
		echo "kernel_module_md5=$sum"
		echo "kernel_module_installed=$STAMP"
	} >> /etc/h713-video-stack
	echo '    loaded; parameters now exposed:'
	for p in /sys/module/$MOD/parameters/*; do
		[ -e \"\$p\" ] || { echo '      (none)'; break; }
		echo \"      \$(basename \$p) = \$(cat \$p)\"
	done"
