# Second-opinion brief: getting a video plane on an Allwinner H713 projector

Self-contained. Assumes no access to our repo. Written to be handed to someone
who knows Allwinner display hardware and might spot something we have missed.

---

## 0. Important correction after stock-HWC reverse engineering (2026-08-26)

> **Further update, 2026-08-31:** legal-value probes show that the AFBD controls
> rejected `0xdeadbeef` but are writable.  Stock's opposite-looking control
> words nevertheless do not reverse the serviced bank: a no-op READY commit on
> stock remained stuck on channel 0 and cleared immediately on channel 1.
> Stock likewise has OSD0 closed, OSD1 open, and only the channel-1 LVDS pair
> populated.  The single-port physical mapping remains an inference, but the
> direct result that channel 0 is unserviced holds on both stacks.  Full record:
> [`reference/afbd-legal-channel-control-tests-2026-08-31.md`](reference/afbd-legal-channel-control-tests-2026-08-31.md).

The original brief's central framing -- that hardware YUV requires opening a
second copy of the working OSD/AFBD channel -- is no longer tenable. Two new
pieces of evidence separate the OSD path we tested from the vendor video path.

### What the photographed patch-0066 result actually proved

Patch 0066 put a 1280x720 NV12 test frame under the live channel while its
source stride remained 5120 bytes (1280 packed pixels x 4 bytes). The panel
showed repeated grey blocks followed by a purple/green band and then unrelated
memory. Those boundaries are diagnostic:

```
NV12 Y bytes:  1280 * 720       / 5120 = 180 displayed rows
NV12 UV bytes: 1280 * 720 / 2   / 5120 =  90 displayed rows
total NV12:                                      270 displayed rows
```

That is what the photograph shows. The hardware was walking the byte stream as
packed 32-bit pixels: luma became the repeated grey pattern and interleaved UV
became purple/green. It did **not** perform YUV-to-RGB. This is strong evidence
that writes to `0x05600011` and the DECD queue registers did not change the
fetch mode of the active OSD source at `0x05600178`.

It does **not** prove that the SoC lacks a no-GPU YUV route. It proves that our
test mixed registers from two different paths.

### Stock Android does submit ordinary video through `/dev/decd`

Disassembly of the shipped, unstripped-enough userspace and kernel binaries
found the consumer that earlier string/immediate searches missed:

- `hwcomposer.ares.so` constructs ioctl `0x40706400` with a split Thumb-2
  `movw #0x6400` / `movt #0x4070` sequence and calls it from
  `DecoderDisplay::present()`.
- `0x40706400` is exactly `DECD_IOC_FRAME_SUBMIT` and encodes a 112-byte frame
  descriptor.
- `VideoTunnel::commitFrameBuffer()` passes an image dma-buf FD, decoder
  format, width/height, and a second dma-buf FD containing `VideoInfo` metadata.
- HWC allocates the metadata dma-buf as 32 KiB and copies a 0x104-byte structure
  to offset 4096. Its magic is `0x61770000`, checked by stock `decd.ko`.
- The uncompressed path is real: HWC's descriptor byte 0 is a compression
  boolean and is zero for ordinary buffers. Stock `decd.ko` then calculates C
  as `Y + height * aligned_stride` for its 8-bit format class.

The simple progressive descriptor produced by stock HWC is:

| offset | value or meaning |
| --- | --- |
| `+0x00` | compressed boolean; `0` for linear video |
| `+0x01` | blue-screen enable; nonzero skips frame creation |
| `+0x04` | image dma-buf FD |
| `+0x08` | decoder format (HWC maps one common video format to `6`) |
| `+0x28/+0x2c` | width / height |
| `+0x40/+0x44/+0x48` | buffer alignment value |
| `+0x4c` | VideoInfo dma-buf FD |
| `+0x50/+0x54` | `0x8000` / `0x10` |
| `+0x64` | `1` for the normal progressive submission |
| `+0x68` | `0`; the stock HWC never selects the legacy/direct branch |

This also found three fatal errors in our reconstructed Linux ABI/client:

1. Our descriptor was 128 bytes, but the ioctl copies exactly 112.
2. HWC places the repeat count at ioctl-wrapper offset `+0x10`; our code used
   `+0x18`, so the vendor enqueue loop received zero.
3. Our client invented `y_phys`/`c_phys` fields beyond byte 112, while our
   reconstructed kernel misread byte `+0x00` as a linear/direct selector.
   Stock uses `+0x00` for compression, leaves its separate `+0x68` legacy
   branch clear, and submits two dma-bufs instead. The invented addresses
   cannot reach the stock ioctl at all.

The metadata check in our port was also wrong (`0x61766b40` rather than the
stock `0x61770000`). These are corrected in kernel patch 0067. The replacement
`decd-client` now builds the same two-dma-buf submission shape as HWC and has
compile-time assertions for the 112-byte ABI. The client passes a strict host
compile and the current 53-patch 6.18.38 stack (including patches 0066 and
0067) builds fully, including `sunxi-decd.ko`.

### Controlled live result: the queue works, but it is not routed (2026-08-26)

The mutually-exclusive patch-0068 boot has now been run. KMS was absent, DECD
alone owned `0x05600000` and SPI 110, and the shared display reset was withheld.
The corrected module bound and accepted the stock-shaped two-dma-buf request:

```
FRAME_SUBMIT format=6 desc=112 repeat@+0x10=1 fence_fd=7
```

This was not a quiet no-op. The DECD IRQ advanced at 59.7 Hz, returned vsync
timestamps were 16.75 ms apart, the frame manager reported sequence 1, and the
four-slot file contained `Y=0x6c500000`, `C=0x6c5e1000` and a valid copied
VideoInfo page. There were no DMA or DECD errors. Panfrost's GPU, job and MMU
interrupt counts remained exactly zero, so this was a genuine no-GPU queue
exercise. The submitted NV12 source was host-decoded separately and is a bright
test pattern, not a black frame.

The panel nevertheless continued to show the U-Boot logo. Hiding its serviced
OSD channel produced black, not the submitted frame. Correcting the inherited
global geometry from 1920x1088/1920-byte stride to 1280x720/1280-byte stride did
not change that result. A stronger discriminator used stock DECD's internal
blue-output control (`workaround + 5` bit 0), which bypasses the YUV buffers and
VideoInfo completely. With blue enabled and the logo channel hidden, the panel
remained black throughout. This proves the failure is routing/topology, not the
synthetic frame contents or metadata. The decisive live register split was:

```
DECD queue:       Y 0x05600070 = 0x6c500000
                  C 0x05600084 = 0x6c5e1000
serviced channel: source 0x05600178 = 0x6c100000 (U-Boot logo)
                  format byte 0x05600011 = 0 (packed OSD)
```

Thus corrected `/dev/decd` submission is necessary but not sufficient. It
queues and clocks the vendor video path, but does not replace or compose into
the already-serviced U-Boot OSD channel.

Stock HWC also identifies the missing companion operation. Its composition
path opens `/dev/ge2d` and issues command **`0x4631`** with an exact **80-byte
`_plane_info`** record. Stock `ge2d_dev.ko` dispatches that command at
`svp_ioctl+0x9a4`, copies 80 bytes, calls `tgd_put_plane_info()` at `0x8ffc`,
and copies the record back with its release fence. This resolves the command
number and payload size that the earlier plane analysis left open. The vendor
runtime therefore uses two coordinated calls: `/dev/decd` supplies video
frames, while `/dev/ge2d`/`tgd_put_plane_info()` configures and commits the
display plane/topology.

> **⚠ The last sentence is wrong and is retracted, same day.**
> `tgd_put_plane_info()` has since been disassembled end to end. Its colour
> format field takes four values, all RGB (32/32/24/16 bpp, written to channel
> `ctrl[15:8]` as `0x19`/`0x19`/`0x17`/`0x18`); it carries one source address
> and no chroma plane; and `ge2d_dev.ko` never touches `0x05600060`–`0x056000ff`
> or writes the mixer at all. `/dev/ge2d`'s whole ioctl table is fbdev-shaped
> OSD management — screeninfo, colour maps, FB allocation, plane flip,
> writeback — with **no video-layer ioctl**. `0x4631` is the RGB OSD flip, which
> `sun50i-h713-afbd` already performs every atomic commit. HWC pairs the two
> calls because it has a UI layer and a video layer to present, which is what a
> hwcomposer does.
>
> The same disassembly produced a better lead, and it is in
> [ge2d-plane-open-re.md](ge2d-plane-open-re.md) under "ioctl `0x4631` is the RGB
> OSD flip": the AFBD writeback engine treats the window as **three** sources
> with a uniform (enable, format, size) interface — `0x05600010` with a *two-bit*
> enable at bits 1:0, `0x05600100`, and `0x05600140`. Source 0 is the video
> source and is exactly what DECD programs. Patch 0066 configured source 0's
> format byte while measuring source 2's fetch, which is why it could not decide
> anything. Nothing we have run, and neither stock driver, sets source 0's enable
> bits; their live value has never been read. The next step is that read, then
> the same read under stock Android playing video.

One more reconstruction bug was found directly in stock `decd.ko` while making
a routing discriminator: `dec_reg_blue_en()` controls `workaround + 5` bit 0,
not `workaround + 16` bit 4. Patch 0013 has been corrected. The old code edited
the low byte of a queued Y address; it happened not to corrupt this test because
that address ended in `0x00` and blue was clear.

**Revised question:** what is the smallest safe port of the `0x4631`
`tgd_put_plane_info()` path that can coexist with DECD under one MMIO/IRQ owner?
The next experiment should reproduce that paired stock transaction, not try
more format/address values on the packed OSD channel.

> **Superseded, same day.** The `0x4631` port is not worth doing — see the
> retraction above. The revised question was: **what sets bits 1:0 of
> `0x05600010`, the video source's enable?**
>
> **Answered 2026-08-26, negative.** Read live: they are `0`. Set to 1, 2 and 3
> with DECD provably submitting at 60 Hz and valid Y/C queued, all readbacks
> taking — **the panel did not change.** Writable, never set, and not
> sufficient.
>
> The real result is next door: `dec_reg_video_channel_attr_config`, the only
> writer of the video source's pixel-format selector, is **dead code in stock
> `decd.ko`** (no relocations reference it; the module exports nothing). So
> **nothing on the ARM side programs the video source's format** — live it reads
> `0`. The configuring component is almost certainly the **MIPS firmware**, fed
> by DECD's VideoInfo dma-buf, and U-Boot parks the MIPS on every boot we have
> tested. That predicts the null and explains the blue-generator null too.
>
> The next experiment is CPU_COMM/VideoInfo — whether the MIPS can be left
> running or restarted with DECD feeding it. Not more AFBD registers.

### Controlled follow-up: ARM submission is stable; visible routing is still absent (2026-08-28)

