# Handoff — 2026-09-04/05: the MIPS window layer becomes reachable

One long session against [mips-window-layer-plan.md](mips-window-layer-plan.md).
It started with the window layer unreachable and every scaling route closed. It
ends with Linux booting under a live MIPS, the firmware's debug shell answering,
its log readable, and the CPU_COMM control path into the window layer driven for
the first time — but still no picture.

Cost: **five power cycles**. Everything below is measured; inferences are
labelled.

## The headline

**Coexistence was never a hardware limit.** Four attempts to run Linux with the
MIPS alive hard-locked the SoC, and the reason was ours: every one re-released
an *already-quiesced* core with `mw.l`, which cold-restarts the firmware with no
ARM-side handshake. An un-initialised MIPS then performs a wild memcpy into DRAM.

The fix needs no code and no flash:

```
cold power cycle -> interrupt autoboot
h713_disp init 0x34        # full bring-up + handshake, core LEFT RUNNING
setenv bootargs <production> initcall_blacklist=h713_afbd_platform_driver_init
run bootcmd
```

`init` is the one command that brings the firmware all the way up and **does not
quiesce** — no "MIPS core quiesced" line. Result: full Linux boot to a login
prompt with `0x0306101c == 1`, zero oops. `h713_disp logo-live` is *not* in the
flashed bootloader; `init` has the property.

## What became possible, in order

| capability | evidence |
| --- | --- |
| Linux + live MIPS | login prompt, core `1`, 0 oops |
| MIPS debug shell driven | `cmds` returned 917 bytes and a `VS:/$` prompt |
| Firmware log readable | `display_cfg.xml` elog `level` 1->5 **and** `mode` 1->2 |
| Frame delivered to a live core | `ring_writes_max=1`, Y/C/VideoInfo populated, no lock |
| CPU_COMM into the window layer | `SetSource(1)` -> `AppTopSetSource`, `SetSignalInfo` |
| `Vp_Init` gate passed | `ret0=1`, destination 0 -> 17856 nonzero bytes |

### The elog is the most valuable thing gained

Two settings, and **both are required**: `level` 1->5 *and* `mode` 1->2 (buf).
Level alone, with `route=0` (uart), **breaks the readiness handshake** —
`MIPS=00000000`, "firmware readiness not proven", teardown. Buffer mode logs to
DRAM around `0x4b272000`, readable from Linux like the shell ring.

It repeatedly answered for free what experiments were costing power cycles, and
it contradicted several of my inferences. **Trust it over reasoning.**

## The DECD lock, resolved

With a live core, a real frame submit locked the SoC while `decd-client blue`
did not. Three mechanisms were proposed; the first two were wrong:

- ~~we publish an IOVA in `0x05600098` and the MIPS dereferences it~~ — refuted:
  it reads `0x4D941000`, a real physical address in `decoder@4d941000`.
- ~~two masters RMW the source-geometry block~~ — refuted:
  `dec_reg_video_channel_attr_config` has no callers in our tree, same as stock.
- **the 60 Hz repetition** — confirmed. Our vsync handler owns SPI 142 and
  rewrites all four ring slots every dirty frame. With `ring_writes_max=1` a
  frame reaches the hardware and nothing locks.

**Architectural consequence:** driving the ring from Linux's vsync is wrong
whenever the MIPS is alive. The firmware owns presentation and advances the ring
itself. Out-of-series `patches/kernel/0094` adds the parameters used here.

## What is now closed

| route | verdict |
| --- | --- |
| Panel down-scaler `0x051c0138` | **dead** — negative on the video path *and* the RGB path, operator watching, pulsed; no commit latch exists in that path so "never latched" is unavailable |
| Poking AFBD to reach the panel | **dead** — the 08-31 known-good recipe (source 0 enable + selector `0x39000000`) is **inert with the core alive**; four pulses, every write accepted, every latch consumed, steady black |
| A descriptor-plus-doorbell handshake | **does not exist** — window apply is `node->vtable[+0x10](node, mask)` with the mask a `lui` immediate at ~70 internal call sites |
| CPU_COMM per-frame notification | **does not exist** — the 82-routine table is complete; `Set/GetImageBufferAddr` are stubs |
| Blue-screen overlay as the cause | **dead** — 3 obtains, **0 enables**, and `blue_screen.cpp` logs every enable |
| `Wce_Enable/DisablePixel2PixelMode` | **dead** — 37 instructions each, only call is the logger |

## The one open question

**What constitutes "signal" for source 1 (VideoDecoder)?**

Everything else is in place: core alive, `Vp_Init` done, source selected
(`hal_source_id: 1`), a frame in the ring. And the WCE still has not
recomputed — no `UpdateWce`, no `CalcWindow`, no `PanelWinNode::WriteReg`, nodes
still at bring-up geometry, `PanelWinNode.cpp:328` still `bypass`, panel black.

A selected source with no signal behind it does not make the window layer
compute. The VideoInfo descriptor carries width/height/stride/fps — decoded in
[videoinfo-descriptor-decoded](reference/videoinfo-descriptor-decoded-2026-09-04.md) —
but nothing observed shows the firmware consuming it, and
`THal_Vp_GetSignalInfo` is a known stub. For HDMI sources the peer sees
`MipsHalCallback_SignalChange` when TMDS locks; the decoder equivalent is
unidentified.

Next, cheapest first:

1. The rest of the peer's **12-call boot sequence** — picture defaults, never sent.
2. `DumpBlueScreenStatus` and the `bs` subcommand table, for direct state.
3. Find the decoder's signal path — who calls `SetSignalInfo` with real geometry.

## Method notes that earned their place

- **`/dev/console` does not reach the UART; `/dev/ttyS0` does.** A streaming
  attempt captured nothing and nearly read as "the firmware said nothing".
- **Narrate risky sequences to `/dev/kmsg`** — it reaches the UART live and
  survives a lock. It is what told us the release died on the final write.
- **Pulse a visual test, do not step it.** The operator cannot see the script's
  output; a single timed change was missed twice.
- **Match a test module's build tree by SHA-256** against
  `/lib/modules/.../*.ko` before building. A mismatched tree probed `-ENOENT`.
- **Files written just before a lock can survive as zero-length.** `sync`.
- **Capture boot output unfiltered.** A `grep` filter nearly turned into a false
  finding about where a boot died.
- The `Bash` tool's cwd persists; a `cd` into a build tree broke later relative
  paths twice and looked alarming both times.

## Board state at handoff

Core alive, `Vp_Init` done, source selected, frame in the ring, DECD loaded with
`ring_writes_max=1`, CPU_COMM up, zero oops, panel black. `display_cfg.xml` on
the FAT still has elog enabled — **leave it**, it is the best diagnostic this
project has. Original at `/root/display_cfg.xml.orig` (md5 `1e7f2c96…`).
