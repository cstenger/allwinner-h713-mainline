# CPU_COMM call table (board B, project 0x33)

Dumped 2026-08-04 from a live firmware with `h713_disp calltable 0`, after
`h713_disp mips-test 0x33`. 82 populated entries of 1224 slots, all named.

The table is only populated after **application readiness**, so it must follow a
run that proves it. `h713_disp mips-test 0x33` does; `h713_disp test` does not
(it passes `prove_ready=false` and patches `source_id` to 2, which makes the
firmware abandon init).

> **This table is also live under project `0x34` (2026-08-28).** A report that
> `0x34` accepts CALLs and never services them was tested directly and **does
> not reproduce**: under `0x34` the 60-second stability window is tick-for-tick
> identical to `0x33`, a no-op call (`2f02f7dd`) round-trips in 1 ms, and
> `THal_Vp_Init` returns `1`. The channel row differs per boot -- read it from
> `h713_disp commdev` rather than reusing a pid from these notes (a `0x34` boot
> gave `chan=0 pid=0x8b8f275c`, not the `0x8b8f32b0` recorded below). See
> "Project 0x34 RPC: the reported scheduler failure does not reproduce" in
> [../mips-display-recovery.md](../mips-display-recovery.md).

## RE-EXAMINED 2026-08-30: the "exhausted" verdict was wrong

This table was closed with "CPU_COMM cannot carry any of it -- 82 entries, all
`THal_Vp_*`, no resume/power/IOMMU/decoder-enable routine exists. Don't go
looking again." The search was accurate and the question was wrong. It looked for
a routine that would *start* something, and never asked whether the firmware
might be actively *suppressing* output.

The 82 entries reduce to 22 unique routines, and three of them are suppression
mechanisms that would each produce precisely our symptom -- everything configured
correctly, nothing on the panel:

| routine | id | handler | code? |
| --- | --- | --- | --- |
| `THal_Vp_EnableBlackScreen` | `a30d4c6b` | `8b10a0e8` | **real** |
| `THal_Vp_DisableBlackScreen` | `b66041d8` | `8b10a110` | **real** |
| `THal_Vp_EnableVideoFreeze` | `2fdcdc6f` | `8b10a138` | **real** |
| `THal_Vp_DisableVideoFreeze` | `3ab1d1dc` | `8b10a160` | **real** |
| `THal_Vp_EnableScreenCover` | `0152f134` | `8b10a188` | **real** |
| `THal_Vp_DisableScreenCover` | `143ffc87` | `8b10a1ec` | **real** |
| `THal_Vp_Wce_SetWindow` | `3356c54b` | `8b109d54` | **real** |
| `THal_Vp_Wce_GetWindow` | `fd483f67` | `8b109dc0` | **real** |
| `THal_Vp_Wce_GetActiveWindow` | `7bbd5772` | `8b109e2c` | **real** |
| `THal_Vp_GetSignalInfo` | `24b17fb7` | `8b109b40` | stub |

"Real" means the handler begins with an actual prologue (`addiu sp,sp,-24; ...`)
rather than `jr ra; nop`. Verified against
`local/mips-display/board-b-mips/display.bin` at file offset `VA - 0x8b100000`.

**The method is self-validating.** The previously established stubs
`THal_Vp_SetImageBufferAddr` (`0x8b10ada8`) and `GetImageBufferAddr`
(`0x8b10adb0`) both read `03e00008 00000000` at their computed offsets, which
independently reproduces that finding and confirms the base and the
little-endian encoding. `GetSignalInfo` reading as a stub is a second control:
the check discriminates, so "real" is not an artifact of pointing at the wrong
place.

**What to do with it, cheapest first.** `Wce_GetWindow` and `Wce_GetActiveWindow`
are **read-only** and take no state change to try. If the firmware's video window
is empty, off-screen or zero-sized, that is the black, and one query says so.
`DisableBlackScreen`, `DisableVideoFreeze` and `DisableScreenCover` are each a
single call that would clear a suppression if one is latched.

This does not overturn the other findings on this path -- `THal_Vp_Init` still
does not touch the video path, `SetSource` still changes nothing, and the
frame-handoff routines are still stubs. It overturns the *conclusion* drawn from
them, which was that the RPC surface has nothing to offer. It has ten live
routines nobody has called.

### The argument ABI, cracked (2026-08-30)

Two read-only calls, MIPS alive under `init 0x34`, live row from `commdev`:

