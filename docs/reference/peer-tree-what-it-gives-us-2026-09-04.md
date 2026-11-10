# What the peer H713 tree still has for us

`local/allwinner-h713-linux/` — an RE port for the HY310, same SoC. It supplied
the coexistence unlock earlier today ([mips-coexistence-lead](mips-coexistence-lead-2026-09-04.md)).
Asked whether it holds more, and it does: **it very probably has the signal we
are missing.**

Treat as leads to verify, not fact — it is a peer RE port, and note its own
display status is *"broken picture"*, so it has not solved scanout either. What
it *has* solved is driving the MIPS from Linux.

## 1. The missing signal is most likely `SetSource`, not a per-frame notify

Our open question is what tells the window layer a frame exists. We established
there is no per-frame CPU_COMM routine in the 82-entry table. The peer's answer
reframes it: **you do not notify per frame — you select a source once, and the
WCE composites from it continuously.**

From `userspace/hy310-hdmird/README.md`:

> Stock-android RPC trace shows tvserver makes **12 calls during boot and 12
> more during HDMI source-switch**. The MIPS-side state machine reaches Running
> state only after this sequence completes.
>
> **Source-switch sequence:** `SetSource(N)` + reapply picture-quality defaults.
> MIPS responds with `MipsHalCallback_SignalChange(Para=3)` when TMDS lock
> achieves.

`THal_Vp_SetSource_1_000` (`0xeaf13de5`, `0x8B10A218`) is in our own registered
table, and `display_cfg.xml` documents the enum: **0 Dummy, 1 VideoDecoder,
2 Image, 3-6 HDMI1-4, 7-9 CVBS, 10 ATV**. Our `power_on_setting` sets
`source_id=1` as a *config default* — nothing has ever *called* SetSource.

That fits every observation: the WCE sits in its bring-up configuration, logs
`bypass`, ignores frames in the ring, and the panel is black — because no source
has been selected at runtime.

## 2. `Vp_Init` needs three parameters, and the third is an address

The exact call, from `hy310-hdmird/src/main.cpp:282`:

```c
call_routine(cc, "THal_Vp_Init", {0, 0, kVpInitStagingPhys});
```

with the comment:

> ParaCount=3 with Para[2] = phys-addr of a **64KB staging region in shmem**.
> MIPS handler (`sub_8B109F04`) does `memcpy(dst=Para[2],
> src=MIPS .bss @ 0x8B48C2F0, n=55296)`.

`0x8B109F04` is `THal_Vp_Init_1_000` in our table too, at exactly that address.
`Para[2] == 0` is what makes the firmware do a NULL 55 KB memcpy and corrupt
memory — the mechanism that explained our four locks.

**The address transfers directly.** The peer uses shmem base + 4 MB =
`0x4E700000`; our device tree has `cpu-comm@4e300000` at 5120 KiB — the *same*
base — so `0x4E700000` is inside our region too.

## 3. What of their init sequence applies to us

Their 12-call boot sequence is largely HDMI-specific and we can skip most of it:

| step | applies to us? |
| --- | --- |
| picture defaults (BacklightLevel, TNR, SNR, DCI, BlackExtension, PictureMode, VideoRange) | **probably yes** — the source-switch reapplies them, so the WCE may expect them set |
| `CvbsSetPedestalMode` | no |
| 3x `HDMI_SetPortMap`, `SetHDCP22Key`, `SetHPDTimeInterval` | no — HDMI input only |
| `DisableBlackScreen` | **yes** — a black-screen flag left set would explain a black panel on its own |
| `Vp_Init(0, 0, 0x4E700000)` | **yes, the gate** |
| `RegisterSignalChangeCallback` | **yes** if we want the MIPS to tell us anything back |
| `SetSource(1)` = VideoDecoder | **yes, the likely missing signal** |

`DisableBlackScreen` deserves flagging on its own: `THal_Vp_DisableBlackScreen_1_000`
(`0xb66041d8`) is registered on our firmware, and we have never called it.

## 4. Their MIPS→ARM callback mechanism

`MipsHalCallback_SignalChange` is **installed ARM-side** via `install_routine`,
not registered on the MIPS. So the CPU_COMM channel is bidirectional and the
firmware calls back into ARM-side routines we register. That is how we would
learn the source actually locked, rather than polling the elog.

## 5. Two smaller things worth taking

- **TVTOP first.** `docs/subsystems/display.md`: *"TVTOP (bus fabric)
  `0x05700000` — MUST program first — gates all sub-blocks."* Our `decd.ko`
  map already has `dec_reg_top_enable` on `0x05700000`; worth confirming it runs
  before anything else in a live-core order.
- **Their pipeline diagram** confirms the shape we inferred independently:
  source -> MIPS WCE -> NV12 in DRAM -> AFBD -> VBlender -> LVDS -> DLPC3435.

## The plan this implies

1. Bring a CPU_COMM client up on our side (`tools/display/cpu-comm-probe.c` and
   `cpu-comm-enable.c` exist; the peer's `libhy310cpucomm` is a reference).
2. With the core alive via `h713_disp init 0x34`, call in order:
   `Vp_Init(0, 0, 0x4E700000)`, the picture defaults, `DisableBlackScreen`,
   then `SetSource(1)`.
3. Watch the elog for the WCE waking up — `UpdateWce`, a new `SetSignalInfo`,
   and window recalculation with a non-zero timestamp.
4. Only then submit frames, with `ring_writes_max` bounded so the 60 Hz
   repetition cannot lock the SoC.
5. If the WCE then reports geometry for a **1080p** source, watch for
   `Need to enable panel down scaler` instead of `bypass` — which is the whole
   scaling question, answered by the firmware itself.
