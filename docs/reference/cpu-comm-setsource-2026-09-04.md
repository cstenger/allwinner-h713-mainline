# CPU_COMM client up, `SetSource(1)` delivered — and inert

2026-09-04, live core, board survived throughout.

## The client already existed and works

No new client was needed. `tools/display/cpu-comm-probe.c` (binary staged at
`/root/cpu-comm-probe`) resolves names from the **live** firmware table at
`/proc/cpu_comm/routines` and issues ioctl `0xC0087F26`. The driver is
`/root/hy310-cpu-comm-next.ko`:

```
cpu_comm: initialized (ShMem=0x4e300000, 5242880 bytes)
/proc/cpu_comm/routines   104 entries
```

`ShMem=0x4e300000` matches the peer tree's base exactly, so its
`Para[2] = base + 4 MB = 0x4E700000` transfers to us unchanged.

## The finding: the live source is Dummy, not VideoDecoder

```
cpu-comm-probe THal_Vp_GetSource_1_000 0x4d830000
  CPU_COMM_CALL_OK  elapsed_us=74668  nret=1  ret0=00000000
```

**`ret0 = 0` — source 0 = Dummy.** `display_cfg.xml` sets
`power_on_setting source_id=1` (VideoDecoder), and the elog shows the firmware's
own app running `AppTopSetSource` and `THiDTVPro.cpp:57 "Enable VideoDeocer [1]"`
at bring-up — yet the live source reads Dummy.

That is a clean explanation for the whole picture: with no real source selected,
the WCE has nothing to composite, which is why it sits in its bring-up window
configuration, logs `bypass`, ignores frames in the ring, and the panel is black.

## `SetSource(1)` is accepted but changes nothing

```
cpu-comm-probe THal_Vp_SetSource_1_000 1
  CPU_COMM_CALL_OK  component=eaf13de5  elapsed_us=74557  nret=0

cpu-comm-probe THal_Vp_GetSource_1_000 ...
  CPU_COMM_CALL_OK  ret0=00000000        <- still Dummy
```

**The call genuinely reached the firmware.** The elog shows the session at
timestamp 1107456+: spinlock acquire/release on `AE300018`, `cpu0 - is APPready`,
`Session3(RETURN): ParaCount:1`, `WAIT ACK completion`. A 74 ms round trip, not a
local no-op.

> ### CORRECTION — `SetSource` DID work. This section's conclusion was wrong.
>
> The claim of "no app or WCE reaction" came from a grep that filtered out the
> `hal` and `app` tags and from `GetSource` returning 0. The firmware log
> actually shows the call landing and the window manager being notified:
>
> ```
> D/hal     [1104371] (thal_display_source.cpp 31) THal_Vp_SetSource() ENTER
> D/hal     [1104371] (thal_display_source.cpp 32) hal_source_id: 1
> I/app     [1104371] (app_top_projector.cpp 974) AppTopSetSource
> D/win_mgr [1104371] (window_manager.cpp 111)    SetSignalInfo
> I/mem_agn [1104372] (memory_agent.cpp 71)       update_onoff
> D/hal     [1104372] (thal_display_source.cpp 37) THal_Vp_SetSource() LEAVE
> ```
>
> **The source switch reached `AppTopSetSource` and the window manager ran
> `SetSignalInfo`.** So the CPU_COMM path into the window layer works, and this
> is the first time we have driven it.
>
> What does *not* follow is any window recomputation: **no `UpdateWce`, no
> `CalcWindow`, no `PanelWinNode::WriteReg`.** The WCE was told the signal
> changed and did not act, which is what you would expect when the selected
> source is not actually producing a signal. AFBD source 0 reads
> `0x05600010 = 0x03000010` — bits [1:0] clear, i.e. **the video source is
> still disabled** — and the LVDS selector is `0x29000000`, the RGB/OSD side.
>
> `GetSource` returning 0 is a separate puzzle and not evidence the switch
> failed: `SetSource` logged `hal_source_id: 1` on the way in. Most likely
> `GetSource`'s single argument is not an output pointer and `ret0` is a status
> rather than the source id.

`DisableBlackScreen(0)` was also delivered — `CALL_OK` in 79.8 ms, and
`thal_display_misc.cpp:57 THal_Vp_DisableBlackScreen() ENTER` in the log — with
no register change and no WCE activity following it.

## Why, most likely: `Vp_Init` has not been called

The peer's stock RPC trace is explicit that the source switch only takes after
the init sequence, and that `THal_Vp_Init` is the gate. Our U-Boot preboot
proves *readiness* (`MIPS READY`, `application readiness proven`) but the elog
shows `Vp_Init` only being **registered**, never called.

**A parameter-count discrepancy to resolve before trying it.** Our live table
declares:

```
 839  0x1c6ff747    1   1024  THal_Vp_Init_1_000
```

i.e. **ParaCount 1** (and a 1024 field the other routines leave at -1), while the
peer records stock sending **ParaCount 3** with `Para[2]` the staging address, and
notes *"Stock-LIVE-elog confirms Session1(Call) ParaCount=3."*

This matters because `Vp_Init` with `Para[2] == 0` is the call that makes the
firmware memcpy 55296 bytes to a NULL destination and corrupt memory — the
mechanism behind four of today's locks. **Do not fire it until the parameter
convention is settled**: whether our probe can send 3 params against a table
entry declaring 1, and whether the 1024 field is the payload size.

## Cheaper things to try first

- **`THal_Vp_DisableBlackScreen_1_000`** (`0xb66041d8`, 1 param) — registered,
  never called, and in the peer's boot sequence. A latched black-screen flag
  would explain a black panel by itself, and it is a single well-formed call.
- Re-read `GetSource` after a longer settle; the switch may be asynchronous and
  the peer notes the MIPS answers with a `SignalChange` callback rather than
  changing state synchronously.

## State

Board healthy throughout: core `0x00000001`, zero oops, CPU_COMM up, DECD loaded
with `ring_writes_max=1`, one frame in the ring, panel black.
