# Missing R_CCU EDID clock and reset

2026-09-17. Patch 0124 describes an H713-specific R_CCU variant with inherited
clock/reset IDs, plus CLK_R_EDID=11 and RST_R_EDID=7. The D1 tables remain
unchanged. This provider patch does not enable the peripheral automatically.

## Offline evidence

The full-symbol vendor kernel (SHA256
3e0d2d3420e066277021fe78d8398eff3937afdaf00c3625354becfbc398bc04)
contains r_apb0_edid_clk at 0xc146549c, size 108 bytes:

| Field | Value |
|---|---|
| Enable mask | 0x80000000 |
| M divider | shift 0, width 5 |
| P divider | shift 8, width 2 |
| Source mux | shift 24, width 2 |
| Register | 0x124 |

Its parent-name table at 0xc0e961f4 contains dcxo24M, osc32k, iosc,
pll-periph0. These match the firmware names hosc/losc/iosc/pll-periph
already supplied to our R_CCU node. sun50iw12_r_ccu_resets at 0xc1464fbc
contains the reset mapping 0x120 / 0x00010000 as its second entry.

Board-A SCP initialization at 0x12100 also writes 0 to 0x07010120,
waits through its delay helper, writes 0x00010000, and writes 0x80000000
to 0x07010124. This independently establishes a concrete setup sequence.
The live projector has both registers zero after the normal boot chain.
The prior D1 provider described neither resource.

## Prepared test

A removable clock/reset consumer is described only in the private test DTS.
Both kernel Image/dtbs and the out-of-tree consumer module compiled cleanly.
Patch dry-run against independent untouched baseline files passed with
--fuzz=0; modified binding YAML parses successfully. Full dt_binding_check
has not been run.

One-time FIT staged as /root/fits/h713-hdmi-edid-test.fit, SHA256:
2fdb850382b2190d1a35f4a2726208470e82b3a60394cf9cbce59b0236aca100.
Normal boot image, persistent U-Boot selection, and Claude's files are unchanged.
## Hardware validation

Test kernel: 6.18.38 #3 SMP Thu Sep 17 16:24:17 PDT 2026.
The provider registered r-edid at 24 MHz with hardware enabled N and no
references; both registers remained zero until the test module was loaded.
Its platform device bound successfully. Load produced:

- 0x07010120 = 0x00010000 (reset released).
- 0x07010124 = 0x80000000 (module clock enabled).
- r-edid clock prepare/enable 1/1 and hardware enabled Y at 24 MHz.

With TVFE/TVCAP also held, the previously approved fixed SCP-side HPD read
completed, returning 0x00000007. No exception was reported, and the A2 page
and vector words were restored with SCP reset held. Target output:

```text
hpd_read=1 marker=48444d49 completed=1 hpd=00000007 exception=0 restored=1 reset=00000000 result=0
```

After removing the SCP probe and EDID hold, both R_CCU registers returned to
zero. Reloading the hold and repeating the HPD read again succeeded with the
same value and restoration checks. This establishes that enabling these two
resources together resolves the observed SCP-side HPD access failure. It
does not separate which resource is necessary, prove ARM reachability, or
explain the earlier 0x068xxxxx wrapper fault.

Current target: transient #3 kernel, removable TVFE/TVCAP and EDID holds on;
SCP reset held, with no stock SCP firmware loaded. The successful probe module
is inert until removed. No HPD, EDID, GPIO, or wrapper writes were performed.
Source detection and readable EDID are still pending.
