# TVCAP bus gate correction and transient boot validation

2026-09-17, board A, HY200 QZ713DF_A1.

## Evidence and change

Patch 0125 changes CCU register 0xd80 bus-hdmi-audio from bit 0 to bit 31,
and bus-cap-300m from bit 1 to bit 30. The vendor ARM32 kernel has full
symbols: bus_hdmi_audio_clk at 0xc14618e0 contains mask 0x80000000;
bus_cap_300M_clk at 0xc1461894 contains 0x40000000. Both descriptors
contain register offset 0xd80. ccu_gate_enable at 0xc05675dc loads the
mask and passes it to ccu_gate_helper_enable. Stock fastlogo independently
writes 0xc0000000. This establishes the two mappings, rather than guessing
from that combined value.

Local vendor vmlinux SHA256:
`3e0d2d3420e066277021fe78d8398eff3937afdaf00c3625354becfbc398bc04`.
Extracted offline from the owner's 20250922 OTA; no vendor binary is committed.

## Build and one-time boot

The owner's physical power cycle recovered SSH and serial. A private kernel
copy was patched, then `make ARCH=arm64 LLVM=1 -j4 Image dtbs` completed.
Patch dry-run against the untouched source also passed with `--fuzz=0`.
The test FIT was staged as `/root/fits/h713-hdmi-clock-test.fit` and booted
once via serial/U-Boot ext4load and bootm. No boot image was flashed, normal
boot selection was unchanged, and no persistent U-Boot environment was saved.

FIT SHA256:
`9d192145615332a62fb464c641ffb40323fc7c422c18cae48306106ec22a97fc`.

Test kernel: `6.18.38 #2 SMP Thu Sep 17 15:56:19 PDT 2026`.
The normal image remains `#1 SMP Wed Sep 16 00:16:22 PDT 2026`.
Boot transcript: local `/tmp/h713-hdmi-clock-test-boot.log` (not committed).

## Hardware result

The removable power module loaded successfully on the test kernel. All four
held clocks showed 1/1 prepare/enable counts and hardware enabled Y.
TVFE and TVCAP were on and both hold devices active.

| Operation | 0x02001d80 | TVFE/TVCAP |
|---|---|---|
| Module loaded | 0xc0000000 | on / on |
| Module removed | 0x80000000 | off / off |
| Module reloaded | 0xc0000000 | on / on |

The cap-300m bit now follows the consumer's reference. The audio bit was
already set at boot and was not acquired by this power module. Two removal/
reload cycles completed. The eight whitelisted THDMIRX words remained
readable with their earlier values. SSH, LVDS connector registration, and
the codec card remained available; playback quality was not tested.

## Limits and current state

This fixes a real clock definition bug, but does not prove the cause of the
wrapper lock. Following the physical power cycle, the unpatched boot already
had 0xc0000000 in hardware, despite its incorrect framework interpretation.
No wrapper or 0x07091014 ARM access was retried.

At the end of this validation, the temporary #2 kernel was running and the
power module was loaded from /tmp. Nothing was installed in the module tree.
An ordinary restart restores the normal image and drops the temporary hold.
The host HDMI output still lacked sink detection/EDID in the earlier test;
receiver lock and captured buffers have not been demonstrated.
