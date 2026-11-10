# EDID signal with U-Boot-preselected source 2

After a physical power cycle, the dedicated-trace U-Boot initialized the
authenticated board-B MIPS firmware, and one direct `THal_Vp_SetSource(2)`
returned in about 1 ms. The guarded trace reported callback `0x5102`, worker
`0x5203`, event 0, new 2, old 0, and queue result 0. The one-time 0132 FIT
booted Linux 6.18.38 #1 built September 23 09:41:06 PDT. Its corrected DTB
reserved the trace page and bound the EDID-clock consumer. The EDID module
held its clock at 24 MHz and released reset; TVFE and TVCAP stayed on.
The installed kernel and persistent environment were unchanged.

The first 10-second SCP HPD/EDID trial used `--stock-io`. SCP reported HPD
high and restored its state, but the host connector stayed disconnected.
The default IO profile then worked in two 15-second trials: the GPU read the
same 128-byte EDID (SHA256
`0812e13a13f9d6f84aca26f136c1a55f5bcb03fb8f24a93c107f3c5f96f89290`)
and enabled 640×480 output about 1.7 seconds after HPD assertion. The second
successful trial had `hy310-hdmird-callback --no-src` running; it completed
the stock pre-source initialization and stayed responsive. A hot-plug callback
appeared before that trial began, but no new callback was logged during its
signal window. Both SCP trials restored their peripheral state and released
DDC pins. The MIPS trace canaries stayed intact and Linux remained responsive.

In a further 20-second default-profile window, the host again enabled video.
Read-only samples of THDMIRX registers `+0x7c`, `+0x84`, `+0xc8`, `+0x150`,
`+0x27c`, `+0x580`, `+0x58c`, and `+0x808` were identical before, twice during,
and after the window. These raw values do not establish receiver lock; the
Synopsys register layout in the local kernel differs from the H713 peer
layout, so their status-bit names cannot safely be imported wholesale.

The read-only `THal_Vp_GetSource_1_000` RPC returned one word, `0`, after
the full Linux-side VP initialization. Two more queries returned `0` while
the GPU was actively transmitting in a final 12-second window. These calls
do **not** reveal the current source: the exact board-B firmware handler at
`0x8b14b524` unconditionally sets its return register to zero at
`0x8b14b5b0`. U-Boot's source-2 trace proves the transition completed before
Linux, but its continuity through VP initialization is still unknown. The
existing HY310 port documentation identifies **HDMI1 as source 3**; source 2
was a MIPS transition control and did not select the attached HDMI input.
We did not call `SetSource` under Linux because earlier calls hard-locked the
projector. `/dev/video0` is the Cedrus
memory-to-memory decoder, and there is no HDMI V4L2 capture node. No receiver
lock, DMA frame, or captured pixel has been demonstrated.

Files here include normalized boot, U-Boot, trial, trace, and daemon logs.
`rx-status.log` records the four read-only THDMIRX snapshots, and
`live-getsource.log` records the three read-only RPCs and the static proof
that their zero return cannot measure current source. The trial directories
contain host DRM observations, target SCP state, receiver power
checks, and cleanup logs. All bounded trials exited successfully.