Later tests supersede the proposed experiment above and narrow the failure
further:

- A diagnostic module bypassed the reconstructed queue/IRQ path, mapped one
  stock-shaped NV12 submission, programmed all four hardware slots directly,
  masked the ARM DECD IRQ, and retained the dma-buf mappings.  With the display
  MIPS stopped, this state is indefinitely stable.  Hardware consumes the
  address/dirty latches, and the held values are `Y=0x6c500000`,
  `C=0x6c5e1000`, plus a valid VideoInfo page.
- Source-0 enable values 1, 2 and 3 at `0x05600010[1:0]` all took but produced
  no visible frame.  Enabling mixer layer 0 (`0x0525c004: 0x1402 -> 0x1403`)
  did not help.
- The corrected internal-blue control (`0x05600065[0]`) also remained black
  with mixer `0x1403`; the fuller firmware-table candidate `0x1003` was
  negative too.  Because internal blue bypasses Y, C, stride, dma-buf and
  VideoInfo, the remaining failure is after DECD's input fetch/format stage.
- TVTOP's live extended route table already exactly matches the authenticated
  firmware/U-Boot values (`0x05700000 = 0xfff11111`, `+0x40 = 0x00011111`,
  `+0x44 = 0x11111111`, `+0x80 = 0x00001111`, `+0x84 = 0xfff000ef`,
  `+0x88 = 0x11111111`).  Replaying `dec_reg_top_enable()` is therefore not a
  missing route-table initialization.
- Releasing the display MIPS under Linux after the ARM configuration did not
  reveal video.  It first reported running and then hard-locked the SoC,
  including Wi-Fi and serial.  The panel stayed black.  This is evidence of
  unsafe shared ownership, not a usable presentation path; another blind MIPS
  restart is not the next experiment.

Static cross-checking also changes how the board captures should be used.
Board A and board B contain byte-identical `hwcomposer.ares.so`, and its video
path performs only `/dev/decd` enable/frame/stop ioctls; `/dev/ge2d` is the
independent RGB UI path.  Their `decd.ko` and `ge2d_dev.ko` files have different
build IDs, but normalized disassembly of the relevant DECD enable, mux, blue,
top-enable and IRQ routines is functionally identical.  We therefore expect
the same video architecture on both boards while using **board B** as the
ground truth for DT, kernel-module build and boot-state comparisons.

One concrete board-B mismatch remained: stock DT requests a 200 MHz AFBD
clock, whereas the isolated Linux test ran it at 100 MHz.  A controlled 200 MHz
test was started with the direct frame held, ARM IRQ masked, source 0 enabled,
internal blue enabled, logo hidden and mixer layer 0 enabled.  Register and
clock readback remained stable, but the operator saw black throughout.  The
100-versus-200 MHz difference is therefore eliminated as the visible-routing
cause.

A subsequent board-B userspace audit found an important qualification to
"HWC only submits video through `/dev/decd`".  `DecoderDisplay::present()` is
indeed only the DECD frame ioctl, but the surrounding HWC SVP power manager's
resume path calls `powerCtrl(1)`, `DecoderDisplay::enable(1)`, `iommuEnable()`
and `tvserverHal::dispCpuResume()`.  The board-B vendor image also contains a
`loadmips`/`libmips.so` path that opens `/dev/mipsloader`, loads `display.bin`,
and waits for `cpu_comm`/`sys.svp_drvload_done`; HWC waits for the
`display.mips.bootfinish` property before notifying its video input path.  This
is the first concrete evidence of the coordinated initialization that the raw
MIPS release experiment omitted.  The next work should reconstruct or invoke
that handshake under single ownership, not guess more DECD format/mixer bits.

That distinction was first tested directly on 2026-08-28.  After physical
power cycles with the normal logo preboot temporarily disabled, U-Boot launched
the authenticated board-B firmware exactly once per boot.  Firmware execution,
MIPS READY, application-ready and both CPU_COMM magic/ready words all passed.
A purported zero-argument call to `THal_Vp_Init` (`0x1c6ff747`) was accepted
immediately and produced a valid `CALL_ACK`, but no `RETURN`.  This occurred
with both the historical project `0x33` recipe and board B's declared project
`0x34`.

**That zero-argument test was malformed and its initialization conclusion is
retracted.**  The disassembly helper had also used a firmware virtual base
4 KiB too high (`0x8b101000` rather than `0x8b100000`), so its earlier view of
the registered adapter was unrelated code.  Disassembly at the corrected base,
then an independent trace through board-B stock `libhaldisplay.so`, recovered
the real ABI:

- ARM allocates a `0xd800`-byte CPU_COMM buffer and converts it to a physical
  address.
- It submits three input words: `0`, `1`, and that physical address.
- The MIPS adapter invokes its local VP initializer, copies `0xd800` bytes of
  state to the supplied address through an uncached alias, returns one value,
  and installs an application callback.

The no-parameter call therefore supplied address zero for the copy and was not
a valid test of standalone initialization.  Register changes made after that
unresolved call, including the internal-blue experiment, cannot establish how
far valid initialization progressed.

The corrected stock-shaped call was first run on a clean project-0x34 boot
with inputs `[0, 1, 0x4df00000]`.  It was consumed immediately and returned a
valid `CALL_ACK`, but no `RETURN`.  A persistent trace then settled where it
stopped: the CALL HISR enqueued the high-priority worker successfully and
returned (`e011`, queue status zero), but the worker never reached descriptor
recycling or routine lookup and the `THal_Vp_Init` adapter was never entered.
The live call table nevertheless contained the exact expected entry,
`1c6ff747 -> 8b109f04`.  The ThreadX clock remained fixed while the hardware
raster advanced.  Thus the project-0x34 failure is upstream of VP init: an
accepted work item is not being serviced, most likely because another firmware
thread is spinning or because project-0x34 state prevents the CALL worker from
being scheduled.

The same traced ABI call was then repeated after a clean reset with project
`0x33`.  It completed the full transport in 1 ms, returned one word equal to
`1`, reached every VP boundary through callback installation (`7101` through
`7105`), and completed RETURN/RETURN_ACK cleanup (`c013`, `f003`).  A final
cache-coherent run used physical destination `0x4d800000` inside the workspace
that U-Boot clears and flushes before releasing MIPS.  The sampled output words
matched the firmware's source at `0x8b48c304` exactly, starting
`00040000 000c0008 00150010 ...`; this directly proves that the local VP
initializer, `0xd800`-byte bulk copy and callback-install tail all return.
The earlier `0x4df00000` destination was cleared through dirty ARM cache lines,
so its later all-zero read was not valid copy evidence and is superseded by the
coherent framebuffer test.

This materially changes the next step.  Do not instrument deeper inside
`THal_Vp_Init`; it works.  Instead compare the `ProjectID_0x0033.TSE` and
`ProjectID_0x0034.TSE` initialization paths and trace the current/runnable
ThreadX threads just before the first CALL.  Also verify from stock boot state
which project ID is actually passed to the display CPU: `panel_config.ini`
declares 0x34, but the only project with a proven live RPC worker is 0x33.  The
apparent whole-board lock after an earlier run was caused by querying
`h713_disp commstate` while a transaction was unresolved, not by the call
itself.

> **The project-0x34 half of the paragraph above is retracted, 2026-08-28.**
> Tested directly on clean board-B boots, and it does not reproduce. Under
> `0x34`: the 60-second stability window is **tick-for-tick identical to
> `0x33`** (210 -> 60665, ~1008/s, zero exceptions); a no-op CALL (`2f02f7dd`,
> `chan=0 pid=0x8b8f275c` from `commdev`) round-trips in **1 ms**; and
> `THal_Vp_Init([0, 1, 0x4d800000])` returns **`1`** in under a millisecond,
> with the `0xd800` copy landing. There is no frozen tick, no unscheduled
> worker, and no project-dependent RPC failure. Item 3 of section 7 is closed,
> negative.
>
> **Nor is it the instrumentation.** The first guess was that two of the five
> new `THal_Vp_Init` trampolines (`0x4b109f28`, `0x4b109f50`) break the adapter
> by displacing a live instruction with `jal`, clobbering `ra`. Disassembly
> refutes it -- the adapter spills `ra` at `0x8b109f10` and does not reload it
> until `0x8b109f58`, so `ra` is dead at both sites, and the delay-slot
> reordering each one introduces touches independent registers. Re-run under
> `0x34` **with the comm-trace set installed**, the call completes and every
> boundary fires: `stage=0xc013`, `CALL=0xe011`, `RETURN_ACK=0xf003`,
> `VP-init stage=0x7105`, `nret=1`, `ret[0]=1`. The reported failure does not
> reproduce instrumented or uninstrumented.
>
> **New and positive:** the copied VP state is project-specific --
> `00050000 0011000b 001d0017 00290023 ...` under `0x34` against
> `00040000 000c0008 00150010 ...` under `0x33`. **New and negative:**
> `THal_Vp_Init` does not touch the video path at all. `0x05600000`-`0x0560007f`
> is byte-identical immediately before and after the call and across two
> independent boots, with source 0 still reading `0x03000010` (enable `0`,
> format `0`) and an empty Y/C queue. Completing VP init is therefore not the
> missing step that programs the video source.
>
> Operationally: **a U-Boot `reset` is a sufficient clean MIPS launch.** Drop
> `h713_disp auto` from `preboot`, `saveenv`, and the whole MIPS experiment loop
> runs over serial with no operator and no physical power cycle.

The existing Linux CPU_COMM reconstruction is not ready to fill this gap.  Its
own kernel README correctly leaves it disabled because the vendor protocol
stores 32-bit shared pointers, while the current arm64 port still reconstructs
some of them by OR-ing a guessed kernel-VA prefix.  It also auto-registers MIPS
handler addresses such as `0x8b109f04` as routine IDs, even though the verified
call-table entry separates that handler address from callable component ID
`0x1c6ff747`.  Enabling that patch now would test two known ABI errors at once.

### The CPU_COMM surface is exhausted for this problem (2026-08-28)

With `THal_Vp_Init` working, the obvious next move was to drive the rest of
stock's resume over CPU_COMM from U-Boot. It cannot be done, and the reason is
worth recording so nobody tries again.

**The live call table under `0x34` holds 82 populated entries and every one is
`THal_Vp_*`.** There is no resume, power, IOMMU, decoder-enable or
frame-submit routine anywhere in it. The firmware's RPC surface is purely the
video-processing HAL -- picture quality, backlight, window geometry, source
selection, HDMI/ATV/VBI, callbacks. Everything HWC does after `THal_Vp_Init`
is an ARM-side driver operation on `/dev/ge2d` and `/dev/decd`, not a call
into the display CPU.

The two routines that looked like the frame handoff are **stubs on this
firmware**:

