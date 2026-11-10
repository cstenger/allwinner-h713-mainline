#!/bin/sh
# Board speaker route: resolve the Codec ALSA card by identity, not index.
set -eu
control=
for path in /sys/class/sound/card*/id; do
    [ "$(cat "$path")" = Codec ] || continue
    [ -z "$control" ] || { echo 'Multiple Codec cards; refusing mixer setup' >&2; exit 1; }
    card=${path%/id}; card=${card##*/card}
    control=/dev/snd/controlC$card
done
[ -n "$control" ] || { echo 'Codec ALSA card not found' >&2; exit 1; }
export CTL="$control"
ctl=/usr/lib/h713-hdmi-speaker/alsa-ctl
# Full-scale HDMI at codec gain 63 overdrives this board's speaker amplifier.
# 43 was audibly clean at 100% source volume (~23 dB below the old setting).
"$ctl" set 'DAC Playback Volume' 43
"$ctl" set 'Line Out Playback Volume' 15
"$ctl" set 'Line Out Playback Switch' 1 1
"$ctl" set 'Speaker Switch' 1
