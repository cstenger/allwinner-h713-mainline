# `Vp_Init` fired, and it worked — self-verified

2026-09-04. Board healthy throughout; core alive before and after.

## The call and its proof

```
cpu-comm-probe THal_Vp_Init_1_000 0 0 0x4E700000
  CPU_COMM_CALL_BEGIN params=3 arg0=00000000 arg1=00000000 arg2=4e700000
  CPU_COMM_CALL_OK    elapsed_us=74888  nret=1  ret0=00000001
```

The read-before/read-after check makes this self-verifying rather than a claim:

| | sha256 (first 32) | nonzero bytes |
| --- | --- | --- |
| before | `35295da1d5eca0b6db3168c0a64a2d61` | **0** |
| after | `bfcda093d713f081cfe72254d2524bd8` | **17856** |

The destination was entirely zero beforehand — which also retires the residual
worry that `0x4E700000` might be in use by the cpu_comm allocator — and
afterwards holds a lookup table:

```
00 00 05 00 0b 00 11 00 17 00 1d 00 23 00 29 00 ...
```

16-bit entries 0, 5, 11, 17, 23, 29, 35, 41 … an arithmetic progression, step 6.
Consistent with the "factory-PQ" data the disassembly says is copied from
`0x8b48c304`. **The 55296-byte memcpy demonstrably happened**, exactly as
`THal_Vp_Init` at `0x8b109f04` describes, and the parameter convention settled
in [vp-init-parameter-convention](vp-init-parameter-convention-2026-09-04.md) is
correct.

## What the firmware did with it

```
D/hal  THal_Vp_Init() ENTER
I/app  (hal_func.cpp 268) OnHalMiscInit
D/bs   ObtainBlueScreenHandle, handle 0x0,     level: 0, Name: hal
D/bs   ObtainBlueScreenHandle, handle 0x10000, level: 1, Name: hal
D/bs   ObtainBlueScreenHandle, handle 0x20000, level: 2, Name: hal
D/hal  THal_Vp_Init() LEAVE
D/hal  THal_Vp_RegisterSignalChangeCallback() ENTER / LEAVE
```

Real work: app-level init, and it **registers the signal-change callback
itself** — we did not call that separately.

## The blue-screen subsystem is a new and promising lead

`Vp_Init` obtains **three blue-screen handles at levels 0, 1 and 2**
(`./blue_screen.cpp:96`). This is the classic TV-firmware "no-signal / mute"
overlay, and it is a strong candidate for the black panel:

**the firmware may be displaying its own no-signal screen — configured black —
over everything, which would explain why our AFBD source and selector writes
are accepted and never reach the glass.**

That fits every observation: writes take, latches are consumed, the WCE never
recomputes, and the panel stays uniformly black rather than showing garbage.

There is a `bs` command in the MIPS debug shell's top-level list, so the state
is queryable, and `blue_screen.cpp` is a named source file to disassemble
against.

## Still not composited

A second `SetSource(1)` after `Vp_Init` returned `CALL_OK` and logged nothing —
consistent with an idempotent early-out, since the first call already set
`hal_source_id: 1`. There is still **no `UpdateWce`, no `CalcWindow`, no
`PanelWinNode::WriteReg`**, and `0x05600010`/`0x051c006c` remain at their
firmware-chosen values.

So the sequence gate is passed and the source is selected, and the window layer
still has no *signal* to compute against.

## Next, in order of cost

1. **Interrogate the blue screen** — `bs` in the debug shell, and disassemble
   `blue_screen.cpp`'s handles. If a level-0 overlay is up, finding its disable
   is cheap and would be a complete explanation of the black panel.
2. **Find what constitutes "signal" for source 1.** The VideoInfo descriptor
   carries width/height/stride/fps but nothing observed shows the firmware
   consuming it; `THal_Vp_GetSignalInfo` is a known stub.
3. The rest of the peer's 12-call sequence — picture defaults — which we have
   still not sent.