```
THal_Vp_SetImageBufferAddr  0x8b10ada8:  jr ra ; nop
THal_Vp_GetImageBufferAddr  0x8b10adb0:  jr ra ; nop
```

Source selection is also not the missing lever, and this is the more
interesting half. On a clean `0x34` boot, in order:

- `THal_Vp_Init([0, 1, phys])` returns `1`.
- `THal_Vp_GetSource` returns `0` (`Dummy`).
- But the firmware's own source trace shows it **already transitioned `0 -> 1`
  (`kSourceId_VideoDec`) during startup**: `worker=0x5203 (source worker
  completed transition), new=1 old=0`.
- `THal_Vp_SetSource(1)` is accepted (`nret=0`) and changes nothing -- no new
  worker transition, `GetSource` still `0`, and the AFBD window byte-identical.

So the firmware boots itself into VideoDec and stays there. The video source
at `0x05600010` still reads enable `0` / format `0` not because the wrong
source is selected, but because **nothing is presenting**: no IOMMU, no DECD
enable, no frames. That is consistent with the format writer being firmware
code driven by DECD's VideoInfo, and it means the remaining work is entirely
on the Linux side.

The remaining "configured versus serviced" question was then closed with an
in-firmware frame trace. PanelWinNode's update method only calls the AFBD frame
programmer when dirty-mask bit `0x800` is set. One bounded Linux fmt-0 submit
arrived with dirty mask `0xffffffff`, entered the programmer, executed its
source commit and AFBD dirty stores, and reached final marker `0x6103`. The
source commit subsequently read zero, proving hardware consumed it, while DECD
continued at approximately 60 IRQ/s with valid Y/C addresses. Black output is
therefore downstream of a serviced, consumed frame update: fetch, mixer
selection, or composition. Full evidence:
[`reference/frame-service-gate-confirmed-2026-08-31.txt`](reference/frame-service-gate-confirmed-2026-08-31.txt).

