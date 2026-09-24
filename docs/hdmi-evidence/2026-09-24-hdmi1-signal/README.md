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
A guarded trace of the `0x8b253578` branch would distinguish an absent VP
callback from one that runs but fails to transition.

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
