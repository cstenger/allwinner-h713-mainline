# Cache-coherent U-Boot HDMI1 source-3 control

The board cold-booted the owner's installed Linux 6.18.38 #1 kernel built
September 23 at 20:57:37 PDT. SSH, UART, and the Cedrus `/dev/video0` node
were healthy. The host GPU's HDMI connector reported `disconnected`, so this
test did not assert an HDMI signal.

The preceding U-Boot source-3 trace had reported a 1-second RETURN timeout and
zeros in all CPU_COMM and SetSource adapter markers, despite receiving
`CALL_ACK` and `RETURN`. U-Boot read the trace page with plain `readl` after a
pre-call `commtrace` had populated ARM's cache. The MIPS writes the same page
through an uncached alias. A later Linux read of that very test verified the
patched instructions and both page canaries and found `c013` (RETURN sender
finished), `e011` (CALL dispatcher returned), `f003` (RETURN_ACK wrapper
returned), and adapter `5302` with requested source 3. This supports stale ARM
cache data, rather than a stalled MIPS sender, as the cause of U-Boot's timeout
report. It does not prove when each MIPS stage executed.

The revised U-Boot invalidates the trace cache lines before a trace snapshot
and on every RETURN-completion poll. Its 404 patch words passed exact-image
guards against board-B `display.bin` SHA256
`4380f1b3ed7b62aa50582e7cb16a87bdface1b4300578fe3631a416354da30ce`;
the 60 trace-base and 72 trace-store relocation counts matched. The rebuilt
FIT U-Boot-proper was 920,169 bytes. Only the established 1,798 sectors at
LBA `0x49ac00` were written; read-back matched padded-image SHA256
`6395d30973f82d4bb5c5344840520da851f7a72429035e94bad638ec54f69f16`.
The previous sectors were backed up. SPL, environment, and kernel were outside
the write range.

After a warm reboot to the verified U-Boot prompt, one
`h713_disp mips-comm-trace 0x34` run authenticated the firmware and installed
the trace. A pre-call `commtrace` intentionally populated ARM's cache, matching
the earlier failing sequence. One `THal_Vp_SetSource(3)` RPC then received
`CALL_ACK` and `RETURN` and observed the MIPS sender complete RETURN in the
first poll. U-Boot consumed `ReturnCmd` and recycled `FreeReturn`; no transport
slot was left unreconciled. The immediate read-only trace showed `c013`,
`e011`, `f003`, and adapter `5302` with requested source 3.

The source callback and worker markers remained `5102` and `5203`, the prior
startup source-1 transition. Event/new fields held event 1 and a pointer, not
source 3. The RPC and adapter return establish that the call reached the
firmware; they do **not** establish that the source worker selected HDMI1, that
the receiver locked, or that any capture frame exists. No second diagnostic
MIPS run or CPU_COMM call was made on this power cycle.

The board booted its installed kernel afterward. Because that kernel does not
reserve the diagnostic trace page, a normal reboot then cleared the temporary
MIPS instrumentation. The same September 23 20:57:37 kernel came back with SSH,
UART, and Cedrus `/dev/video0`; no Oops or panic appeared in the checked log.
The owner's video-decode kernel and modules were not written by this test.