The first capture of the firmware-owned ARM `0x05000000` composition block
now closes another ambiguity. Supplying the old `0x5000/0x2d00` VideoInfo
rectangles changed size fields throughout that block from 1280x720 to
852x480; immediately submitting the corrected canonical `0x7800/0x4380`
rectangles reversed every one back to 1280x720. The two-thirds geometry is
therefore real downstream composition state, but entirely explained by the
already-corrected coordinate-space input. It is not the remaining black-screen
gate. Two non-geometry words changed only on the first accepted frame
(`0x05000058: 0x80040000 -> 0x00040000` and `0x05000104: 0x1b00ff00 ->
`0x1100ff00`). A subsequent clean boot made the corrected canonical frame the
first and only submit and reproduced exactly those two changes while every
geometry and routing word through `+0x87c` remained byte-identical. A direct
real-time MMIO watcher captured stages `0 -> 0x6101 -> 0x6103`, eliminating
the earlier shell-watcher scheduling ambiguity. The two words are therefore
normal first-frame effects, although their hardware meaning remains unknown;
PanelWinNode's update method contains no direct access to either offset. Full
diff, watcher source and apparatus hashes:
[`reference/frame-composition-block-capture-2026-08-31.txt`](reference/frame-composition-block-capture-2026-08-31.txt).

### DECISIVE: the firmware DOES program the video source (2026-08-28, late)

The experiment this brief has been building toward was finally run: **the MIPS
left running into Linux**, with the 0068 DECD-exclusive kernel and **IOMMU
bypass** (translation would fault the firmware's own physical fetches, and one
fault wedges the engine).

Setup: `preboot` calls `h713_disp init 0x34` instead of `auto 0x34 logo`.
`auto` calls `h713_disp_quiesce_mips_owner()`, which is why every previously
measured boot had a parked coprocessor; `init` does not. U-Boot prints
"display initialised **with the firmware running**", and Linux comes up with
`0x0306101c = 0x00000001`.

**The result, and it settles the central question of this document.** Submitting
one NV12 frame through `/dev/decd` with the coprocessor alive causes the
firmware to configure the video source:

```
                    MIPS parked        MIPS running + DECD submitting
0x05600010          0x03000010    ->   0x03000413    enable[1:0] 0->3, fmt 0->4
0x05600020          0x043F077F    ->   0x02CF04FF    1920x1088 -> 1280x720 - 1
0x05600040/44       0x00000780    ->   0x00000500    stride 1920 -> 1280
0x0560004c          0x01680500    ->   0x02D00500    360 -> 720 rows
```

Seven sessions of ARM-side register work never moved `0x05600010`. It moved on
the first submit with the firmware alive, and the geometry was rewritten to
match our exact frame. **"The MIPS firmware configures the video source, fed by
DECD's VideoInfo" is no longer an inference -- it was observed.** The
`dec_reg_video_channel_attr_config()`-is-dead-code finding predicted precisely
this.

Also newly established: **source 0's commit latch at `0x05600014` is consumed by
hardware.** Written `1`, it reads back `0`, repeatedly -- the behaviour of the
serviced OSD channel, and the opposite of channel 0's latch at `0x05600104`
which sticks at `1` forever. Source 0 is in the serviced path.

**And the panel stayed black.** Every one of these was applied, cumulatively,
each verified by readback, with the raster alive at 59.7 Hz throughout and every
write sticking (the firmware did not revert them):

| applied | register | result |
| --- | --- | --- |
| firmware-configured source | `0x05600010 = 0x03000413` | black |
| logo channel hidden | `0x05600140 = 0x03001900` | black |
| mixer video layer | `0x0525c004 = 0x1403`, then `0x1003` | black |
| `dec_reg_int_to_display()` | `0x05600060` bit 4 set, `0x01 -> 0x11` | black |
| `dec_reg_bypass_config()` non-zero branch | `0x05600069` bit 0 cleared, `0x0560006c = 1` | black |
| source-0 commit latch | `0x05600014 = 1`, consumed | black |
| **DECD internal blue generator** | `0x05600065` bit 0, `0x05600064 = 0x0100` | **black** |

The last row is the discriminator. Internal blue bypasses Y, C, stride,
dma-buf, VideoInfo and the whole frame data path -- the source generates its own
pixels. With the source enabled, formatted, geometry-correct, commit-latched and
generating internally, **nothing reaches the panel**.

**So the remaining gap is downstream of DECD entirely**, in the mixer / VBlender
/ LVDS composition the firmware owns. No further DECD-side configuration will
reach it. That is a much smaller and better-located target than "how do we make
a channel fetch YUV".

Positive controls for this boot, so the black is not a dead pipeline: the U-Boot
logo was visible on this same boot until it was deliberately hidden; vsync held
59.7 Hz (16.74 ms deltas) after every write; DECD ran at 60 IRQ/s throughout;
panfrost GPU/MMU/job stayed at 0; the SoC never locked and Wi-Fi/serial stayed
up the whole time.

A complete 154-line register dump of this configured-but-black state is saved at
[reference/decd-firmware-configured-black-2026-08-28.txt](reference/decd-firmware-configured-black-2026-08-28.txt)
-- AFBD `0x05600000`-`0x056001ff`, mixer `0x0525c000`-`0x0525c03f`, TVTOP. It is
the obvious thing to diff against a stock Android playback capture.

**What I would do next, in order:**

1. Diff that snapshot against stock Android during real video playback. The
   remaining difference is in composition, and this dump makes it a diff rather
   than a search.
2. `THal_Vp_SetSource` / the display-CPU resume (`tvserverHal::dispCpuResume()`)
   from the ARM side while the firmware is running. Stock does this and we never
   have; CPU_COMM is not reachable from Linux today (patch 0014 disabled, known
   ABI errors), so this likely means either fixing that port or driving it from
   U-Boot before handing off.
3. The mixer window slots `0x0525c01c`/`020` versus `0x030`/`034` -- two slots
   with identical geometry, never separated, and a plausible video-vs-OSD pair.
4. The AFBD writeback engine (`0x4777`/`0x4778`, `get_afbd_wb_inst`), untouched.

**Status update 2026-08-30.** Item 4 is **eliminated** -- the writeback engine is
disabled on stock and is not the video path. Item 2 is now the live one, and is
better specified than it was: the CPU_COMM `Wce_*` window path is **dead** (its
worker is a stub), the suppression routines are **real but tested negative at the
U-Boot prompt with an invalid observable**, and settling them requires calls made
while video is composited -- i.e. CPU_COMM from Linux. A disabled 8440-line port
already exists (`patch 0014`, `# CONFIG_HY310_CPU_COMM is not set`) with at least
one located ABI defect. See [handoff-2026-08-30.md](handoff-2026-08-30.md).

**Do not** spend more time on DECD-side format/enable/mux permutations. The blue
generator result closes that space: the source is doing its job and the output
is being discarded after it.

### The stock Android playback capture (2026-08-28, later)

Step 1 above was run. Stock Android, `com.softwinner.TvdVideo` playing a 1280x720
H.264 Main clip, verified on the panel by the operator and by 114 decoder log
lines, sampled once a second for eight seconds from inside the playback window.
Captures: [reference/stock-android-playback-2026-08-28.txt](reference/stock-android-playback-2026-08-28.txt)
and an idle baseline in [reference/stock-android-idle-2026-08-28.txt](reference/stock-android-idle-2026-08-28.txt),
both in the reference dump's exact format so they diff line-for-line.

**The pipeline is unmistakably live.** The Y base at `0x05600070` cycles through
a ring -- `0x00200000`, `0x01900000`, `0x00400000`, `0x02900000` -- with the C
base at `0x05600084` always exactly `Y + 0xE1000`, which is 921600, the 1280x720
NV12 luma plane. Frame counters at `0x05600058`/`0x0560005c` advance throughout.

Three findings, in descending order of how much they should change what we do.

**1. Stock never sets the format nibble we set.** Across all eight samples,
`0x05600010` reads `0x03000013` -- enable 3, **fmt 0**. Our DECD submit drove it
to `0x03000413`, fmt 4. This brief read that transition as the firmware
configuring the source correctly. It did configure it, but *not to the value
stock uses while putting real video on the panel*. Whatever our VideoInfo
declares, it is not what the vendor path declares. The idle baseline already
reads `0x03000013`, so fmt 0 is the resting and the playing value alike.

**2. Stock has a channel fully configured at `0x05600100` that Linux leaves
empty, and bit 31 set on two channel-control registers.**

| register | Linux (black) | stock (playing) |
| --- | --- | --- |
| `0x05600100` | `0x00010000` | `0x83001901` |
| `0x05600108` | `0x00000000` | `0x008000FF` |
| `0x0560010c` | `0x00000000` | `0x00FF0080` |
| `0x05600140` | `0x03001900` | `0x83001900` |

The structural tell: `0x05600148`/`0x0560014c` are `0x008000FF`/`0x00000080` in
**both** dumps, so the `0x140` channel has its pair programmed either way -- but
the `0x100` channel's corresponding pair is programmed **only** on stock. And
bit 31 is set on both control words on stock, in idle and in playback, and was
never set by any ARM-side write we have made. That is a static enable, not a
playback artifact, and it sits exactly where this brief predicted the gap:
downstream of the source, in composition.

**3. Stock runs translated, we ran bypassed.** Every stock buffer address is a
low IOVA (`0x00200000`-`0x02900000`); ours were raw physical (`0x6C500000`).
Item 4 of the earlier list assumed IOMMU bypass was a safe simplification for
the firmware's own fetches. Stock does not use it.

Also worth noting, smaller: the mixer layer control at `0x0525c004` is `0x1402`
on stock. The DECD experiments tried `0x1403` and `0x1003`; **neither is the
stock value**. And `0x0525c000` is `0x02F7054F` on stock against our
`0x02F80550` -- both H and V totals off by exactly one.

**Operational note for repeating this.** The vendor player silently refuses a
video-only file: a 1280x720 H.264 clip with no audio track produced "Video
Problem: Do not support this video" on screen, while the byte-identical video
muxed with a silent AAC track played immediately. A file pushed to `/sdcard`
also lands `-rw-------` under a FUSE-synthesised uid that `chmod` cannot change,
so the player cannot open a `file://` path to it; scan it with
`MEDIA_SCANNER_SCAN_FILE` and launch the resulting `content://` URI instead.

### Writes to AFBD need the commit latch, and bit 31 is not the answer (2026-08-28)

Rather than rebuild a kernel to set bit 31 on the black side, it was cleared on
the working side: stock Android, clip playing, `tools/display/hidtvreg-poke.c`.
A working system that breaks when you remove one bit says more than a broken
system that stays broken when you add it.

**The rule that came out of it, which matters more than the bit: a write to this
block does nothing until the per-register commit latch is pulsed.** Control at
`+0x00`, latch at `+0x04`. Clearing the source enable at `0x05600010` and
holding it -- verified held, 300/300 samples over six seconds, never reverted by
the firmware -- left the playing video completely unaffected. The *identical*
write with `0x05600014` pulsed replaced the video with **solid green**, which
reverted cleanly on restore.

So an uncommitted write to this block lands in the register, reads back, holds
indefinitely, and is inert. **Readback proves nothing here.** Any earlier result
that rests on "the write stuck" without a latch pulse should be re-checked.

Green rather than black is itself a useful signature: `Y=0, Cb=0, Cr=0` is about
`RGB(0,135,0)`. The composition dropped to zero luma, which confirms AFBD source
0 is genuinely the live video path to the panel and gives this line of testing
the positive control the DECD work lacked for so long.

**Bit 31 is not load-bearing.** With the latch pulsed, cleared on `0x05600100`
alone, on `0x05600140` alone, and on both together, held six seconds each during
playback of a clip verified frame-by-frame to contain motion: the video was
unaffected every time. Finding 2 of the stock diff is eliminated as the
mechanism -- the bit differs between stock and our black state, but it is not
what makes the difference.

One behavioural difference worth recording: on stock, `0x05600014` written 1
**reads back 1**. This brief documents it as consumed on Linux -- written 1,
reads back 0. Same register, opposite behaviour, and unexplained.

Two cautions on this session's method, both of which cost a result:

- A first pass used a clip generated as flat navy with a `drawbox` overlay that
  silently never rendered. With a static image "playing" and "frozen" look
  identical, so the observation was uninterpretable. Verify the test clip
  contains motion -- hash frames at several timestamps and confirm they differ --
  *before* it reaches the board.
- Clearing the channel enable at `0x05600100` was read as evidence that the
  Android UI is not composited through this block. That inference was wrong: the
  write was simply uncommitted. Whether the UI runs through AFBD is untested.

### fmt 4 is causal, and it is NOT what makes our state black (2026-08-28)

Same method as the bit-31 test: set stock to the value our black state carries,
during playback, with the latch pulsed. `0x05600010` `0x03000013` ->
`0x03000413`, held 1250/1250 samples across 25 seconds, photographed off the
panel. (`adb screencap` is useless for this -- it reads the Android surface, and
the video is on a hardware overlay that never appears there.)

**The picture broke, and it broke in a specific way.** The image repeated
roughly twice horizontally and was squashed into the top ~45% of the frame, with
the remainder flat. That combination is one signature, not two: the fetch is
consuming about two source lines per output line, so content repeats across the
width and exhausts the buffer at about half the height. Everything below is
fetch past valid data, which is why the flat region was a different colour in
each of two photographs (teal, then yellow-green) rather than stable.

Colours in the valid region were also shifted -- saturated neon pink/green/cyan
rather than the clip's colour bars -- so the chroma plane is misread as well,
not only the line stride. Both are consistent with the format field selecting
buffer interpretation, and 4 assuming a different bytes-per-pixel packing than
the NV12 the buffer actually contains.

**So finding 1 of the stock diff is causal: fmt 4 is wrong for our data and
stock's fmt 0 is right.** Making DECD's VideoInfo produce fmt 0 is a concrete,
targeted change.

**But it does not explain the black.** fmt 4 on stock yields a distorted,
clearly visible picture. Our Linux state has fmt 4 *and* shows nothing at all.
Setting fmt 0 is therefore necessary and demonstrably not sufficient; at least
one other difference is still doing the work. Do not treat this as solved.

**Unplanned observation, worth its own look:** the player's own UI -- seek bar
and transport icons -- was tiled *inside* the distorted region, in the same
repetition as the video. What AFBD source 0 fetches therefore already contains
the player's overlay, so composition happens upstream of this fetch. That has
implications for the subtitle/OSD question raised earlier in this brief.

### Which blocks are actually used for video, and the GPU answer (2026-08-28)

A scoping question worth more than another register permutation: which of these
components does stock actually drive per frame? Answered by sweeping eleven
known-safe windows at idle twice, two seconds apart, then once during playback --
the double idle sample separates free-running counters from anything genuinely
video-driven. Full capture in
[reference/stock-android-block-sweep-2026-08-28.txt](reference/stock-android-block-sweep-2026-08-28.txt).

| block | regs | free-running | video-driven | verdict |
| --- | --- | --- | --- | --- |
| **AFBD** | 128 | 8 | **8** | **active in the video path** |
| TVTOP | 48 | 0 | 0 | static |
| MIXER | 32 | 0 | 0 | static |
| DE_OSD | 32 | 0 | 0 | static |
| LAYER / ROUTE / LVDS_PHY / PLL / GE2D / MIPS / IOMMU | — | 0 | 0 | static |

**Only AFBD moves**, and only its Y bases (`0x05600070`-`7c`) and C bases
(`0x05600084`-`90`), flipping as a ring. **TVTOP is not driven for video** -- its
48 registers are byte-identical idle versus playback.

The caveat that keeps this honest: *static is not unused*. TVTOP still routes the
signal, the LVDS PHY still drives the panel, the PLL still clocks it. They are
load-bearing but **configured once at init and never touched per frame**. That is
the useful shape for scoping: get them right once, and the only per-frame driving
required is AFBD's buffer slots.

**And the GPU is genuinely off during video.** Measured through the Mali runtime
PM counters at `/sys/devices/platform/1800000.gpu/power`:

```
idle, 12 s                      gpu active +0 ms      suspended +12114 ms
playing, controls visible, 12 s gpu active +12128 ms  suspended +0 ms
playing, controls hidden, 15 s  gpu active +0 ms      suspended +15115 ms
```

The middle row is the player's transport controls, not the video -- a trap worth
naming, because measured alone it looks like stock composites video on the GPU.
Once the controls auto-hide and the video is still playing, the GPU is
**completely suspended**. This document's central premise -- that the vendor
stack puts video on the panel without the GPU doing colour conversion -- is now
**directly confirmed on hardware** rather than inferred from `hwcomposer`.

**This also answers the open subtitle/OSD product question.** Stock has two
modes: video alone runs decoder -> dma-buf -> AFBD source 0 -> panel with the GPU
asleep, and video *with* UI wakes the GPU to composite both into one buffer which
AFBD then scans out. That is why the transport controls appeared tiled *inside*
source 0's corruption in the fmt-4 photographs -- they share the video's buffer.
So the vendor answer to overlays is **wake the GPU and composite**, not hardware
subtitle blending over video. Section 0's third option was the right one.

### All three stock-diff findings are tested, and none of them is the black (2026-08-29)

The IOMMU was the last of the three. Bypassing master 2 on stock during playback
-- `IOMMU_BYPASS_REG` at `0x02010030`, bit 2, `0x00000000` -> `0x00000004`, held
300/300 samples across six seconds -- produced **coloured static**. Which is what
bypass should do: the registers hold IOVAs like `0x00400000`, and unstranslated
they address below the H713's `0x40000000` DRAM base, so the fetch reads
non-memory. The engine did not wedge, the bypass restored cleanly, and uptime was
unbroken.

| finding | forced onto stock | result |
| --- | --- | --- |
| bit 31 on the channel controls | cleared, committed | **no effect** |
| fmt 4 rather than fmt 0 | set, committed | tiled, half-height, colour-shifted |
| IOMMU master 2 bypassed | bypass bit set | **coloured static** |

**None produces black.** Two produce visible corruption, one does nothing at all.
The three differences this brief identified as the candidate answers have yielded
none.

**What that negative is actually worth.** On stock, *every* way source 0 can be
broken still puts something on the panel: green when starved of data, tiling when
misformatted, static when misaddressed. The path downstream of source 0 passes
whatever it produces, unconditionally. Our state shows nothing at all. So the
black is not a misconfiguration of source 0 -- it is source 0's output not
reaching composition in the first place. That was this brief's conclusion from
the blue-generator result; it now has direct hardware support rather than
inference, and from the opposite direction.

**Where that leaves the search.** Two differences from the stock diff remain
untested, and both are in the mixer -- downstream, where the fault was localised:

```
0x0525c004   stock 0x1402       ours 0x1003
0x0525c000   stock 0x02F7054F   ours 0x02F80550
```

`0x0525c004` is the more interesting of the two: the DECD experiments tried
`0x1403` and the vendor table's `0x1003`, and **neither is what stock runs**. The
obvious next experiment is to write our values into stock's mixer during playback
and see whether the panel goes black rather than merely corrupt. Black would be
the first time any forced difference reproduced our symptom.

### The mixer is not in the video path, and the stock diff is exhausted (2026-08-29)

The two remaining differences were both in the mixer, so they were forced onto
stock during playback. All three attempts are null:

| written to `0x0525c004` | latch | panel |
| --- | --- | --- |
| our `0x1003` (stock `0x1402`) | none | no change |
| `0x00000000`, layer control zeroed | none | no change |
| `0x00000000`, layer control zeroed | `0x0525c008` pulsed | **no change** |

Each held its value 300/300 samples across six seconds. The second and third are
positive controls, not experiments: zeroing a block's layer control outright
should do *something*. It does nothing, latched or not.

**So the mixer at `0x0525c000` is not in the live video path**, and two
independent lines say so. The block-sweep found zero of its registers moving
between idle and playback, and now zeroing its control word changes nothing on
screen. The two mixer differences from the stock diff are therefore almost
certainly irrelevant, including `0x0525c004`, which had looked like the strongest
remaining lead precisely because neither value we had tried was stock's.

One caveat kept deliberately: `0x0525c008` as a double-buffer latch is a guess by
analogy with mainline `sun8i-mixer`, and it read back `1` rather than being
consumed, so "mixer writes never reach hardware at all" is not fully excluded.
The sweep result does not rest on that guess.

**The stock-side search is now exhausted.** Every difference the stock capture
revealed has been forced onto working hardware: bit 31 (nothing), fmt 4
(tiling), IOMMU bypass (static), mixer control and H/V total (nothing). None
reproduces black.

**What is actually left, and it is a gap in the data rather than a new theory.**
The sweep shows every block except AFBD is static during playback, so the path
from AFBD to the panel is statically configured. But we have only ever captured
three of those blocks on the Linux side -- AFBD, mixer and TVTOP -- and TVTOP
already matched exactly. **DE_OSD, LAYER, ROUTE, LVDS_PHY, PLL, GE2D and the
IOMMU have never been compared between stock and our black state at all.** A
static-configuration difference in any of them would not have shown up in
anything done so far.

The next experiment is therefore not another poke: it is to capture those same
eleven windows under our Linux with `tools/display/hidtvreg-read.c`'s equivalent
and diff them against
[reference/stock-android-block-sweep-2026-08-28.txt](reference/stock-android-block-sweep-2026-08-28.txt).
That is the one comparison that has never been made, and it covers exactly the
statically-configured path the evidence now points at.

### The comparison that had never been made (2026-08-29)

Booted back to our stack and swept the same eleven windows with
`tools/display/mmio-read.c` -- the arm64 counterpart of the stock reader, going
through `/dev/mem` and emitting a byte-identical format so the two captures diff
line-for-line. Saved as
[reference/linux-block-sweep-2026-08-29.txt](reference/linux-block-sweep-2026-08-29.txt).

**49 of 340 registers differ.** By block:

| block | regs | differ |
| --- | --- | --- |
| TVTOP | 48 | **0 -- identical** |
| LAYER | 16 | **0 -- identical** |
| ROUTE | 8 | **0 -- identical** |
| MIXER | 32 | 1 |
| DE_OSD | 32 | 1 |
| PLL | 8 | 1 |
| GE2D | 16 | 1 |
| MIPS | 4 | 1 |
| IOMMU | 32 | 3 |
| LVDS_PHY | 16 | **4** |
| AFBD | 128 | 37 (expected -- different video state) |

**State caveat, and it matters:** stock was playing video; ours is an idle console
with the MIPS parked (`0x0306101c` = 0 here, 1 on stock) and no DECD activity. The
AFBD deltas are therefore expected. TVTOP, LAYER and ROUTE being byte-identical
independently confirms the earlier conclusion that those are configure-once and
already correct on our side.

**The cleanest finding: our H/V total encoding is off by one, in two independent
blocks.**

```
MIXER   0x0525c000   stock 0x02F7054F   ours 0x02F80550
DE_OSD  0x0524c010   stock 0x02F7054F   ours 0x02F80550
```

`0x54F` = 1359 against our 1360, `0x2F7` = 759 against our 760. Stock encodes
total-minus-one and we encode the total, and the *same* value appears in both
blocks. This was previously visible only as one odd mixer value and easy to
dismiss; a second independent block carrying the identical discrepancy makes it a
convention error rather than a curiosity.

**The biggest new difference is the LVDS PHY** -- four of sixteen registers, in
the block that physically drives the panel, which had never been compared:

```
0x051c0010   stock 0x00000000   ours 0x00000045
0x051c0014   stock 0x1A000005   ours 0x18000005
0x051c0024   stock 0x00350000   ours 0x00300000
0x051c0028   stock 0x08100035   ours 0x1F300030
```

**Tempering that before anyone spends a week on it:** our values are exactly the
ones `tools/display/devmem32.c` and the handoff doc record as the *working* logo
configuration, so they demonstrably can drive this panel. And on stock the MIPS
firmware owns the display while on ours U-Boot does, so this may be two valid
configurations rather than one broken one. It is the strongest new lead, not a
smoking gun.

**The IOMMU difference is now concrete rather than inferred:**

```
0x02010030 BYPASS         stock 0x00000000   ours 0x0000007C
0x02010050 TTB            stock 0x6F3A0000   ours 0x41F28000
0x02010070 TLB_PREFETCH   stock 0x0003007F   ours 0x0000007F
```

`0x7C` is masters 2,3,4,5,6 bypassed -- master 2 is `dec@5600000`, so our side
really is running the video master untranslated, in the register rather than by
inference. Bypass was already shown on stock to produce coloured static rather
than black, so this remains a difference rather than a cause.

Also new: `PLL 0x058c0018` is `0xC950311E` on ours and **zero** on stock, and
`GE2D 0x05240018` is `0x00004000` on stock against zero on ours.

### How this should reach mpv if the one-frame test works

Decode and presentation are separate choices. VA-API already drives Cedrus
through the `libva-v4l2-request` shim and exports linear NV12 dma-bufs; a native
FFmpeg V4L2-request path can expose the same buffers as DRM PRIME. Neither API
requires a GPU, but mpv's `vo=gpu` does: it imports Y and UV as textures and
runs the colour conversion in panfrost.

The clean production design is therefore to merge DECD's queue/register code
into `sun50i-h713-afbd` and expose a PRIME-importing NV12 DRM plane (or NV12
mode of the full-screen plane). Then mpv's DRM-PRIME overlay/direct-scanout
path can consume either VA-API-exported or native V4L2-request dma-bufs while
the one KMS driver owns MMIO, vblank, fences and teardown. The DECD release
fence must control when a decoder surface may be reused; the synthetic client
closes it only because its static carveout is never recycled during the test.

A small custom mpv `vo_decd` would be a faster product-specific bridge after
the hardware proof, but would duplicate buffer lifetime, scaling, seek/EOS and
colour-metadata policy in userspace. The existing proposed mpv `render_fd`
fallback remains worthwhile as a zero-copy compatibility path, but it still
uses the GPU shader and is not the no-GPU solution.

One product question remains even if full-screen DECD works: subtitles and UI.
They need either a simultaneously serviced RGB OSD over DECD video, hardware
subtitle blending, or a fallback to GPU composition. The first Android
playback register capture should therefore include a visible subtitle/overlay
case as well as plain full-screen video.

---

## 1. The goal

Play video without the CPU or GPU doing colour-space conversion.

The decoder (`cedrus`, mainline V4L2 stateless) outputs **NV12**. Our display
driver scans out **XRGB8888 only**. So today something must convert.

| path | result |
| --- | --- |
| CPU `videoconvert` | 3.15 fps default, 14.93 fps with `n-threads=4` |
| GPU (GLES, `samplerExternalOES`) | **59.71 fps, zero copy — works today** |

The GPU path already saturates the panel (vsync ceiling ~58.9 fps), so this is
**not** about throughput. It is about freeing the GPU and letting stock clients
(`mpv`, GStreamer `kmssink`) work without a GLES pipeline.

The vendor's own stack does neither: it decodes into a dma-buf and submits that
plus a metadata dma-buf to `/dev/decd`, letting the **display hardware** do
YUV→RGB. We want that path. The earlier assertion that it must be a second copy
of the OSD/AFBD channel was an inference, not a fact, and patch 0066 tested only
that OSD channel.

**The question we cannot yet answer: how is DECD video routed into the serviced
display output, and can Linux reproduce that stock route safely?**

---

## 2. The hardware

**SoC:** Allwinner H713 / sun50iw12p1, Cortex-A53, Mali-G31. Projector product
(HY300-class). Android 11 stock; we run mainline Linux 6.18.

**The display is not a normal Allwinner DE.** There is no `DE2`/`DE33` mixer
driver path and no `sun4i-drm`. Instead:

- A **MIPS co-processor** runs vendor firmware `display.bin` (1.2 MB) and owns
  the display pipeline: VBlender timing, LVDS PHY.
- U-Boot loads that firmware, replays a register table (`LogoRegData.bin`),
  releases the MIPS, and finalises LVDS.
- Linux **adopts** the already-running display. Our KMS driver never touches
  timing, PHY or the display reset — it only changes which buffer is scanned
  out and when.

Note the DT calls the display block `ge2d`, `compatible = "trix,ge2d"`. This is
**not** Allwinner's G2D 2D engine — it is the projector's display controller
(OSD planes, LVDS FIFO, backlight, TI DLPC3435). There is no G2D on this SoC:
the stock kernel binary contains no `g2d` string at all (verified against a
calibration showing clock names *are* readable in it), and the vendor DTB has
zero `g2d|mixer|rotate|blit` nodes.

### Register map (all verified by reading a live board)

| block | plane 0 | plane 1 (live) |
| --- | --- | --- |
| AFBD channel | `0x05600100` | `0x05600140` |
| OSD | `0x05248000` | `0x0524c000` |
| "window" regs | `0x05280040` | `0x05280080` |
| unknown pair | `0x05288000` | `0x0529c000` |
| VBlender-ish | `0x0520002c` | `0x05200034` |
| LVDS pair | `0x051c0060` | `0x051c006c` |
| LVDS pair 2 | `0x051c0180` | `0x051c019c` |

Fixed blocks: AFBD global `0x05600000`, LVDS base `0x051c0000`,
GE2D core `0x05240000`, **mixer `0x0525c000`**.

AFBD channel stride is `0x40`. Within a channel: `+0x00` ctrl, `+0x04` READY
latch, `+0x08`, `+0x0c`, `+0x10` size-1, `+0x20` size, `+0x24`, `+0x28`,
`+0x2c`, `+0x30` stride, `+0x38` source address.

### Live state of the working plane (plane 1)

```
0x05600140 = 0x03001901   ctrl
0x05600144 = 0x00000000   READY latch -- consumed every vsync
0x05600178 = 0x76D00000   source (framebuffer)
0x0524c01c = 0x79860601   "plane open" word
0x0525c004 = 0x00001402   mixer, low bits 0b10
0x0525c01c = 0x0500003C   width 1280, x-offset 60
0x0525c020 = 0x02D00016   height 720, y-offset 22
0x0525c030 = 0x02D00016   identical pair
0x0525c034 = 0x0500003C   identical pair
```

Plane 0 at rest: AFBD ctrl `0x00010000` (idle), OSD block all zeros,
`0x0524801c = 0`.

---

## 3. The single most diagnostic fact

```
0x05600144   plane 1 READY latch   reads 0   -- hardware consumes it every vsync
0x05600104   plane 0 READY latch   reads 1   -- written, NEVER consumed
```

Writing 1 to a channel's READY latch is how a commit is armed (our own KMS
driver does exactly this on plane 1 every page flip, and it clears). On plane 0
the write sticks and is never taken, under **every** configuration we have
tried. Writing 0 to it does not clear it either; only a reboot does.

