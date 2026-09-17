#!/usr/bin/env bash
# Run on the H713 target. Default is sysfs/debugfs only.
set -euo pipefail

read_thdmirx=0
case "${1:-}" in
  '') ;;
  --read-thdmirx) read_thdmirx=1 ;;
  *) echo 'usage: check-power.sh [--read-thdmirx]' >&2; exit 2 ;;
esac

uname -a
cat /sys/kernel/debug/pm_genpd/pm_genpd_summary
awk '$1 ~ /^(bus-tvcap|bus-cap-300m|bus-hdmi-audio|vincap-dma|tvfe-1296m|tcd3|hdmi-audio)$/ {print}' \
  /sys/kernel/debug/clk/clk_summary

if (( read_thdmirx )); then
  # Presence alone does not prove active PM ownership: check both hold devices.
  test -d /sys/module/h713_hdmi_power || {
    echo 'Refusing THDMIRX reads: power-hold module is not loaded.' >&2
    exit 1
  }
  for domain in tvfe tvcap; do
    state=$(cat "/sys/devices/h713-hdmi-$domain/power/runtime_status")
    test "$state" = active || {
      echo "Refusing THDMIRX reads: $domain hold is $state." >&2
      exit 1
    }
  done
  awk '
    $1 ~ /^(bus-tvcap|bus-cap-300m|vincap-dma|tvfe-1296m)$/ {
      count++
      if ($2 < 1 || $3 < 1) bad=1
    }
    END {exit (count != 4 || bad)}
  ' /sys/kernel/debug/clk/clk_summary || {
    echo 'Refusing THDMIRX reads: expected clock references are missing.' >&2
    exit 1
  }
  reader=$(command -v mmio-rw || true)
  if [[ -z "$reader" && -x /root/mmio-rw ]]; then reader=/root/mmio-rw; fi
  test -n "$reader" || { echo 'mmio-rw is unavailable.' >&2; exit 1; }
  # Each read has a flushed marker; stop on the first failure. These are the
  # eight registers validated in experiment 0087 and the 2026-09-17 load test.
  for address in 50c0000 50c0004 50c0008 50c000c 50c0010 50c0014 50c0018 50c001c; do
    printf 'THDMIRX_READ_BEGIN %s\n' "$address"
    "$reader" r "$address"
    printf 'THDMIRX_READ_END %s\n' "$address"
  done
fi
