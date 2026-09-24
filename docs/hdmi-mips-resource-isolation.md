# MIPS resource isolation, 2026-09-18

The MIPS debug shell and CPU_COMM work on the #4 private diagnostic kernel.
Communication stops when the removable HDMI hold resumes TVCAP. This narrows
and corrects the earlier undifferentiated IPC timeout; it does not establish
receiver lock, captured frames, or the exact firmware failure mechanism.

**Current-kernel comparison (2026-09-24):** The merged default 6.18.38 kernel
logs that it retained TVCAP on from U-Boot. After a cold U-Boot MIPS/source-3
run, acquiring both domains with zero receiver clocks kept the MIPS shell and
CPU_COMM responsive. Enabling each of the four clocks in turn also kept them
responsive. This does not contradict the earlier power-on stall: the current
run acquired a domain that was already on, while the earlier run resumed a
powered-off TVCAP. A live 640x480 GPU signal then left MIPS responsive, but
receiver lock and capture are still unproved. See
[`2026-09-24-hdmi1-signal`](hdmi-evidence/2026-09-24-hdmi1-signal/README.md).

## Reproduced working route

Graceful ARM reboot, interrupt autoboot, then `h713_disp init 0x34` performs the
full firmware load and ARM/MIPS handshake, leaving MIPS running. Firmware SHA256
is 4380f1b3ed7b62aa50582e7cb16a87bdface1b4300578fe3631a416354da30ce.
Boot /root/fits/h713-hdmi-functional-clocks.fit with volatile
`initcall_blacklist=h713_afbd_platform_driver_init`. The normal image and
persistent U-Boot environment are untouched. Kernel is 6.18.38 #4, Sep 18
00:16:45 PDT; FIT SHA256 f807d7276c2c4d2f78c45d8627e64afde0bf8d1774879604bb20646d99dbc181.

- Before CPU_COMM loads, `cmds` returns 917 bytes and down-ring wr/rd reach 5/5.
- Load the matching /root/hy310-cpu-comm.ko without force_init. It adopts the
  live region; `cmds` again returns 917 bytes, offsets 10/10.
- Read-only GetSource resolves live ID 24efc7c9 and receives CALL_ACK, RETURN,
  and RETURN_ACK in 74722 us. Its zero return is not interpreted as source ID.
- With TVFE alone held on, the shell still answers and the same RPC completes
  in 74495 us. Power notifications confirm TVFE PRE_ON and ON.

U-Boot has no `dcache` command, confirmed on the flashed build. Its cacheable
md/mw commands therefore cannot reliably test this uncached firmware ring;
no ring write was attempted there. Linux aligned /dev/mem accesses provide
the validated functional test. No raw Linux core release was used.

## First failing resource boundary

| Resources added | Shell result | Evidence |
|---|---|---|
| CPU_COMM adoption only | 917-byte reply | after-cpucomm.log |
| Zero-domain, zero-clock diagnostic module | 917-byte reply | tvfe-only.log |
| TVFE only, no clocks | 917-byte reply | tvfe-only.log |
| TVFE + TVCAP, no clocks | No reply; down wr/rd 15/10 | domains-only.log |
| Four receiver clocks before TVFE + TVCAP | No reply; down wr/rd 10/5 | clocks-first.log |

The domain-only test stops before any clock-count increment. CCU d20 stays
zero and all sampled PLL/divider/gate registers are unchanged. It reproduces
the full-hold failure without the EDID module. The clocks-first test enables
d20=80000000 before resume and records PRE_ON/ON for both domains, yet also
stops shell consumption. Hence simply changing the four clock-enable order
does not fix the failure. A zero-resource load also rules out the module load
and obtaining the four clock handles alone as the observed trigger.

Before the last tests, both software domains are off and physical PPU status
is 00020000. TVFE-only changes TVFE to 00010000 while TVCAP remains 00020000;
MIPS remains responsive. Adding TVCAP changes it to 00010000. ARM serial/SSH
remain healthy, and MIPS reset-status remains 1 despite no command consumption.
Neither that reset status nor shared READY flags prove scheduler progress.

The exact mechanism remains open: receiver-thread MMIO/polling, interrupts,
or a firmware exception after TVCAP power-on need an execution witness.
No broad register scan, wrapper access, source-selection RPC, Vp_Init, live
PLL rate change, persistent firmware patch, or flashing was attempted.
Linux uses arch_sys_counter; no evidence currently supports a sun4i-timer
conflict. The kernel Image and relocated DT do not overlap firmware RAM, which Linux reserves.

## Diagnostic helper

The removable hold keeps its normal two-domain/four-clock defaults and gains:
`domain_count=0..2` (TVFE then TVCAP), `clock_count=0..4` with runtime increases
only, and optional `clocks_first=1`. Partial domain holds require zero clocks.
Power notifiers record the generic-domain transition enum. Both domains are
required before runtime clock enabling; decreases and counts above four are
rejected. Partial holds do not authorize receiver MMIO. Do not unload an active
hold under live MIPS; reboot through full U-Boot initialization for a new test.
The zero-resource instance was unloaded safely because it held no PM or clock
references. Module built with Clang/LLD 22.1.8 against the matching private tree;
git diff --check passes. Tested module SHA256
ee12416ccd97706a79dda57151e6cfebb0892d6d01fe0f4d6190e92ad7a6d041.

Evidence is in [the isolation directory](hdmi-evidence/2026-09-18-mips-isolation/).
Final restoration passed: shell cmds returned 917 bytes, GetSource completed
in 74709 us, and help hal returned 63 bytes. Ring down wr/rd is 14/14;
TVFE is on, TVCAP off, SCP reset status zero, and EDID/DDC modules absent.
Only the TVFE-only hold and CPU_COMM are loaded for this workstream. Serial
capture is finished. Target CPU_COMM SHA256 is
60bbddeab6c985607b7feb7e3d2f15d4e98704016ce8773e10a2b52bdb689608;
its whole-file hash differs from the private build, but .text, .init.text,
.rodata and .data have identical sizes/hashes. .modinfo differs. The comparison
is retained with the evidence; this does not claim byte-identical module files. All work stays in
codex/hdmi-capture; Claude's original checkout/build remain untouched.