Our reading: **channel 0 is not being serviced by the pipeline at all.** Not
misconfigured — unserviced.

---

## 4. What the vendor driver does (recovered by RE)

We extracted the stock display driver `ge2d_dev.ko` from the Android vendor
partition — **ARM 32-bit, unstripped, 926 symbols, relocations intact**.

Findings:

- MMIO goes through an external helper,
  `io_accessor_write_reg(space=2, addr, value, mask)`, from a `trix,io-accessor`
  driver whose DT node maps exactly the display windows.
- `init_osd_plane()` (the plane configuration) is reachable at runtime: it is
  called by `tgd_init_planesetting()`, an exported symbol with no in-module
  callers (so, an ioctl entry), and by `ge2d_resume_operation()`, which re-runs
  it against already-live hardware with **no display reset asserted**.
- `tgd_is_plane_open()` reads OSD base `+0x1c` bit 0. That word is **written**
  by bring-up, not set by hardware — it is not a status bit.
- `osd_ready_for_update(plane)` indexes a rodata table
  `OSD_AFBD_REG_OFFSET = {0x05600100, 0x05600140}` and writes 1 to
  `base + 4` — i.e. the READY latch above.
- `tgd_put_plane_info()` (11 KB, the largest function) does 42 writes / 35 reads
  and calls `osd_ready_for_update` + `osd_wait_update_finish`.