```
h713_disp commcall fd483f67 chan=0 pid=8b8f275c 0 4d800000 4d810000 4d820000
h713_disp commcall 7bbd5772 chan=0 pid=8b8f275c 0 4d830000 4d840000 4d850000
```

```
GetWindow        4d800000: 00000000 00007800 00000000 00004380
GetActiveWindow  4d830000: 00000000 00005000 00000000 00002d00
```

**The ABI:**

- Parameters are `0` then up to three **ARM physical addresses**. The adapter
  reads them from the block at `+4`, `+8`, `+12`, so `param[0]` is a dummy.
- **Pass the ARM physical address unmodified.** The `0xA0000000` OR inside the
  adapter is its own business; translating to "MIPS physical" by subtracting
  `0x40000000` is wrong and was the error that made the first attempt fail.
- Output is a **four-word struct `{x, width, y, height}`** in **1/16-pixel fixed
  point**.
- The destination must be **untouched workspace** U-Boot cleared. Planting
  sentinels first creates dirty ARM cache lines and the read comes back stale --
  this build has no `dcache` command to flush them.

**The encoding is self-validating.** `GetActiveWindow` returns `0x5000`/`0x2d00`,
which divided by 16 is exactly **1280x720** -- the panel. The fixed-point reading
was not assumed; the panel-sized answer confirmed it, and the same layout then
reads `GetWindow` as a clean 1920x1080.

### The discrepancy

| call | value |
| --- | --- |
| `Wce_GetActiveWindow` | **1280 x 720** at (0,0) -- the panel |
| `Wce_GetWindow` | **1920 x 1080** at (0,0) |

The firmware's configured video window is **1080p on a 720p panel**. That
corroborates a long-standing observation from the register side: with the MIPS
parked, `0x05600020` reads `0x043F077F` = 1920x1088, and it took a DECD submit to
rewrite it to 1280x720.

**What this does and does not establish.** It establishes the ABI, the encoding,
and the discrepancy -- all measured. It does **not** establish that the 1080p
window causes the black. `GetActiveWindow` already reporting 1280x720 is
consistent with the effective window being correct and the 1920x1080 being a
configured default that is not in use. Do not skip that check.

`THal_Vp_Wce_SetWindow` (`3356c54b`) is the lever if it does matter, and it takes
the same argument shape.

### Settled 2026-08-30 by disassembly: the window is NOT the black

The check above ("do not skip that check") is now done, statically, with no
hardware time. Disassembled with `tools/mips/disasm.py`. **The 1080p window is a
linked-in default that nothing reads back into the display, and
`Wce_SetWindow` cannot change what is on the panel.**

The three routines are not peers. Two are pure accessors over firmware globals
and one is a live query:

| routine | what it actually does |
| --- | --- |
| `Wce_GetWindow` (`0x8b14cef0`) | copies **globals** `0x8b22f1b0`, `0x8b22f1a0`, `0x8b22f19c` to the caller. Touches no hardware. |
| `Wce_SetWindow` (`0x8b14cd18`) | stores the caller's structs **into those same globals**, then calls `0x8b1099c8` |
| `Wce_GetActiveWindow` (`0x8b14cf64`) | resolves an object via `0x8b1ac5f8` and makes a **virtual call** through its vtable `+0x24` -- a genuine live query |

The load-bearing fact: **`0x8b1099c8` is a stub** -- `jr $ra; addiu $v0, $zero, 1`.
It is the only thing `SetWindow` calls that is not a trace or a `memcpy`, so
`SetWindow` is a write to three globals that only `GetWindow` reads back.

And the globals have never been written. `0x8b22f1b0` in the **static image**
already reads `00000000 00007800 00000000 00004380`, byte-identical to what the
live board returned, so no call has ever modified it -- consistent with
`SetWindow` having exactly one caller path (ours, never used). The 1920x1080 is
also materialised as a literal inside `SetWindow`'s own prologue
(`addiu $v1, $zero, 0x7800` / `addiu $v0, $zero, 0x4380`) as the default it
substitutes for null arguments.

So `GetActiveWindow` returning 1280x720 was the live answer all along, and the
`GetWindow`/`GetActiveWindow` discrepancy is exactly the benign case the caveat
described: a configured default that is not in use. **Do not spend hardware time
calling `SetWindow`.** It would change what `GetWindow` returns and nothing else.

Two corroborations worth keeping, because both were free:

