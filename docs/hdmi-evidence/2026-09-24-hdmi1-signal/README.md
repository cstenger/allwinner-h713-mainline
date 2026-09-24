# HDMI1 source 3 with live GPU signal

After a physical power cycle, the installed cache-coherent U-Boot authenticated
the board-B MIPS firmware, installed the guarded trace once, and sent one
`THal_Vp_SetSource(3)` RPC on the live channel. It received `CALL_ACK` and
`RETURN` in about 1 ms, observed the MIPS RETURN sender complete, consumed
`ReturnCmd`, and recycled `FreeReturn`. The immediate trace showed `c013`,
`e011`, `f003`, and adapter `5302` with requested source 3. The source callback
and worker markers still described the startup source-1 transition, so this
does not independently prove that source 3 became active. No second MIPS
startup or CPU_COMM call was made on this power cycle.

Offline disassembly of this exact SHA256-verified MIPS firmware clarifies the
gap. `THal_Vp_SetSource` at `0x8b14b448` validates the argument, calls the
source-event dispatcher at `0x8b109174`, then stores the request at
`0x8b2729ac`. The dispatcher loads a VP callback object from `0x8b253578`;
if that pointer is zero, it skips the virtual callback and still returns `1`.
The early U-Boot RPC thus can return successfully without queueing a source
event. The unchanged source-worker markers fit this path, but the pointer's
live value was not sampled. The RPC is not proof that HDMI1 was selected.
The exact instruction windows are in `mips-setsource-disassembly.txt`.

The validated 0132 diagnostic FIT booted without changing the installed
kernel. Its trace-page guards read `43414e31/43414e31`; the source adapter
still reported requested source 3. TVFE/TVCAP power holds and the 24 MHz EDID
clock were active. The experimental initializer wrote its sequence at
`0x050c0000`, including an observed `+0x24=0x00203901`. Subsequent comparison
with the board-B MIPS firmware identifies this address as the DETN display
noise-reduction block, so that write cannot be interpreted as enabling HDMI
RX. The initializer has since been disabled. The Linux CPU_COMM module and
daemon `SetSource` path were not loaded or called.

Three 15-second SCP HPD/EDID windows used the default IO profile. In the
first, SCP reported HPD high but the host connector stayed disconnected. In
the next two, the GPU detected the same 128-byte EDID (SHA256
`0812e13a13f9d6f84aca26f136c1a55f5bcb03fb8f24a93c107f3c5f96f89290`)
after about 1.4 seconds and enabled 640x480 after about 1.7 seconds. The
source disconnected after the SCP window ended. All three SCP trials reported
`peripheral_restored=1`, `restored=1`, `edid_mismatch=0`, and their DDC pins
were released. The first missed detection is not yet explained.

Eight read-only words in the DETN window sampled repeatedly across the third,
live video window were constant. In particular, `+0x7c=0`,
`+0x84=0x01000100`, `+0x580=0xff0f0100`, and `+0x808=0x33` before, during,
and after host output. They say nothing about receiver lock or active pixels.
No HDMI capture
V4L2 node or DMA frame has been demonstrated; `/dev/video0` is Cedrus decode.

The projector was rebooted normally into the owner's installed Linux
6.18.38 #1 built September 23 at 20:57:37 PDT. SSH and UART returned,
`sunxi_cedrus` was loaded, `/dev/video0` was named `cedrus`, and the checked
boot log had no Oops or call trace. The diagnostic kernel and modules were
temporary. The next investigation should validate the MIPS source-worker's
actual port selection and receiver/PHY programming while the GPU transmits;
repeating EDID-only trials cannot establish capture.
This motivated a guarded trace of the `0x8b253578` callback-object pointer.

Follow-up on the merged default kernel: the guarded trace captured a non-null
object `0x8b8c8378` at SetSource adapter entry. CALL_ACK, RETURN, and trace
guards passed, but the stage markers did not prove a source-3 worker event.
The exact bounded result and corrected register map are in
[`hdmi-register-map-pointer-trace.md`](../../hdmi-register-map-pointer-trace.md).

A second guarded U-Boot trace after a physical power cycle captured the
dispatcher call target `0x8b107574` with startup source argument 1 before the
RPC and source argument 3 afterward. The source-3 RPC returned and the merged
kernel booted normally; its read-only trace reader verified the patch words,
canaries, and source-3 target. This proves the request reached the virtual
callback call site, but the existing worker markers still do not prove an
HDMI source transition or receiver lock. The exact serial evidence is in
[`dispatch-trace-uart.log`](dispatch-trace-uart.log) and
[`dispatch-trace-uart.raw.gz`](dispatch-trace-uart.raw.gz).

The next one-shot trace resolved the worker gap. Source-3-specific callback,
worker dequeue, and transition-completion counters each changed from 0 to 1
after one CPU_COMM call. The worker recorded old source 0 and new source 3;
the old value is left as observed because the startup source-1 marker does
not explain it. Linux booted normally afterward, and its read-only reader
verified the same trace with intact canaries. The UART evidence is in
[`source3-worker-uart.log`](source3-worker-uart.log) and
[`source3-worker-uart.raw.gz`](source3-worker-uart.raw.gz). This establishes
MIPS-side source selection, while receiver lock and captured frames remain
unproven.

