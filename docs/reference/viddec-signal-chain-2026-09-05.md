# The full signal chain for source 1, and where it stops

> Correction, 2026-09-08: event 8 has a registered secondary-vtable callback into
> the state machine. GetFrameInfo copies into its caller's destination, which is
> self+0xb0 only when CheckSignal supplies that address. See
> [the new dispatch trace](dispatch-trace-2026-09-08.md).

Static RE, no board writes. Completes
[what-is-signal-for-source1](what-is-signal-for-source1-2026-09-05.md) and
[viddec-device-vtable](viddec-device-vtable-2026-09-05.md).

## The chain, end to end

```
THidTVPro                         (log tag "dtv", ./THiDTVPro.cpp)
  vtable 0x8b1f8bd4, vptr 0x8b1f8bdc
  owns CVidDecSignalDetector at  self + 0x5a8
  STM state word at             self + 0x5a0

  slot  5 (+0x14)  0x8b146e34   Enable VideoDeocer   -> sets state at +0x5a0
  slot  6 (+0x18)  0x8b146f88   Disable VideoDeocer  -> clears it (0x8b147018)
  slot 16 (+0x40)  0x8b147390   THE STATE MACHINE
        |
        +-- switch ([self + 0x5a0])
        |     0 -> return immediately          <-- no case; the constructor
        |     1 -> 0x8b1474c8                      zeroes it at 0x8b147264
        |     2 -> 0x8b1473e0
        |     3 -> 0x8b147524
        |
        +-- each state calls detector slot 3, then slot 4
              0x8b1473f8 / 0x8b1474dc / 0x8b14753c   jalr 0xc($v0)  = CheckSignal
              0x8b147414 / 0x8b1474f8 / 0x8b147558   jalr 0x10($v0)
        |
        +-- EntrySTMNoSignal / EntrySTMSignalChanging / EntrySTMSignalValid
              traces at 0x8b147588, 0x8b147604, and slot 16's own body

CVidDecSignalDetector             (log tag "vdd", ./vid_dec_signal_detector.cpp)
  vtable 0x8b1f8d78, ctor 0x8b147bbc (28 bytes: store vptr, memset 0xac)
  allocated 0x1d0 bytes at THidTVPro construction (0x8b147210 -> 0x8b147278)

  slot 3 (+0x0c)  0x8b147dd0   CheckSignal
        +-- calls slot 6 via lw 0x18($v0)
  slot 6 (+0x18)  0x8b147834   GetFrameInfo
        +-- reads 0x05600098 / 9c / a0 / a4 by slot index
        +-- rejects 0, rejects < 0x40000000 ("invalid frame info, buf_addr")
        +-- (v & 0x0fffffff) | 0xa0000000, copy 144 bytes to self+0xb0
  slot 5 (+0x14)  0x8b147948   ConvertFrameInfo2SignalInfo
  working buffer self+0xb0, last-latched copy self+0x140
```

So the intended flow is unambiguous: **the `dtv` state machine polls the `vdd`
detector, which reads our VideoInfo descriptor and turns it into SignalInfo.**

## Where it stops

Everything upstream is satisfied and nothing downstream runs:

| link | state on our board |
| --- | --- |
| VideoInfo descriptor present and valid | **yes** — all four slots `0x4D941000`, Y/C populated, `GetFrameInfo` would accept |
| `Enable VideoDeocer` called | **yes** — `I/dtv [20] "Enable VideoDeocer [1]"` at bring-up, which is the write at `0x8b146eb0` that sets `+0x5a0` |
| STM (slot 16) executes | **no** — zero `vdd` records, and only that one `dtv` record all boot |
| `CheckSignal` / `GetFrameInfo` | never reached |
| SignalInfo produced | never |
| WCE recomputes | never — no `UpdateWce`, nodes at bring-up geometry, `bypass` |

**Setting the state is not the same as running the machine.** `Enable
VideoDeocer` writes `+0x5a0` and returns; slot 16 is a separate virtual call
that something must invoke, and on our board nothing does.

## The one remaining unknown

**Who calls `THidTVPro` slot 16 (`+0x40`).** By analogy with the WCE — whose
node walk dispatches `node->vtable[+0x10](node, mask)` from ~70 internal sites —
this will be a periodic task or scheduler that walks registered devices.
`IDeviceVidDec : IDevice` and the `BaseDev` strings in slots 3, 4, 9 and 10 say
there is a device framework doing exactly that.

Three ways to find it, all static and all cheap:

1. Scan for `lw $reg, 0x40(vt); jalr $reg` and filter to callers that also touch
   `dtv`/`vdd` code — the technique that found the WCE apply dispatch.
2. Find what registers a `THidTVPro` into the device framework; the `BaseDev`
   slots are the interface it presents.
3. Look for the periodic task itself. The elog's `sys` heartbeat
   (`app_init.cpp:259`, every 5 s) proves a scheduler runs; something similar
   should drive device polling.

If slot 16 turns out to be driven only when the decoder device is *opened* by a
higher layer, the untried picture-default calls in the peer's 12-call boot
sequence remain the most likely trigger, and are testable over CPU_COMM without
any firmware work.
