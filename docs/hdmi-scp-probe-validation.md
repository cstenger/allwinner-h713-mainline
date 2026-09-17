# SCP startup and HPD read probe results

2026-09-17, board A, transient corrected-CCU kernel #2.
The owner explicitly approved the bounded SRAM-marker test and, separately,
the SCP-side HPD read. Automatic review initially blocked each operation;
both were executed only after the respective approval.

## SRAM mapping resolved experimentally

Putting instructions directly at ARM 0x00100100 failed instruction readback:
0x00100104 remained 0x15000000 instead of the proposed ORI. Aligned 64-bit
writes did not fix it. Moving the program to 0x00100120 returned all zeros.
Those guards stopped before SCP reset release; restoration checks passed.

The stock image's entire first 0x4000 bytes contain only sparse vector
jump/NOP stubs and zeros. SRAM A2 at 0x00104000 instead contained the leftover
ARM SPL header and executable instructions. The successful probe placed
code at ARM 0x00104100 and set the reset vector to jump to SCP address 0x4100.
It saved/restored the first A2 page and changed vector words.

Target output at uptime 734.805814:

```text
h713-scp-probe: marker=48444d49 restored=1 reset=00000000 result=0
```

This proves SCP execution and the ARM/SCP address relationship for these
locations. Writing the numeric OR1K instruction words through ARM little-
endian MMIO worked, and the SCP's numeric marker read back unchanged. It does
not prove a full stock loader, mailbox protocol, or peripheral access.

## Fixed SCP-side HPD read

The added payload wrote the startup marker, loaded address 0x07091014,
attempted one LWZ, and would then store a snapshot plus completion marker.
ARM never accessed that address. No HPD or receiver writes were performed.

Target output at uptime 836.698759:

```text
hpd_read=1 marker=48444d49 completed=0 hpd=00000000 restored=1 reset=00000000 result=-110
```

The read did not complete within the polling deadline. The zero HPD field
is not a register value. ARM cleanup remained responsive and restored the
backups, with the core held in reset. An exception-reporting revision then
produced no startup/exception/completion marker, and a SRAM-only run also
failed to produce its marker. This is consistent with a lingering SCP bus
transaction, but does not prove its cause or rule out a reset-path problem.
SSH and TVFE/TVCAP remained active. No SCP probe was left loaded.

## Stock HPD handler checked against this blob

Board-A SCP SHA256:
`93adf8a90fb190fc567fafcccbc5959e6514aa8cff6d4a6ed15981f08666dfa1`.

The handler actually begins at 0x121f4 in this image; the peer's 0x121e4 is
in the previous function's epilogue. It reads 0x07091014 at 0x12258 and
writes it at 0x12328. Port selection loads a byte from a runtime table at
0x17258 + 8*port + 2. That byte selects hardware bit 0, 1, or 2. The table
is initially zero in the file, so physical connector-to-bit mapping must be
recovered from initialization, not assumed from the logical port number.

The low-level handler sets the selected bit when its fourth argument is
zero, and clears it otherwise (after its configuration-dependent branch).
The higher handler at 0x12340 also implements counters/reset behavior, so
this observation alone does not define electrical HPD polarity or a safe
replacement command protocol.

The OR1K opcode checks used the primary architecture encoding table:
https://openrisc.io/or1k.html . No vendor firmware binary is committed.

## Controlled restart recovered the execution path

A normal ARM reboot, stopped at U-Boot, followed by the same one-time test FIT
boot recovered SCP execution. The final exception-reporting module's default
SRAM-only test passed:

```text
hpd_read=0 marker=48444d49 completed=1 hpd=00000000 exception=0 restored=1 reset=00000000 result=0
```

TVFE/TVCAP holds were restored, and both tested R_CCU EDID registers read zero:
0x07010120 = 0, 0x07010124 = 0. The vendor R_CCU table contains an EDID clock
and reset absent from our D1-derived provider. Their verification is the next
clock investigation; a register read must not be retried just because the SCP
is now able to execute. Host HDMI remains disconnected with zero-byte EDID.

## HPD access resolved with the missing EDID resources

Patch 0124 and a removable consumer enabled R_CCU EDID reset/clock. The
same approved SCP-side HPD read then completed twice, returning 7, with
no exception and restoration verified. Unload restored both resources
to zero. See [the EDID clock validation](hdmi-edid-clock-validation.md).
The earlier timeout describes the resources-off state and is superseded
for this specifically validated read. ARM HPD access was not retried.