On the updated merged 6.18.38 default kernel, CPU_COMM adopted the already
running MIPS firmware and its read-only `HDMI_GetPortStatus` RPC completed.
The query reads the firmware-owned per-port nibble at physical `0x0684037a`;
it accepts no pointer or input argument. It returned `0` before receiver
holds, then `0x2` with only TVFE and the EDID clock held, while the GPU was
still disconnected. One 15-second SCP HPD/EDID window missed detection. An
identical repeat connected the GPU at 2.18 seconds, delivered the known
128-byte EDID, and enabled 640x480 at 2.46 seconds. Five read-only MIPS
queries during the enabled interval all returned `0x2`; it remained `0x2`
after HPD restoration and disconnect. With TVFE still on, unloading the
EDID-clock module changed the result to `0`; reloading changed it to `0x2`;
unloading again restored `0`. The module changes clock enable and reset
deassertion together, so the bit tracks that combined hold. It does not prove
cable presence or video lock. Both windows reported `peripheral_restored=1`, `restored=1`, and
`edid_mismatch=0`; DDC pins were released. The target stayed responsive on
SSH, CPU_COMM, and the MIPS shell with the merged kernel and Cedrus decoder.
Evidence is in the two `h713-hdmi-trial-20260924T1935*Z` directories. The
TVFE-only hold and CPU_COMM module remain loaded for this
session; neither TVCAP nor receiver clocks were explicitly held by the
diagnostic module, and no HDMI frame was captured. The EDID-clock module was
unloaded after the control, returning the clock/reset to its previous state.

After another physical power cycle, the same U-Boot-proper FIT authenticated
the board-B firmware and a single source-3 RPC again reached `CALL_ACK` and
`RETURN`. The guarded reader reported one source-3 callback, worker dequeue,
and completed transition with intact canaries. The unchanged merged default
kernel then logged `TVCAP domain retained from boot`. CPU_COMM adoption and
the MIPS shell worked at baseline. Acquiring TVFE plus the already-on TVCAP
domain with **zero** diagnostic receiver clocks preserved both interfaces.
Increasing the clock references from zero to four, one at a time, also
preserved shell replies and read-only status RPCs at every step. This current
kernel does not reproduce the older MIPS stall at TVCAP acquisition; the
older test powered TVCAP on, while this kernel retained it from boot.

With all four receiver clocks held and the EDID clock/reset enabled, a
15-second SCP window connected the GPU at 2.13 seconds and enabled 640x480
at 2.42 seconds. The expected EDID hash matched; the MIPS port-status RPC
returned `0x2` before, throughout, and after active video. SCP restoration
passed with no mismatch, and the source-3 trace, MIPS shell, CPU_COMM, SSH,
and Cedrus `/dev/video0` stayed healthy afterward. No receiver lock bit or
captured frame was demonstrated. The optional historical DETN snapshot
helper was absent at `/tmp/h713-check-power.sh`; its failed invocation is
preserved in `receiver.log` and did not affect the signal window or cleanup.
The trial tool now requests that unrelated DETN snapshot only with
`--read-detn`. Evidence is in
[`h713-hdmi-trial-20260924T194648Z`](h713-hdmi-trial-20260924T194648Z/)
and [`tvcap-full-power-uart.raw.gz`](tvcap-full-power-uart.raw.gz)
(raw serial SHA256 `b65f2bfb16ff52e1e192c321420163a6b71884384ee09117635ca96074039397`).

The owner subsequently power-cycled the board. It is back on the same merged
default kernel, with Cedrus loaded, TVCAP retained on, TVFE off, and the
temporary CPU_COMM and HDMI hold modules absent. This boot has not run the
one-shot MIPS source-3 command.

A subsequent DRAM-only inspection on this boot followed the guarded device
manager and receiver pointers to all three HDMI port objects. Their vtables
matched the exact firmware, each link base was `0x06840000`, and each cached
TMDS count was zero with the GPU disconnected. The MIPS core was parked at
`0x0306101c`, so these values are a structural baseline, not a live receiver
measurement. The reader is staged at
`/root/hdmi-safe-trace/read-mips-port-cache.py`; the next bounded signal
trial can sample it before, during, and after GPU output using
`--probe-port-cache` once MIPS is running from a cold U-Boot start.

The older [`hdmi-in.md`](../../hdmi-in.md) HDMI map is contradicted by the
board-B firmware census and [`registers.yaml`](../../re/registers.yaml):
`0x05000000` is display composition, `0x05040000` is a picture-quality tap,
and `0x050c0000` is DETN. The receiver's actual register window remains
unproven. The `0x0680xxxx` wrapper addresses are also hazardous on ARM:
`0x068008f1` returned a bus error and the following `0x068008fc` access
likely locked the board. Validate an address against the exact firmware and
its bus owner before another MMIO probe.

The timestamped trial directories contain host DRM samples, EDID bytes,
receiver power/status checks, SCP logs, and cleanup state. `hdmi1-rx-live`
contains the one-second receiver snapshots across the third window. The
U-Boot source-3 RPC result above was observed live on serial; the serial boot
and restore captures are included here.
