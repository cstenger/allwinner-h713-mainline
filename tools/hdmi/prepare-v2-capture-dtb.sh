#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Prepare the opt-in V2 HDMI test DTB offline. U-Boot supplies the live handoff.
set -euo pipefail

if [[ $# != 2 ]]; then
    echo "Usage: bash $0 V2_BASE_DTB OUTPUT_DTB" >&2
    exit 2
fi

base=$1
output=$2
if [[ -e $output || -L $output ]]; then
    echo "Output already exists: $output" >&2
    exit 1
fi

if [[ $(fdtget -t s "$base" / compatible) != 'cstenger,hy200-qz713-v2 allwinner,sun50i-h713' ]]; then
    echo 'Expected a HY200 QZ713 V2 Linux DTB' >&2
    exit 1
fi
if [[ $(fdtget -t u "$base" /soc/audio-bridge@203042c interrupts) != '0 115 4 0 113 4' ]]; then
    echo 'Unexpected HDMI audio bridge and AudIf IRQ order' >&2
    exit 1
fi
if [[ $(fdtget -t u "$base" /reserved-memory '#address-cells') != 1 ||
      $(fdtget -t u "$base" /reserved-memory '#size-cells') != 1 ]]; then
    echo 'Unexpected V2 reserved-memory layout' >&2
    exit 1
fi

# The guarded HDMI startup owns this fixed trace range. Reject overlap with
# any reservation already carried by the selected slot's DTB.
trace_start=0x4d980000
trace_end=0x4d9c0000
children=$(fdtget -l "$base" /reserved-memory)
while IFS= read -r child; do
    [[ -n $child ]] || continue
    if regs=$(fdtget -t u "$base" "/reserved-memory/$child" reg 2>/dev/null); then
        read -ra cells <<< "$regs"
        for ((i = 0; i < ${#cells[@]}; i += 2)); do
            start=${cells[i]}
            size=${cells[i+1]}
            if ((start < trace_end && start + size > trace_start)); then
                echo "HDMI trace range overlaps /reserved-memory/$child" >&2
                exit 1
            fi
        done
    fi
done <<< "$children"

here=$(cd "$(dirname "$0")" && pwd)
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
cp -- "$base" "$scratch/base.dtb"

# The boot FIT is built without -@. Supply its clock controller symbols on
# a copy of the base for the overlay's external references.
ccu=/soc/clock-controller@2001000
r_ccu=/soc/clock-controller@7010000
if [[ $(fdtget -t s "$base" "$ccu" compatible) != allwinner,sun50i-h713-ccu ||
      $(fdtget -t s "$base" "$r_ccu" compatible) != allwinner,sun50i-h713-r-ccu ]]; then
    echo 'Expected the H713 main and always-on clock controllers' >&2
    exit 1
fi
fdtput -p -t s "$scratch/base.dtb" /__symbols__ ccu "$ccu"
fdtput -p -t s "$scratch/base.dtb" /__symbols__ r_ccu "$r_ccu"

dtc -@ -I dts -O dtb -o "$scratch/capture.dtbo" "$here/v2-capture.dtso"
fdtoverlay -i "$scratch/base.dtb" -o "$scratch/candidate.dtb" "$scratch/capture.dtbo"
(set -o noclobber; cat "$scratch/candidate.dtb" > "$output")
