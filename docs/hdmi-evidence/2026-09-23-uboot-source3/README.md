# One guarded U-Boot HDMI1 source-3 call

The host GPU connector was disconnected before the test. After the owner's
physical power cycle, the projector booted its normal installed kernel. The
installed U-Boot-proper sectors still matched the validated padded-image
SHA256 `935a1b33c59f501cab498232d24108c548d941256958366792d29a9a30f0d526`.
The CP210x UART became accessible, and a warm reboot stopped at the installed
dedicated-trace U-Boot prompt. U-Boot authenticated the exact board-B MIPS
firmware (SHA256 `4380f1b3ed7b62aa50582e7cb16a87bdface1b4300578fe3631a416354da30ce`)
and installed the guarded trace at `0x4d980000`. Its channel table showed the
live channel 0, PID `0x8b8f275c`. Before the call, the source trace contained
the firmware startup transition `0 -> 1` with callback `0x5102`, worker
`0x5203`, and queue result zero.

One direct `THal_Vp_SetSource(3)` call used U-Boot's `commcall eaf13de5
chan=0 pid=8b8f275c 3`. U-Boot observed `CALL_ACK` and `RETURN` after 0 ms,
with `nret=0`, and published `RETURN_ACK` to the interrupt handler after 1 ms.
The MIPS sender did **not** complete RETURN during the following 1-second
wait. U-Boot explicitly preserved the unreconciled `ReturnCmd` and
`FreeReturn` state. It stayed at a responsive prompt. The immediate and a
later read-only trace snapshot both showed no instrumented CPU_COMM stage and
only the earlier source-1 callback/worker markers; neither showed a source-3
worker transition. `commstate` showed one pending `ReturnCmd` on CPU0/dir1 and
one consumed `FreeReturn` slot there. No further CPU_COMM call was attempted.

The already-validated one-time 0132 FIT then booted Linux 6.18.38 #1 built
September 23 09:41:06 PDT. Its image hashes passed, TVCAP was retained, and
the CPU_COMM module was deliberately left unloaded. The Linux trace reader
verified 22 patch words and both `0x43414e31` canaries. Its event/new fields
later held event 1 and pointer `0x8b25357c`, which are not a source-3 result;
the source callback/worker fields remained at their earlier source-1 markers.
The independent MIPS debug shell answered `cmds` with 917 bytes. SSH and UART
remained responsive, and the kernel logged no Oops or panic.

This is a source-selection failure boundary even without an asserted HDMI
signal. `RETURN` arrival alone is not proof that source 3 became active:
the return handshake remained incomplete and no source-3 worker completion
was observed. The next experiment should instrument the MIPS sender's
RETURN_ACK/wakeup path and private source state before another source-3 call.
The installed kernel, SPL, and persistent U-Boot environment were unchanged.

Later evidence changed the interpretation of the 1-second timeout: U-Boot had
read a cached trace-page zero. A cache-coherent repeat observed the sender
complete and verified that the SetSource adapter received source 3. See
[`2026-09-24-cache-coherent-source3`](../2026-09-24-cache-coherent-source3/).

The adjacent files are whitespace-normalized copies of the UART and SSH
captures in ignored `build/`.
