# MIPS continuity with TVCAP retained from boot

On 2026-09-22, private kernel #5 tested whether the MIPS failure at TVCAP
power-on came from the transition or the active domain. Retaining TVCAP from
U-Boot through Linux kept the MIPS scheduler, shell, and CPU_COMM alive.

## Diagnostic image

Patch 0126 adds opt-in `allwinner,keep-tvcap-on` support to the H713 PPU
driver. The private board DT enabled it. `GENPD_FLAG_ALWAYS_ON` prevents
generic power-domain sync from turning off U-Boot's TVCAP state.

- Kernel: Linux 6.18.38 #5 SMP Tue Sep 22 14:02:09 PDT 2026
- FIT: `/root/fits/h713-mips-early-tvcap.fit`
- FIT SHA256: `0beecad60219f9216075ff85e0e435a5312dc1e37a11ccc056d6907792f73208`
- Volatile addition: `initcall_blacklist=h713_afbd_platform_driver_init`
- Normal boot image and persistent environment: unchanged

The flashed U-Boot `h713_disp mips-stability 0x34` command verified the exact
firmware and guarded patch sites. Its 60-second self-test advanced 1007-1008
ticks per second with no general or cache exception. The Linux reader
`tools/mips/read-witness.py` verifies all 34 patch words before reading the
mailbox.

## Retained-domain result

Linux logged `TVCAP domain retained from boot`; genpd reported TVCAP `on`, and
the physical control/status values were `00000001` / `00010000`. Over ten
seconds the ThreadX timer advanced from 169910 to 179911 with no exception.
The MIPS shell returned 917 bytes, and GetSource completed in 74576 us.

Acquiring TVFE and four receiver clock references preserved this state. TVFE
and TVCAP both reported `on`; a 12-second witness advanced continuously, the
shell returned 917 bytes, and GetSource completed in 74961 us. TVCAP can remain
active. Powering it off and back on while MIPS runs is the failing operation.

## Source and MIPS initialization

The validated SCP EDID/DDC trial detected the GPU on its second cold-start
assertion. It read the exact 128-byte EDID (SHA256
`0812e13a13f9d6f84aca26f136c1a55f5bcb03fb8f24a93c107f3c5f96f89290`),
listed two 640x480 modes, and enabled output in 1.653 seconds. Cleanup passed.

`THal_Vp_Init(0, 0, 0x4e700000)` returned `ret0=1` in 74480 us. Stock HDMI
port maps `(1,0)`, `(2,1)`, `(3,2)` and the 200 ms HPD interval completed.
The timer continued and no exception was recorded.

## Live SetSource failure boundary

During a new 30-second signal window, the GPU detected the same EDID and
enabled 640x480. One `THal_Vp_SetSource(3)` call began for HDMI1, but no result
returned. SSH closed; subsequent SSH and ping timed out, and serial produced
no bytes. The last remote output is CALL_BEGIN with component `eaf13de5`.

This is broader than the earlier reversible MIPS-only stall. Target-side
witness and elog files could not be recovered, so the mechanism is unresolved.
Do not repeat live SetSource with only the minimal init calls. A future attempt
should reproduce the full stock HDMI initialization with callback registration
or isolate the remaining prerequisite offline first.

Evidence: [`hdmi-evidence/2026-09-22-early-tvcap`](hdmi-evidence/2026-09-22-early-tvcap/).