- The adapter disassembly **confirms the measured ABI independently**. Each
  adapter reads `4($a0)`, `8($a0)`, `0xc($a0)` -- so `param[0]` is genuinely
  unused -- and maps each with `ext rX, rX, 0, 0x1c` then `or 0xa0000000`, i.e.
  low 28 bits into the MIPS uncached window. That is why the **unmodified ARM
  physical address is correct** and subtracting `0x40000000` was wrong. `movz`
  preserves a null, so a null argument stays null rather than becoming
  `0xa0000000`.
- The trace strings inside `SetWindow` are `%s() ENTER`, `hal`,
  `./thal_display_wce.cpp`, `THal_Vp_Wce_SetWindow`. This is the **first
  confirmation of the call table's name-to-handler mapping from outside the
  table itself**.

One correction to the entry above: `0x8b12bb30` is a plain 16-byte copy, not a
converter. The 1/16 fixed-point reading rests solely on the 1280x720 match, which
is still good evidence, but nothing in the firmware independently labels the
units.

`Wce_GetWindow` also fills **two** structs and a scalar, not one. Only `p1` was
read on hardware; from the static image `p2` is also 1920x1080 and the scalar is
`2`. No re-run needed.

### The suppression routines are real -- and they are the surviving lead

The same deeper check was applied to the six suppression routines, because the
previous entry's "ten live routines" claim was measured at the **adapter** level
only, and `Wce_SetWindow` proves that test is too shallow: a real prologue can
still bottom out in a stub. These do not.

`EnableBlackScreen` (`0x8b1498a4`) and `DisableBlackScreen` (`0x8b149948`) are
trace / **`jal 0x8b106bec`** / trace, passing a 12-byte message whose first word
is an opcode -- `0xc` to enable, `0xd` to disable. `0x8b106bec` is a real
dispatcher:

```
lui  $v0, 0x8b25
lw   $v0, 0x3570($v0)   ; the singleton pointer at 0x8b253570
beqz $v0, +0x20         ; NOT registered -> jr ra with v0 = 0, silently no-op
lw   $v1, ($v0)         ; vtable
lw   $t9, 0xc($v1)      ; method
jr   $t9                ; tail-call, $a0 = object, $a1 = message
```

The method at vtable `+0xc` (`0x8b106a70`) posts the message to a **ThreadX
queue** created by the constructor (`0x8b15c320(obj+4, 0x390, 0xc)` -- 12-byte
messages), so these are genuine asynchronous commands to a live worker, not
state flags.

**The gate is closed only if nothing registered the singleton, and something
does.** `0x8b253570` is past the end of `display.bin` (image ends `0x8b232910`),
so it is BSS and starts at zero; it is written by a lazy singleton initialiser at
`0x8b106b7c` (allocate `0xc`, construct, store). That initialiser has exactly one
caller, `0x8b153598`, which is an **unconditional straight-line `jal`** near the
end of the early-system-init function `0x8b15340c` -- our **marker 55**. Since
CPU_COMM registration runs *after* `0x8b15340c` returns, and the call table is
demonstrably populated and serving calls, that init completes on our board.
Therefore the singleton exists and the dispatch is live.

So the cheapest experiment from the previous entry is now justified rather than
speculative: **`DisableBlackScreen` (`b66041d8`), `DisableVideoFreeze`
(`3ab1d1dc`), `DisableScreenCover` (`143ffc87`)**, each a bare call, no
arguments. If one of them is latched, clearing it is the black.

### There is a SECOND 1920x1080, and it is NOT eliminated

Do not let the section above contaminate this one. Two different things carry
`0x7800`/`0x4380`, and only one of them is dead:

| where | status |
| --- | --- |
| firmware globals `0x8b22f1b0` / `0x8b22f1a0` (`Wce_GetWindow`) | **inert** -- no path to any register, `SetWindow`'s worker is a stub |
| `tools/video/decd-client.c` VideoInfo `+0x70` and `+0x80` | **live input, handed to the firmware on every frame submit** |

The client declared `W 1280` / `H 720`, set the source dimensions and output
window from them, and then hardcoded `0x7800`/`0x4380` into the crop and display
frame -- under a comment reading `identity setDisplayFrame()`, which it was not.
`0x7800`/`0x4380` is also the firmware's own linked-in default window, which is
the likely origin of the copy.

That the two blocks share the encoding is not an assumption. The
`{x, width, y, height}` 1/16-pixel layout was recovered from the firmware today
and validated against the panel, and `0x5000`/`0x2d00` -- what `W << 4` and
`H << 4` produce -- is exactly what `Wce_GetActiveWindow` returns.