### The bring-up register table

U-Boot replays `LogoRegData.bin`, which is indexed by project ID into a
consistent triple: prologue variant (3 exist), timing variant (11), **DE/mixer
variant (8)**. Records are `{addr, value, mask, type}` u32 with 4-byte resync.

Order: prologue → timing → LVDS FIFO reset → mixer write → DE table →
clocks/INCAP/LVDS → MIPS release → LVDS finalise.

**Critical: parsing every block of that file, across all 8 DE variants, all 3
prologues and all 11 timing variants, there is not one record touching
`0x056001xx` (channel 0) or `0x05248xxx` (OSD plane 0).** Every shipped
configuration programs exactly one plane.

DE variant 1 (our 1280x720 panel) writes, in order:
`0x05600000=0x80000020` (AFBD global, bit 31 set), then 13 channel-1 records,
then `0x05240000`, `0x0524001c`, then 14 mixer records
(`0x0525c000`–`0x0525c034`), then 14 OSD-1 records, then `0x05280080/84/88/8c`,
then **`0x05600144 = 1` with mask `0x1`** (the ch1 latch), then LVDS
(`0x058c0000`, `0x051c0014/24/28`, `0x05140054`, `0x051c006c/70`).

---

## 5. What we tried, and what happened

All negative. Each was verified by register readback, and by an operator
watching the physical panel where visual output was possible.

| # | attempt | result |
| --- | --- | --- |
| 1 | Set bit 31 on ch1 ctrl (`0x83001901`), the one value differing from live | Sticky, not a trigger. Nothing latched. A page flip carrying it changed nothing. |
| 2 | Apply `init_osd_plane`'s 15 literal writes to plane 0 from Linux | All landed. Open word never set (we had not yet realised bring-up writes it). |
| 3 | Full DE-table mirror ch1→ch0 (`-0x40`) and OSD1→OSD0 (`-0x4000`), **including** the open word `0x79860601`, then the latch | Open word reads back correct. **Latch never consumed.** |
| 4 | Sweep AFBD global low bits: `0x80000030`, `0x800000f0` (theory: bit 5 gates ch1, bit 4 ch0) | No effect. |
| 5 | Mixer layer-enable: live `0x0525c004 = 0x1402` vs table `0x1003`; set bit 0 → `0x1403`, with plane 0 fully configured and ch0 source pointed at a real framebuffer | Write takes. Latch still unconsumed. **Operator: no flash, no change, two 15-second holds.** |
| 6 | `h713_disp teardown`, pre-set all ch0/OSD0 registers while pipeline is down, then `h713_disp init` | **The prologue zeroes them.** Nothing survives. |
| 7 | **Flashed a modified U-Boot** injecting the 26 mirror writes + latch *inside* the bring-up sequence, immediately after the DE table, before clocks/INCAP/LVDS | Config **survives** into live scanout — first time. `ch0 ctrl=0x03001901`, `open=0x79860601`. **Latch still `1`, never consumed.** Operator: panel shows console only, no logo, despite ch0 source = logo buffer. |

Attempt 7 is the important one: it controls for *placement*, which was the last
plausible confound. Channel 0 entered live scanout fully and correctly
configured, and the hardware still ignores it.

---

## 6. What we believe, and how confident

**High confidence (direct measurement, reproducible):**
- Channel 0's READY latch is never consumed; channel 1's is consumed each vsync.
- No shipped vendor configuration opens a second plane.
- The plane set is not changed by any register we have written, at any time.

**Moderate confidence (inference):**
- The plane count is fixed by the MIPS firmware's VBlender programming, before
  any of these registers matter.
- This product only ever uses one plane; the plane-0/plane-1 duality in
  `ge2d_dev.ko` is generic vendor code for a family of products.

**We have been wrong repeatedly in this investigation**, so treat the inferences
with suspicion. Specific corrections we had to make: "GE2D is a 2D engine"
(false); "the open word is a hardware status bit" (false, it is written);
"plane-open cannot be applied to a running pipeline" (false, it is a callable
function); "bit 31 is a commit enable" (false).

---

## 7. Avenues we have NOT chased

This is the section we most want reviewed.

1. **Reproduce the complete board-B SVP startup under one owner.** The exact
   board-B `display.bin` (`4380f1b3...`) and support files are available and
   already extensively disassembled.  The remaining question is not what
   firmware to run, but how to hand ownership from boot firmware to Linux
   without the raw-reset hard lock.  Stock order is: load `cpu_comm_dev`, load
   the MIPS image/config/TSE set through `mipsloader`, wait for CPU_COMM, restart
   MIPS, wait roughly 800 ms, complete `THal_Vp_Init`, then let HWC resume the
   SVP display and DECD.

