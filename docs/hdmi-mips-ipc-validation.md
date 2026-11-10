# MIPS IPC receiver diagnostic

2026-09-18. The normal source-detection tests run with MIPS stopped. To begin
receiver control, the target was gracefully restarted and U-Boot's existing
`h713_disp init 0x34` performed full loading and handshake, leaving MIPS out of
reset. This is the previously successful route, not raw core release from
Linux. The exact image matches local board-B display.bin SHA256
4380f1b3ed7b62aa50582e7cb16a87bdface1b4300578fe3631a416354da30ce.
Its disassembler base/stub self-test passed.

The same #3 FIT booted with volatile
`initcall_blacklist=h713_afbd_platform_driver_init`; boot logs confirm the
blacklist. Linux reached its root shell and SSH with no captured oops/BUG.
No normal image or persistent environment was changed. MIPS status at
0x0306101c read 1. The CPU_COMM module adopted the live shared region;
force_init was not used. Both magics were deadbeef and CPU flags stayed 5.
TVFE/TVCAP and EDID holds were active before the IPC tests.

## Functional result

This route did not reproduce the earlier successful diagnostic interface:

- Shell `cmds`, `help hal`, and `help elog` produced no reply.
- Down-ring write offset reached 24 while read offset stayed 0.
- Up-ring write offset stayed at the eight startup clear-screen bytes.
- A read-only GetSource RPC resolved live ID 24efc7c9 but timed out after
  2044774 microseconds, errno 62. The driver reported ACK timeout; TX FIFO
  became 1. No mutating source-selection or Vp_Init RPC was sent.
- Ready flags and out-of-reset status therefore do not prove an executing
  scheduler or a working receiver-control interface.

The target remained responsive through ARM serial/SSH. It was gracefully
rebooted into the original stopped-MIPS #3 test route, and source detection
passed again. No raw core-release retry, wrapper access, or persistent
firmware patch was performed. The initial framework reported MIPS=8MHz;
subsequent vendor-table verification showed its mux order is wrong, so this
is not evidence of the hardware's actual frequency or the timeout's cause.

Evidence: [U-Boot initialization](hdmi-evidence/2026-09-18-mips/uboot-init.log),
[clock/IPC diagnostics](hdmi-evidence/2026-09-18-mips/clock-ipc.log).

Next investigation: establish where execution stops between full U-Boot
readiness and live Linux diagnostics, while verifying receiver clocks and
fabric access. The peer firmware function-name/address list is not universally
reliable: its claimed HDMIRX_SetPortMap entry 8b130c54 disassembles inside an
existing routine in this exact file. Resolve RPC names through the live table
and validate handlers against the matching image before calling them.

## Follow-up isolation

The #4 diagnostic boot reproduces a working 917-byte shell reply before and
after CPU_COMM adoption, plus a read-only RPC round trip. TVFE alone also
works. Adding TVCAP stops shell consumption even with receiver clock enables
skipped; enabling clocks first does not fix it. See
[the resource isolation](hdmi-mips-resource-isolation.md). The earlier test
loaded the full power hold before checking IPC, so its timeout did not locate
the failure at Linux boot or CPU_COMM initialization.