Changed to derive from `W`/`H`. **Untested on hardware**, and there is no stock
VideoInfo capture to confirm the vendor sends source-sized values here rather
than always sending 1080p and letting the pipeline scale. Capturing stock's
VideoInfo would settle it; until then this is an internal-consistency fix with a
plausible mechanism, not a demonstrated one.

A near-miss worth recording as method. The first cross-reference scan for writes
to `0x8b253570` reported **zero stores**, which would have supported a confident
and wrong "nothing ever registers it". It missed `sw $s1, 0x3570($s0)` at
`0x8b106bc0` because the scan only tracked `lui`-formed bases. Re-running it as a
base-register-independent opcode/immediate match over the raw image found the
store immediately. When a scan's answer is "none", check that the scan could have
seen one.

## Entry layout

| offset | contents |
| --- | --- |
| `+0x00` | `0x00010000`, version/flags |
| `+0x04` | pid -- `0x8b8f32b0` for every entry so far |
| `+0x08` | routine id, what `commcall` takes |
| `+0x0c` | ASCII name, NUL-terminated (`THal_Vp_Deinit_1_000`) |
| `+0x50` | handler VA |
| `+0x5c` | `0xffffffff` free sentinel |

Stride `0x60`. Ids are **not** derivable from the name: crc32, ~crc32, djb2,
djb2-xor, sdbm, FNV-1, FNV-1a and ELF hash all fail against
`THal_Vp_GetImageBufferAddr -> 0x2f02f7dd`. Read them from the table.

Invocation form, known good:

```
h713_disp commcall 2f02f7dd chan=0 pid=8b8f32b0
```

## Arguments: `THal_Vp_Init` is not a no-argument call

Most routines here were exercised with no parameters, which is correct for the
getters and the black-screen/screen-cover toggles. **`THal_Vp_Init` is not one
of them, and calling it bare is a malformed test.** Recovered 2026-08-28 by
disassembling the registered adapter and independently tracing board-B stock
`libhaldisplay.so`:

```
h713_disp commcall 1c6ff747 chan=<chan> pid=<pid> 0 1 <phys>
```

- ARM allocates a **`0xd800`-byte** buffer and passes its **physical** address.
- The three input words are `0`, `1`, and that address.
- The adapter runs a local state reset, then the VP initializer, then copies
  `0xd800` bytes of VP state to the supplied address through an uncached alias,
  returns one value, and installs an application callback.

A bare call supplies destination address `0`, so the bulk copy has nowhere to
go. Any earlier "standalone `THal_Vp_Init` does not initialise the display"
result taken from a zero-argument call is void, as is any register observation
made after it -- that transaction never resolved.

