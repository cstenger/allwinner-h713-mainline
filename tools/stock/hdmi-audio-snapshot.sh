#!/system/bin/sh
# Stock Android, read-only via hidtvreg-read. Never read receiver/wrapper MMIO.
# The audio offsets below are the status/control words already sampled by
# h713-hdmi-audio-probe. No FIFOs, DMA payloads, writes or IRQ clearing.
set -eu
T=${T:-/data/local/tmp/cap}
R=$T/hidtvreg-read
label=${1:-idle}
case "$label" in *[!a-zA-Z0-9_-]*|'') echo 'invalid label' >&2; exit 2;; esac
d=$T/audio/$label
mkdir -p "$d"
cat /proc/uptime > "$d/uptime"
cat /proc/interrupts > "$d/interrupts"

reg() {
    line=$($R "$1" 1)
    set -- $line
    case ${2:-} in 0x*) printf '%d\n' "$2";; *) exit 1;; esac
}
bit() { [ $(( ($1 >> $2) & 1 )) -eq 1 ]; }
domain_on() { [ $(( ($1 >> 16) & 3 )) -eq 1 ]; }

# Always-on power and clock status first. Fail closed before peripheral reads.
tvfe=$(reg 070010a4)
tvcap=$(reg 07001124)
demod=$(reg 02001d64)
bus=$(reg 02001d80)
rx=$(reg 02001d84)
cpu=$(reg 02001d48)
umac=$(reg 02001d4c)
ihb=$(reg 02001d50)
printf 'tvfe=%s tvcap=%s demod=%s bus=%s rx=%s cpu=%s umac=%s ihb=%s\n' \
    "$tvfe" "$tvcap" "$demod" "$bus" "$rx" "$cpu" "$umac" "$ihb" > "$d/gates.txt"

# Vendor gate descriptors establish HDMI-audio bit 31, cap-300m bit 30.
# See docs/hdmi-tvcap-clock-validation.md; the older bit-0 model is superseded.
if domain_on "$tvfe" && domain_on "$tvcap" && \
    bit "$demod" 0 && bit "$demod" 16 && bit "$bus" 31 && bit "$bus" 30 && \
    bit "$rx" 31 && bit "$cpu" 31 && bit "$umac" 31 && bit "$ihb" 31; then
    for address in 06146000 06146004 06146008 06146010 \
        06146034 06146038 0614603c 06146048 0614604c \
        06148100 06148104 0614810c 06148110 06148114 \
        06148384 06148388 0614838c 06148390 \
        0614a000 0614a00c 06142044; do
        $R "$address" 1 >> "$d/audio-registers.txt"
    done
else
    echo 'SKIPPED peripheral reads: power/clock/reset gate failed' > "$d/audio-registers.txt"
fi

# Read firmware objects from the host using read-hdmi-audio-cache.py, which
# follows guarded live pointers. Android allocations differ from Linux.
echo "$d"
