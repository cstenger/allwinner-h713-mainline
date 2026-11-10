# The CPU_COMM parameter convention, and the safe `Vp_Init` call

Desk work, no hardware writes. Settles the blocker recorded in
[cpu-comm-setsource-2026-09-04.md](cpu-comm-setsource-2026-09-04.md).

## The "ParaCount 1" worry was a misreading

The routines table looked like it declared a parameter count of 1 for
`Vp_Init` while stock sends 3. It declares nothing of the kind — the header
names the columns:

```
version 208, count 100
index  comp_id     cpu  next  name
  331  0x3356c54b    1     -1  THal_Vp_Wce_SetWindow_1_000
  485  0xeaf13de5    1     -1  THal_Vp_SetSource_1_000
  839  0x1c6ff747    1   1024  THal_Vp_Init_1_000
```

**`cpu` = target CPU (1 = the MIPS), `next` = hash-chain link.** The `1024` is a
chain index, not a size or a count. `Wce_SetWindow` — known to take three
parameters — carries the identical `1  -1`. **The table never declares parameter
counts, so nothing truncates what we send.**

## The layout, confirmed from three independent directions

**Our client** (`tools/display/cpu-comm-probe.c`) writes, at `PARAMS_OFFSET` 64:

```c
params[0] = arg_count;                 /* ParaCount */
for (i = 0; i < arg_count; i++)
        params[i + 1] = argv[i + 2];   /* Para[0], Para[1], ... */
```

**The firmware** reads that payload as:

| payload offset | meaning |
| --- | --- |
| `+0x00` | ParaCount |
| `+0x04` | Para[0] |
| `+0x08` | Para[1] |
| `+0x0c` | Para[2] |

**`THal_Vp_Wce_SetWindow` (`0x8b109d54`)** reads `4($a0)`, `8($a0)`, `0xc($a0)` —
three parameters, matching the documented "takes three ARM physical output
addresses".

**`THal_Vp_Init` (`0x8b109f04`)** reads **only `0xc($a0)`**, i.e. **Para[2]**:

```
lw   $a0, 0xc($s1)                  ; Para[2]
ext  $v0, $a0, 0, 0x1c              ; mask to 28 bits
or   $v0, $v0, 0xa0000000           ; -> MIPS kseg1, uncached
movz $v0, $zero, $a0                ; if Para[2] == 0 then dst = 0
addiu $a1, $a1, -0x3cfc             ; src = 0x8b48c304 (MIPS .bss)
ori  $a2, $zero, 0xd800             ; n = 55296
jal  0x8b1bcf34                     ; memcpy(dst, src, 55296)
...
sw   $v0, ($s0) ; sw $v0, 4($s0)    ; result = {1, 1}
```

So the peer's account is confirmed **from our own firmware**: `Para[2]` is a
destination address, 55296 bytes are copied to it, and the `movz` is exactly why
`Para[2] == 0` produces a NULL memcpy and corrupts memory.

## The safe invocation

```
cpu-comm-probe THal_Vp_Init_1_000 0 0 0x4E700000
```

sends ParaCount 3 with Para[2] = `0x4E700000`.

**Why that address is sound.** `/proc/cpu_comm/status` reports
`ShMemAddr 0x4e300000`, `ShMemSize 0x00500000`, so the region runs
`0x4e300000`–`0x4e7fffff`. `0x4E700000` is base + 4 MB, leaving 1 MiB to the end
— comfortably more than the 55296 bytes copied. It is the address the peer uses,
against the same base. Live cpu_comm structures observed in the log sit near the
start of the region (`AE300018` spinlock, `AE301F68` payload), 4 MB below the
target.

**One residual unknown, stated rather than hidden:** nothing has verified that
`0x4E700000` is unused by the cpu_comm driver's own allocator. The cheap
pre-check is to read that range first and confirm it is zero or stale, and to
re-read after the call to confirm 55296 bytes changed — which also proves the
call did what the disassembly says.

## Status

Convention settled; the call is well-founded and has not been fired.
