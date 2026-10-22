uname -a
cat /proc/sys/kernel/random/boot_id /proc/cmdline /proc/sys/kernel/panic
dmesg -n 7
cat /sys/kernel/h713_dsp_retention/state
systemctl is-active h713-hdmi-capture h713-hdmi-signal h713-hdmi-speaker