2. ~~**Port the board-B GE2D control ioctls needed at SVP resume.**~~
   **RESOLVED 2026-08-28.** Both were disassembled to their relocations, and
   three of the four resume steps are already ported:

   | HWC step | stock | our side |
   | --- | --- | --- |
   | `powerCtrl(1)` | ge2d `0x4680` -> `__pm_runtime_resume(dev, 4)` | `DECD_IOC_PM_HINT` on |
   | `powerCtrl(0)` | ge2d `0x4680`, zero payload -> `__pm_runtime_idle(dev, 4)` | `DECD_IOC_PM_HINT` off |
   | `DecoderDisplay::enable(1)` | decd enable | `dec_enable()` |
   | frame submit | decd `0x40706400` | patch 0067 |
   | `iommuEnable()` | ge2d `0x4681` -> `sunxi_enable_device_iommu(2, 1)` | **was missing** |

   `0x4681` is four instructions -- `mov r1,#1; mov r0,#2; bl
   sunxi_enable_device_iommu` -- so it is master 2, translation on. Master 2
   is `dec@5600000`, this device's own window, shared with `ge2d@5240000`. The
   stock DTB ships it *bypassing* (`<&mmu_aw 2 0>`) and turns translation on at
   runtime, right before presenting video. Our `dec` node carried no `iommus`
   property at all, which is why every DECD test to date fetched untranslated
   physical addresses -- the four-slot file held `Y=0x6c500000` rather than an
   IOVA. Patch 0069 adds it, out of series: master 2 is shared with the live
   adopted scanout, so translating it will fault U-Boot's logo fetch.

   **Run 2026-08-28. The port works; the boot is confounded.** DECD queued
   proper IOVAs (`0x05600070 = 0xFFC00000`, `0x05600084 = 0xFFCE1000`, delta
   `0xE1000` = one luma plane) and fetched them at 60 IRQ/s with zero further
   faults and zero panfrost interrupts. But the panel was black, and a
   **positive control failed**: repointing the live OSD channel at DECD's own
   IOVA, with its READY latch consumed and no fault, still rendered nothing --
   while vsync stayed at 59.7 Hz. One translation fault at attach
   (`0x6c332000`, master 2, inside U-Boot's logo carveout) appears to wedge the
   AFBD **fetch** engine for the rest of the boot; latch consumption and vsync
   only prove the **commit** path. So this boot says nothing about DECD routing
   and must not be cited as a negative for the no-GPU path.

   The concrete unblock: map the display carveout into the same IOMMU domain
   (identity mapping for `0x6c100000`, via a reserved-memory region with
   `iommu-addresses`, or mapped by the driver at attach) so the adopted scanout
   survives translation. Master 2 cannot be translated on a display Linux
   inherited rather than programmed.

   **Done, as patch 0070, and it works (2026-08-28).** With the carveout
   identity-mapped the board boots with master 2 translating, zero page faults,
   and the **logo still on the panel** -- the first healthy fetch engine under
   translation. Getting there also exposed a real `sun50i-iommu` bug: the driver
   cannot map before attach, because `sun50i_table_flush()` and the page-table
   allocator dereference `sun50i_domain->iommu`, which only `attach_domain()`
   sets, so any `IOMMU_RESV_DIRECT` region NULL-derefs inside
   `iommu_device_register()`. Fixed by binding the instance in
   `domain_alloc_paging()`, which already receives the device. That fix is
   upstream-shaped and independent of this project.

### The clean negative, at last (2026-08-28)

On that one boot, fetch engine verified working throughout:

| step | state | panel |
| --- | --- | --- |
| boot, master 2 translated, carveout identity-mapped | 0 faults | **logo** |
| DECD holding red NV12 | 60 IRQ/s, `Y=0xFFE00000` `C=0xFFEE1000`, 0 faults, panfrost 0 | logo |
| logo channel disabled | DECD still 60 IRQ/s, 0 faults | **black** |
| OSD repointed at DECD's own IOVA | fetched 1.38 MB, then ran off the mapping | **white -- panel responded** |

The last row is the control 0069 could not produce. Panel, raster and IOMMU all
work; DECD's buffer is fetchable under translation; the frame is genuinely red
(`Y=0x81, U=0x5A, V=0xF0`). So the black is **specifically DECD's output not
being routed** -- not a wedged engine, not a bad address, not an empty buffer.

And throughout, unchanged:

```
0x05600010 = 0x03000010    video source 0: enable[1:0]=0, format[15:8]=0
```

Frames at vsync, addresses translated exactly as stock's hardware sees them,
all three ARM-side resume steps reproduced -- and the video source is still
neither enabled nor formatted. Stock's only writer of that field,
`dec_reg_video_channel_attr_config()`, is dead code. Nothing ARM-side programs
it, and nothing ARM-side can make it unnecessary. **The MIPS firmware fed by
DECD's VideoInfo dma-buf is the only remaining candidate**, and U-Boot parks it
on every boot tested. That makes "MIPS running + DECD submitting" the one
experiment left, and it is now well-posed rather than a guess.

**Operational rule, reproducible:** one IOMMU page fault on master 2 wedges the
AFBD fetch engine for the whole boot -- seen on the 0069 boot and again here
(fault at `0xFFF52000`, one page past the DECD buffer end at `0xFFF51800`;
panel stuck white, unrecoverable by register writes). Budget one fault per boot
and design experiments so the fault comes last.

3. ~~**Resolve the project-0x34 scheduler failure before another live MIPS
   handoff.**~~ **CLOSED 2026-08-28 -- there was no scheduler failure.** Under
   `0x34` the firmware is healthy for 60 s (tick identical to `0x33`, zero
   exceptions), a no-op CALL round-trips in 1 ms, and `THal_Vp_Init` returns
   `1`. See the retraction in section 0. What survives from this item is the
   Linux-side work: replace the arm64 guessed-pointer conversions with explicit
   shared-memory offsets/physical handles, register callable component ids
   rather than MIPS handler addresses, and add tracing for inbound MIPS-to-ARM
   calls. Original text follows.

   The authenticated board-B firmware's call table and transport
   were reconstructed, and clean round trips were completed for black-screen,
   all screen-cover selectors, picture-mode and `THal_Vp_SetSource(2)`.  None
   changed visible composition.  More importantly, the corrected stock-shaped
   `THal_Vp_Init([0, 1, physical_buffer])` now completes under project 0x33:
   every adapter boundary fires, the RPC returns `1`, and sampled output is an
   exact copy of the firmware's VP state.  Under project 0x34, the same CALL is
   acknowledged and enqueued but never reaches the generic CALL worker, before
   the VP adapter.  Compare the two ProjectID TSE paths, capture the runnable
   ThreadX thread/queue state, and verify the project ID stock actually gives
   MIPS.  In parallel, replace the Linux arm64 guessed-pointer conversions with
   explicit shared-memory offsets/physical handles, register callable component
   IDs rather than MIPS handler addresses, and add tracing for inbound
   MIPS-to-ARM calls.  Only then combine it with display-CPU resume.

4. **Determine which side services DECD/display interrupts after the handoff.**
   Direct ARM submission is stable only with ARM IRQ 331 masked; blindly
   running MIPS and the ARM reconstruction together locks the SoC.  A correct
   design must assign each level interrupt and shared register block to one
   owner, or implement the same coordination as the stock stack.

5. **A stock playback register trace remains useful but must be captured
   safely.** Booting Android on this unit risks the Debian filesystem because
   both use the shared `UDISK`; do not switch the live board merely to obtain
   it.  If a disposable image/board becomes available, diff TVTOP, GE2D power,
   IOMMU, VBlender, DECD, CPU_COMM flags and MIPS status before and during a
   real video-tunnel frame.

6. **Three LVDS read-modify-write operations in `init_osd_plane` were skipped**
   (runtime-computed values against `0x051c001c`/`0x051c0010`). Probably
   irrelevant, but untested.

7. **Mixer registers beyond the table's range**: `0x0525c038 = 0x00000040` and
   `0x0525c03c = 0` are live but not written by any DE variant. Never probed.

8. **Only DE variant 1 was mirrored.** Variants 2, 5 and 6 also carry 1280x720
   geometry and differ in ways we did not diff.

9. **Is the second AFBD channel physically present on this die?** H713 may be a
   harvested/reduced variant. We have no datasheet. A fused-off channel would
   explain every result exactly, and we have no way to distinguish that from
   "present but not enabled".

10. **`decd.ko` -- now the primary route, not an unexplored avenue.** Stock HWC
    calls its frame-submit ioctl for video and supports an uncompressed dma-buf
    path. See section 0. The remaining work is a controlled Linux reproduction,
    not another direct write to guessed format/address registers.

---

## 8. Questions we would most like answered

1. On Allwinner display hardware of this generation, what actually gates a
   scanout channel being *serviced* — as distinct from configured? What makes a
   READY/commit latch get consumed?
2. Is a never-consumed commit latch a known signature of a specific condition
   (clock gated, channel fused off, mixer not routing, missing enable elsewhere)?
3. Given the mixer has two window slots both programmed with identical
   geometry, does that indicate two usable layers, or is that pairing something
   else (e.g. double-buffered registers for one layer)?
4. Is there a plausible reason a vendor would ship a display controller with
   two plane register banks and use only one — beyond simple product
   segmentation?
5. How does DECD's four-slot Y/C/info queue become the displayed source? The
   photographed test establishes that changing DECD state does not mutate the
   active packed-OSD fetch at `0x05600178`; it does not establish that the DECD
   output is absent. Is the selection made by the MIPS display firmware, the
   mixer, the `+0x30c` mux state, or a vendor display ioctl/RPC?

---

## 9. Constraints

- No datasheet for H713 display, no vendor source for `display.bin`.
- FEL recovery works, but `sunxi-fel uboot` does **not** on this SoC (SPL loads,
  post-SPL handoff fails), so U-Boot changes require flashing.
- The panel is brought up by U-Boot; Linux cannot re-initialise it, so a broken
  display needs a reboot.
- We have full stock firmware, both eMMC images, and can boot vendor Android.

---

## 10. LATE AND POSSIBLY DECISIVE: the two "planes" may be LVDS ports

Added after the brief was written, prompted by the operator noting the panel is
LVDS. The vendor's own `panel_config.ini`, shipped beside the MIPS firmware and
never previously read:

```
ProjectID       = 52
PanelWidth      = 1280      PanelHeight = 720
PanelDualPort   =   0       <-- single-port LVDS
OddEven         =   0
PanelODDDataCurrent  = 7    <-- odd/even lane drive strengths exist
PanelEvenDataCurrent = 7
PanelHTotal = 1360   PanelVTotal = 760   PanelDCLK = 62000000
```

Independently, the peer project's `LogoRegData` parser decodes `0x05600140`
— the AFBD channel-1 control register — as carrying a **`dual_port` bit**.

**Hypothesis: AFBD "channel 0" and "channel 1" are the odd and even LVDS
ports, not two compositing layers.** If so, channel 0 is unused *hardware* on a
single-port panel, and no amount of configuration will ever make it serviced.

This fits every negative result in this investigation, with nothing left over:

| observation | explained by |
| --- | --- |
| ch0 READY latch never consumed, ch1's consumed every vsync | no second port is clocked |
| no `LogoRegData` variant touches ch0/OSD0 | no shipped panel here is dual-port |
| per-plane LVDS register pairs (`0x051c0060`/`006c`, `0x051c0180`/`019c`) | one set per LVDS port |
| mixer window pairs holding *identical* full-screen geometry | one per port, both fed the same frame |
| configuring ch0 correctly at bring-up still inert | the port does not physically exist in this build |

It also reframes the goal. If there is only ever one scanout channel, the
question was never "how do we open a second plane" but **"how do we make the one
channel fetch YUV"** — which is the reviewer's point 5 arrived at from a
different direction, and much more strongly.

**Cheapest tests of this hypothesis:**

1. Decode the `dual_port` bit in `0x05600140` (live value `0x03001901`) and see
   whether toggling it changes what channel 0 does. One register.
2. Check whether any of the 8 DE variants in `LogoRegData.bin` sets that bit —
   if some do, those are the dual-port panels, and the variants that set it
   should *also* be the only ones touching ch0. If that correlation holds, the
   hypothesis is confirmed from the file alone, with no hardware.
3. Look for a `PanelDualPort = 1` product in the 13 `ProjectID_*.TSE` sets.

Test 2 is free and needs no board. **Do it before anything else in section 7.**

### Corroboration, 2026-08-25

**Hardware-verified, independent of this project.** The operator has driven this
same panel from a Geekworm HDMI-to-LVDS board **configured as 1-port LVDS**, and
it worked. That confirms `PanelDualPort = 0` from equipment with no stake in the
theory — the panel is genuinely single-port.

**And the file agrees.** If AFBD channels map to LVDS ports, no shipped variant
should differ in port configuration, since none of them touches channel 0.
Checked across all 8 DE variants:

```
DE 0: ctrl=0x03001901  global=0x80000020  1920x1080
DE 1: ctrl=0x03001901  global=0x80000020  1280x720
DE 2: ctrl=0x03001901  global=0x80000020  1280x720
DE 3: ctrl=0x03001901  global=0x80000020  640x360
DE 4: ctrl=0x03001901  global=0x80000020  864x480
DE 5: ctrl=0x03001901  global=0x80000020  1280x720
DE 6: ctrl=0x03001901  global=0x80000020  1024x608
DE 7: ctrl=0x03001901  global=0x80000020  1024x608

distinct ctrl values: {0x03001901}
```

**Identical everywhere**, across resolutions from 640x360 to 1920x1080. Only
geometry varies between variants; the channel/port configuration never does.

### What this does and does not establish

**Established:** the panel is single-port LVDS (hardware); no shipped
configuration enables a second channel or differs in port setup (file); channel
0's commit latch is never consumed (live board).

**Still inference:** that channel 0 *is* the second LVDS port. An absent or
fused-off block would produce identical evidence, and we cannot distinguish
those without a datasheet.

**Why it does not matter much which:** both readings give the same practical
answer. Channel 0 is not usable on this hardware, and the video path has to go
through the single channel that works. The remaining question is therefore
**"how do we make one channel fetch YUV"**, not "how do we open a second plane"
— and the two-plane framing that shaped this entire investigation was wrong from
the start.

---

## 11. Update, 2026-08-30 (later) — what changed, and what we most want a second opinion on

Four things happened after section 0's last status note. One of them retracts a
claim made earlier the same day; read that first so it does not get propagated.

### A retraction, so it does not spread

It was asserted here and elsewhere that **"a DECD submit breaks the display path
for the rest of the boot"**. That is **withdrawn**. Re-tested on a fresh boot
with the panel confirmed live immediately before each step (a known pattern
written into the scanout buffer and visually confirmed), three submits in two
different pixel formats left the panel unchanged.

No measurement in the original was wrong. The bisection's four rows came from
**two different boots**, and the deciding row came from one where the panel was
never confirmed working after Linux booted and before the first submit.

The corollary is withdrawn too: earlier "still black" null results — hiding the
OSD, the internal blue generator, the source-enable and mixer sweeps — are **not**
known to have been measuring a dead path. They stand as originally reported.

One boot's panel genuinely was black with the OSD channel enabled, its buffer
holding white, both commit latches consuming and the raster running. **Cause
unidentified.**

### The MIPS sees the peripherals at a different address

Every previous attempt to find display-register accesses in the firmware image
failed, in every encoding. The reason is an offset, not an absent access path:

    MIPS address = ARM physical + 0xB5000000

    ARM 0x05600000  AFBD           ->  MIPS 0xba600000   (kseg1, uncached)
    ARM 0x051c0000  LVDS PHY       ->  MIPS 0xba1c0000
    ARM 0x05140000  display route  ->  MIPS 0xba140000

**If you recognise `+0xB5000000` as a standard MIPS-side aperture on this SoC
family, that would be useful to know** — we derived it from correspondence and
it is not documented anywhere we have.

With it, the firmware is visibly reading and writing the video source control
register at 11 store sites, which converts the earlier *inference* that the
firmware programs the video source into readable code.

### The pixel-format question is answered and confirmed

The firmware resolves the format from a bounds-checked jump table (16 entries),
mapping the metadata structure's format selector to the byte it writes into the
source control register's bits 15:8:

    0 -> fmt 0      8 -> fmt 4     14 -> fmt 7        1,3,5,10,13 -> error arm, writes 0
    2 -> fmt 1      9 -> fmt 5     15 -> fmt 6        7 -> stores nothing at all
    4 -> fmt 2     11 -> fmt 4
    6 -> fmt 3     12 -> fmt 5

Confirmed on hardware, control run first: sending 11 gives `0x03000413`
(fmt 4, what we had been getting); sending 0 gives `0x03000013` (fmt 0, exactly
what stock plays at). So the metadata field is genuinely the resolver's input,
and our client now sends 0.

**This is necessary but not sufficient** — forcing fmt 4 onto a working stock
system produces a broken but plainly visible picture, not black.

### The thing we would most like an outside view on

Every submit leaves the firmware writing a geometry that we cannot explain:

    register                       after submit      expected
    source dimensions              0x02CF04FF        1280x720 minus one   <- correct
    stride                         0x00000500        1280                 <- correct
    "picture size"    0x05600030   0x01E00354        852 x 480  ??
    "second size"     0x0560004c   0x00F00354        852 x 240  ??   (fmt 0)
                                   0x01E00354        852 x 480  ??   (fmt 4)

852x480 on a 1280x720 panel, from a 1280x720 NV12 buffer, while the source
dimensions and stride beside it are correct. Stock during real playback has
`0x0560004c = 0x02D00500` (1280x720). The low half is 0x354 = **852** in every
case; the high half tracks the chroma subsampling, halving from 480 to 240 when
the format goes from 4 to 0 — which at least suggests the field is a plane
height and the firmware is computing it consistently from *something*.

Notably this geometry does **not** break composition: the panel keeps showing an
unrelated marker image while these values are live and unrestored.

**Questions we would value answers to:**

1. On Allwinner display hardware of this generation, what is the usual meaning of
   a triple like {source dimensions, picture size, second size} on a scanout
   channel? Is "picture size" an output/scaled size rather than a source size?
2. Does 852x480 suggest a default or fallback output window — e.g. a
   letterboxed 480p — that the firmware falls back to when some field of the
   submitted metadata is missing or unrecognised?
3. What gates a scanout channel being *serviced* as distinct from configured?
   That remains this document's central unanswered question (section 8, item 1),
   and everything since has narrowed rather than answered it.

### The 852x480 geometry is resolved: HWC uses canonical 1080p coordinates

Follow-up disassembly of the shipped `hwcomposer.ares.so` resolves this without
a stock memory capture.  The library exports its `VideoInfo` methods, so the
metadata construction is directly readable:

- `VideoInfo::setOutputWindow()` writes the real output window to
  `+0x18..+0x24`, then unconditionally writes the crop as
  `{0, 0x7800, 0, 0x4380}` at `+0x6c..+0x78`.
- `VideoInfo::setDisplayFrame()`, called with the same full-screen rectangle as
  both arguments, normalises it into the same 1920x1080, 1/16-pixel coordinate
  space at `+0x7c..+0x88`.
- `VideoTunnel::commitFrameBuffer()` calls both methods in that order.  The
  1920x1080 values are therefore deliberate canonical coordinates, not stale
  source dimensions or an inert firmware default.

Our client originally matched those values.  Commit `6a0a796` changed all four
width/height words to `1280<<4` / `720<<4` under an explicit **UNTESTED** caveat.
Every capture showing 852x480 was taken after that change.  Interpreting a
1280x720 rectangle in the vendor's 1920x1080 coordinate space gives the exact
two-thirds signature observed: approximately 853x480, with the firmware/AFBD's
even-bound rounding accounting for 852x480 in the registers.  The
high-half 480-to-240 change remains the independently-correct chroma
subsampling calculation.

`tools/video/decd-client.c` now restores the stock canonical 1920x1080 crop and
display-frame values while retaining the corrected VideoInfo format selector
0.  This is **confirmed on hardware**.  In one bounded submit, the control state
had `0x05600030 = 0x02D00500` and `0x0560004c = 0x01680500`; after the submit
both values were unchanged.  The submit itself was proven live by source
dimensions changing to `0x02CF04FF`, stride changing to `0x00000500`, source
control changing to `0x03000013`, DMA addresses being installed and the DECD
IRQ count advancing from 0 to 30.

Full readback: [`reference/video-coordinate-space-confirmed-2026-08-30.txt`](reference/video-coordinate-space-confirmed-2026-08-30.txt).

The 1280-wide result matches stock.  Stock's captured second-size high half was
720 rather than 360, so that remaining plane-height difference should not be
silently folded into the solved coordinate-space issue.  The 852x480 component
is closed; it did not explain black output.

### What `+0xB5000000` actually contains

The whole constant is not a standard MIPS alias.  It combines two mappings:

```
ARM-visible physical address + 0x15000000 = MIPS-bus physical address
MIPS-bus physical address   + 0xA0000000 = KSEG1 uncached virtual address
```

For example, ARM `0x05600000` becomes MIPS-bus physical `0x1A600000`, then
KSEG1 virtual `0xBA600000`.  MIPS KSEG1 (`0xA0000000..0xBFFFFFFF`) being an
unmapped, uncached alias of the low 512 MiB is architectural; the
`+0x15000000` peripheral-fabric offset is H713/vendor specific.  The firmware's
byte, halfword and word accessors all implement `addr + 0xB5000000`, followed
by `OR 0x20000000`, after validating the ARM-form address.  No independent
public Allwinner document or source was found that names the `+0x15000000`
aperture, so correspondence plus the accessor code remains the authority for
that half.

The serviced-channel gate is still not identified.  One useful negative from
the same pass: stock `ge2d_dev.ko` parses a DT property named
`panel_dual_port` into `g_OSDData + 0xb0`, but there is no direct read of that
member elsewhere in the module.  It is not an ARM-side switch that this driver
later applies.  Also keep the two latches separate: the DECD video source latch
at `0x05600014` is consumed once the MIPS configures source 0; the still-open
question concerns why OSD/AFBD bank `0x05600104` is not consumed while
`0x05600144` is.

One downstream ambiguity is now closed by hardware.  With a red-band/logo OSD
control visibly live, DECD was proven flowing at approximately 60 IRQ/s with
fmt 0, correct 1280x720 geometry and valid Y/C addresses.  OSD bank 1 was then
disabled and its `0x05600144` commit consumed.  Source-0 enable values 1, 2 and
3 were each committed through `0x05600014` and held for 10 seconds.  The panel
was solid black throughout, then immediately returned to the red-band/logo when
OSD bank 1 was restored.  No IOMMU or DECD fault was logged.  Thus the missing
video is not OSD occlusion, an unset source enable, or an uncommitted shadow
write.  Latch consumption proves the update request is serviced; it does not
prove the source is fetched or selected into the mixer output, which is now the
narrower gate question.

Full result: [`reference/osd-hidden-source-enable-2026-08-30.txt`](reference/osd-hidden-source-enable-2026-08-30.txt).

### Submitted video content is fetched, but not selected into the output

A red-green-red content-dependence control now narrows the remaining gate.
Three accepted submissions used identical metadata and DMA addresses while
changing only a solid NV12 buffer. The panel showed the boot logo continuously,
but composition-page word `0x05000a60` followed the input in exact A-B-A order:

    red    0x0a3c0a3c
    green  0x06080608
    red    0x0a3c0a3c

The green and final-red values were each stable over five one-second samples,
and every submit reached trace stage `0x6103` with a valid fence. The word's
semantics and tap position are unknown, so it must not yet be labelled a CRC or
final-output monitor. Because only the frame-buffer bytes changed, however,
this is strong evidence that hardware samples the submitted video content.

The broad "configured but never fetched" hypothesis is therefore closed. The
missing gate is now later blend participation, routing after this
content-monitor tap, or final output selection.

Full result: [`reference/video-content-fetch-confirmed-2026-08-31.txt`](reference/video-content-fetch-confirmed-2026-08-31.txt).

### Where the effort stands

The vendor's own metadata structure has never been captured during real
playback.  The geometry no longer depends on that capture, because the shipped
HWC builder answers it directly.  A capture remains useful for checking every
other reconstructed field at once: its physical address is readable from a
slot register during playback, and the vendor's debug character device maps
arbitrary physical pages, so reading it is two commands once the board is
booted into the stock firmware.  The obstacle is the vendor boot itself, which
is slow and has failed before.
# Resolution: Linux DECD video reached the projector

The black-screen question this brief tracks is resolved.  On 2026-08-31 a
bounded Linux test displayed the 1280x720 NV12 test frame correctly, with full
colour and correct geometry, then restored the boot logo.  The required state
is source size `0x02cf04ff`, block size `0x002c004f`, Y/C stride `0x500`, source
control `0x03000013` plus consumed commit, chroma gain `0x144c0000`, and
plane-1 selector `0x051c006c = 0x39000000`.  OSD1 remained at the Linux control
value, so the stock OSD1 control is not required.

The preceding minimal route test produced a repeated greyscale version of the
same frame.  A live readback proved that source geometry was still the inherited
1920x1088 / stride-1920 fallback; correcting it removed the distortion and the
known chroma gain restored colour.  Exact evidence and restoration values are
in
[`reference/linux-decd-scanout-confirmed-2026-08-31.md`](reference/linux-decd-scanout-confirmed-2026-08-31.md).