Under project `0x33` the corrected call completes the whole transport in ~1 ms,
returns `1`, fires every adapter boundary, and the destination holds an exact
copy of the firmware's VP state at `0x8b48c304` (`00040000 000c0008 00150010
...`). Use a destination inside the workspace U-Boot clears and flushes before
releasing MIPS (e.g. `0x4d800000`); a destination the ARM has dirty cache lines
over reads back as zeros and proves nothing about the copy.

Related correction: the firmware's virtual base is **`0x8b100000`**, not
`0x8b101000`. A disassembly helper carrying the 4 KiB-high base described
unrelated code as the registered adapter, which is how the zero-argument ABI
was believed in the first place.

## Display state -- the teardown set

| id | handler | routine |
| --- | --- | --- |
| `a30d4c6b` | `8b10a0e8` | `THal_Vp_EnableBlackScreen` |
| `b66041d8` | `8b10a110` | `THal_Vp_DisableBlackScreen` |
| `2fdcdc6f` | `8b10a138` | `THal_Vp_EnableVideoFreeze` |
| `3ab1d1dc` | `8b10a160` | `THal_Vp_DisableVideoFreeze` |
| `0152f134` | `8b10a188` | `THal_Vp_EnableScreenCover` |
| `143ffc87` | `8b10a1ec` | `THal_Vp_DisableScreenCover` |
| `1c6ff747` | `8b109f04` | `THal_Vp_Init` |
| **`eaaa24c9`** | `8b10a0e0` | **`THal_Vp_Deinit`** |

## Backlight

| id | handler | routine |
| --- | --- | --- |
| `4d80db0e` | `8b10a410` | `THal_Vp_SetBacklightWorkMode` |
| `b46ce545` | `8b10a444` | `Thal_Vp_SetBacklightPwmInfo` |
| `51ad877e` | `8b10a4c8` | `Thal_Vp_SetBacklightLevel` |

Note the lower-case `Thal_` on two of the three -- the vendor is inconsistent
and the name must match the table exactly if it is ever looked up by string.

## Source and image buffer

| id | handler | routine |
| --- | --- | --- |
| `eaf13de5` | `8b10a218` | `THal_Vp_SetSource` |
| `24efc7c9` | `8b10a244` | `THal_Vp_GetSource` |
| `2f02f7dd` | `8b10adb0` | `THal_Vp_GetImageBufferAddr` |
| `396f16bf` | `8b10ada8` | `THal_Vp_SetImageBufferAddr` |
| `24b17fb7` | `8b109b40` | `THal_Vp_GetSignalInfo` |

## Window / geometry

| id | handler | routine |
| --- | --- | --- |
| `3356c54b` | `8b109d54` | `THal_Vp_Wce_SetWindow` |
| `fd483f67` | `8b109dc0` | `THal_Vp_Wce_GetWindow` |
| `7bbd5772` | `8b109e2c` | `THal_Vp_Wce_GetActiveWindow` |
| `09ffc6eb` | `8b109d20` | `THal_Vp_Wce_SetMirrorMode` |
| `8f8a9581` | `8b109e88` | `THal_Vp_Wce_EnablePixel2PixelMode` |
| `ea7ffef5` | `8b109edc` | `THal_Vp_Wce_DisablePixel2PixelMode` |
| `cb6d765f` | `8b109cd0` | `THal_Vp_SeamlessEnable` |
| `c5429d4a` | `8b109cf8` | `THal_Vp_SeamlessDisable` |

## Picture quality

`7221d017` SetBrightness, `880be6ff` GetBrightness, `023c4033` SetContrast,
`6665fe81` GetContrast, `a84983c3` SetSaturation, `5263b52b` GetSaturation,
`5b2c62d5` SetHue, `5432b456` GetHue, `7335ebb5` SetSharpness, `563e60ab`
GetSharpness, `1a116843` SetGamma, `f6a798d3` SetDCI, `f9b94e50` GetDCI,
`c0da6a8e` SetSNR, `cfc4bc0d` GetSNR, `a4bb0747` SetTNR, `aba5d1c4` GetTNR,
`5c135587` SetBlackExtension, `5d3d7258` GetBlackExtension, `fc42fe0c`
SetWhiteBalance, `f00ca77d` SetColorManagement, `e661461f` GetColorManagement,
`83a878bf` SetPictureMode, `2d8338c3` GetPictureMode, `9817a1c1` SetVideoRange,
`623d9729` GetVideoRange, `c201c220` SetLowLatencyMode, `c32fe5ff`
GetLowLatencyMode, `434567b0` GetDisplayLatency.

## HDMI, ATV, VBI, callbacks

`9ce74c48` HDMI_SetPortMap, `cbf83247` HDMI_GetPortStatus, `6eb4c96a`
HDMI_SetHPDTimeInterval, `449effe8` HDMI_ReloadHdcp14Key, `50817813`
SetHDCP22Key, `fa085aaa` SetHDCP22Pkf, `ba3e5a70` SetHDMIHotPlugByPortCallback,
`93965d14` TurnOnARCAudioPath, `e9b4464d` SwitchARCTXPath.

`a16b7c24` AtvSetRegion, `a138c8fe` AtvChannelChange, `39d6eec4`
AtvChannelScanStart, `9558d223` AtvChannelScanEnd, `80e56656` AtvSetSignalStd,
`6e857547` AtvEnableSnowScreen, `71a4c888` AtvIsFastSyncLock, `24f44438`
CvbsSetPedestalMode.

`0fe1790c` StartVBI, `8a0d26cb` StopVBI, `9c91450e` ResetVBI, `096b60b1`
GetVBIData, `ec2ca0b4` GetVBIOffset, `8f5859c2` GetVBIAddr, `96046e19`
GetVBISize, `f3772724` EnableVBILine.

`671ceca6` RegisterSignalChangeCallback, `2692bdbe`
UnregisterSignalChangeCallback, `87a96488`
RegisterCallbackOfDisplayLatencyChange, `72341984`
UnregisterCallbackOfDisplayLatencyChange.

## What is NOT here

There is **no panel power routine** -- nothing for panel VCC, reset, or the
PF6/PH16 GPIOs. Those stay ARM-side, in `h713_disp_stock_panel_power`. So a
complete teardown is two halves: the firmware's own `Deinit`, and our GPIO
power-down using `PanelOffTiming0/1/2 = 20/250/75`.
