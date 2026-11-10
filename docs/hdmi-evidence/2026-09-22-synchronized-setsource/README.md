# Synchronized sustained-input SetSource trial, 2026-09-22

This trial removed the timing ambiguity from the preceding controller test.
The SCP asserted HPD at target uptime `132.111731`. The callback-capable daemon
opened its MIPS callback channel at `134.717773`, only 2.606 seconds later, and
therefore had roughly 27 seconds of the 30-second assertion remaining.

The host GPU changed from disconnected to connected in 1.502 seconds, read the
same 128-byte EDID (SHA256
`0812e13a13f9d6f84aca26f136c1a55f5bcb03fb8f24a93c107f3c5f96f89290`),
then enabled one of the two advertised 640x480 modes at 1.814 seconds.

On the target, TVFE and TVCAP were active, all four receiver clocks were held,
the Synopsys controller initialization was still present, and every
stock-equivalent pre-source RPC returned. The daemon entered
`THal_Vp_SetSource(3)` and received a live
`HdmiHotPlugByPortHandler(port=1)` callback. SetSource did not return. The last
kernel diagnostic was a five-second CPU_COMM RETURN timeout for session
`0x16`; SSH reset and subsequent SSH, ping, and serial input produced no
response.

This establishes a sustained live-input failure inside or downstream of the
MIPS source-change path. It is not explained by late daemon startup, expired
HPD, missing EDID, missing callback delivery, gated TVFE/TVCAP, or an
uninitialized `0x050c0000` controller block. Do not repeat the same trial
without MIPS source-worker instrumentation.

Files:

- `source.json`: timestamped host connector transitions.
- `edid-0812e13a13f9d6f8.bin`: exact EDID presented during the trial.
- `receiver.log`: target power, clocks, and safe THDMIRX register reads.
- `daemon.log`: full initialization, SetSource entry, and hot-plug callback.
- `target.log`: SCP helper connection loss when the target stopped.
- `cleanup.log`: expected cleanup timeout after the lock.
- `serial-boundary.log`: serial timestamps at HPD, callback-channel creation,
  callback delivery, and the final CPU_COMM timeout.
