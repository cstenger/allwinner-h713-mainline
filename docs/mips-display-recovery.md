# MIPS display recovery plan

This plan recovers the H713 bench kernel first, then brings up the display
coprocessor one dependency at a time. It deliberately separates "the kernel
boots" from "the MIPS firmware starts" and from "ARM/MIPS RPC works." A build
that merely links is not evidence that the shared-memory protocol is safe.

The DDR3 `HY200_QZ713DF_A1` bench board is the only target in scope. Do not
flash these experiments to the untested LPDDR3 projector board.

## CPU_COMM: the routine map is recovered (2026-07-31)

The firmware's HAL routines are addressable, and the identities are confirmed
against this exact firmware rather than inferred.

### How a routine is named

The transport addresses a routine by a hashed id computed over
`<name>_<cpu_id>_<pid_low12>` -- `cpu_id` 1 for MIPS-side routines callable
from the ARM, 0 for MIPS-to-ARM callbacks, and `pid_low12` `000` for both
sides of the firmware's own registrations. The hash is an Allwinner CRC32
variant:

```python
def comp_id(name, seed=0x123456):
    crc = seed
    for b in name.encode():
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ (0xEDB88320 if crc & 1 else 0)
    return crc & 0xFFFFFFFF
```

### Why this is trusted

Three independent checks, in increasing strength:

1. The function reproduces 10/10 ids documented externally.
2. `display.bin` contains 85 `THal_Vp_` and `MipsHalCallback_` name strings,
   against the 82 registrations counted on hardware.
3. **Decisive:** the live call table stores each routine's *name* alongside its
   id, and the stored name hashes to the stored id. Verified on hardware for
   `THal_Vp_GetSNR_1_000`, `THal_Vp_SetHDCP22Key_1_000`,
   `THal_Vp_SetBrightness_1_000` and `THal_Vp_AtvSetRegion_1_000`. The third
   also reproduces the externally documented `0x7221d017`.

### Call-table entry layout

1224 entries of 0x60 bytes at `shared+0x75c8`, count at `+0x75c4`, version at
`+0x75c0`. Version is exactly twice the count -- each insertion bumps it twice.

```
+0x00   00010000     flags/type
+0x04   8b8f32b0     owner/vtable pointer, identical across entries
+0x08   comp_id
+0x0c   routine name, NUL-terminated ASCII, stored in place
+0x50   handler function pointer (MIPS VA, unique per entry)
+0x5c   next/free link, 0xffffffff when free
```

The handler pointer at `+0x50` means any routine can be disassembled in
`display.bin` before it is called.

### Reading it on hardware

```
h713_disp panel-test 0x33     # or mips-test -- the table only exists
h713_disp calltable           # after a launch
```

`calltable` is read-only: no writes, no messages. It does **not** consume the
one-launch-per-power-cycle budget, so run it at the prompt on the same boot
while the firmware is still up. Observed: `version=164 count=82`, all 13
embedded ids matched at entry offset `+0x08`.

### Entries that matter for the display problem

| entry | routine | why |
| --- | --- | --- |
| 989 | `THal_Vp_GetImageBufferAddr` | read-only; asks the firmware where the image buffer is |
| 703 | `THal_Vp_SetImageBufferAddr` | the OSD path in the vendor's own terms |
| 472 | `THal_Vp_DisableBlackScreen` | zero-parameter; would explain every observation if asserted at power-on |
| 107 | `THal_Vp_EnableBlackScreen` | its peer |
| 485 | `THal_Vp_SetSource` | source selection |
| 969 | `THal_Vp_GetSource` | read-only |
| 325 | `Thal_Vp_SetBacklightPwmInfo` | the unresolved PWM5 question |
| 894 | `Thal_Vp_SetBacklightLevel` | brightness |

### What a CALL still needs

Sending is **not** implemented and is not a small addition. A call goes through
routine lookup, session allocation, message allocation, FIFO enqueue, the
msgbox doorbell at `0x03003874`, an ACK wait and a return read. Those run on
master-side structures U-Boot does not initialise:

```
0x04CE8   va_offset
0x04D0C   linked lists (5 pairs)
0x04DB0   rec entries + wait/share-seq structures
0x240E8   component pool
0x2C068   messager pool      <- messages are allocated from here
0x2CCF0   SMM heap
```

What we do initialise -- magic words, `max_cpu`, CPU flags, 12 spinlocks, call
table sentinels -- is exactly enough for the MIPS to register and report ready,
which is why everything to date has worked. It is not enough to send.

Recovering the rest is the same job as `comm_InitSpinLock` and the call-table
sentinels, both of which were read out of `display.bin` successfully. Do not
guess at it: a malformed message to a live coprocessor can wedge it, and every
wedge costs a power cycle.

### Complete routine map

Ids for the ARM-to-MIPS direction (`_1_000`), or `_0_000` for the
`MipsHalCallback_` entries, computed from the 85 names in `display.bin`.

| routine | comp_id |
| --- | --- |
| `MipsHalCallback_DisplayLatencyChange` | `0xad9f0a86` |
| `MipsHalCallback_HdmiHotPlugByPortHandler` | `0x38d780e2` |
| `MipsHalCallback_SignalChange` | `0x3e7fbc46` |
| `THal_Vp_AtvChannelChange` | `0xa138c8fe` |
| `THal_Vp_AtvChannelScanEnd` | `0x9558d223` |
| `THal_Vp_AtvChannelScanStart` | `0x39d6eec4` |
| `THal_Vp_AtvEnableSnowScreen` | `0x6e857547` |
| `THal_Vp_AtvSetRegion` | `0xa16b7c24` |
| `THal_Vp_AtvSetSignalStd` | `0x80e56656` |
| `THal_Vp_CvbsSetPedestalMode` | `0x24f44438` |
| `THal_Vp_Deinit` | `0xeaaa24c9` |
| `THal_Vp_DisableBlackScreen` | `0xb66041d8` |
| `THal_Vp_DisableScreenCover` | `0x143ffc87` |
| `THal_Vp_DisableVideoFreeze` | `0x3ab1d1dc` |
| `THal_Vp_EnableBlackScreen` | `0xa30d4c6b` |
| `THal_Vp_EnableScreenCover` | `0x0152f134` |
| `THal_Vp_EnableVBILine` | `0xf3772724` |
| `THal_Vp_EnableVideoFreeze` | `0x2fdcdc6f` |
| `THal_Vp_GetBlackExtension` | `0x5d3d7258` |
| `THal_Vp_GetBrightness` | `0x880be6ff` |
| `THal_Vp_GetColorManagement` | `0xe661461f` |
| `THal_Vp_GetContrast` | `0x6665fe81` |
| `THal_Vp_GetDCI` | `0xf9b94e50` |
| `THal_Vp_GetDisplayLatency` | `0x434567b0` |
| `THal_Vp_GetHue` | `0x5432b456` |
| `THal_Vp_GetImageBufferAddr` | `0x2f02f7dd` |
| `THal_Vp_GetLowLatencyMode` | `0xc32fe5ff` |
| `THal_Vp_GetPictureMode` | `0x2d8338c3` |
| `THal_Vp_GetSNR` | `0xcfc4bc0d` |
| `THal_Vp_GetSaturation` | `0x5263b52b` |
| `THal_Vp_GetSharpness` | `0x563e60ab` |
| `THal_Vp_GetSignalInfo` | `0x24b17fb7` |
| `THal_Vp_GetSource` | `0x24efc7c9` |
| `THal_Vp_GetTNR` | `0xaba5d1c4` |
| `THal_Vp_GetVBIAddr` | `0x8f5859c2` |
| `THal_Vp_GetVBIData` | `0x096b60b1` |
| `THal_Vp_GetVBIOffset` | `0xec2ca0b4` |
| `THal_Vp_GetVBISize` | `0x96046e19` |
| `THal_Vp_GetVideoRange` | `0x623d9729` |
| `THal_Vp_HDMI_GetPortStatus` | `0xcbf83247` |
| `THal_Vp_HDMI_ReloadHdcp14Key` | `0x449effe8` |
| `THal_Vp_HDMI_SetHPDTimeInterval` | `0x6eb4c96a` |
| `THal_Vp_HDMI_SetPortMap` | `0x9ce74c48` |
| `THal_Vp_Init` | `0x1c6ff747` |
| `THal_Vp_RegisterCallbackOfDisplayLatencyChange` | `0x87a96488` |
| `THal_Vp_RegisterSignalChangeCallback` | `0x671ceca6` |
| `THal_Vp_ResetVBI` | `0x9c91450e` |
| `THal_Vp_SeamlessDisable` | `0xc5429d4a` |
| `THal_Vp_SeamlessEnable` | `0xcb6d765f` |
| `THal_Vp_SetBacklightWorkMode` | `0x4d80db0e` |
| `THal_Vp_SetBlackExtension` | `0x5c135587` |
| `THal_Vp_SetBrightness` | `0x7221d017` |
| `THal_Vp_SetColorManagement` | `0xf00ca77d` |
| `THal_Vp_SetContrast` | `0x023c4033` |
| `THal_Vp_SetDCI` | `0xf6a798d3` |
| `THal_Vp_SetGamma` | `0x1a116843` |
| `THal_Vp_SetHDCP22Key` | `0x50817813` |
| `THal_Vp_SetHDCP22Pkf` | `0xfa085aaa` |
| `THal_Vp_SetHDMIHotPlugByPortCallback` | `0xba3e5a70` |
| `THal_Vp_SetHue` | `0x5b2c62d5` |
| `THal_Vp_SetImageBufferAddr` | `0x396f16bf` |
| `THal_Vp_SetLowLatencyMode` | `0xc201c220` |
| `THal_Vp_SetPictureMode` | `0x83a878bf` |
| `THal_Vp_SetSNR` | `0xc0da6a8e` |
| `THal_Vp_SetSaturation` | `0xa84983c3` |
| `THal_Vp_SetSharpness` | `0x7335ebb5` |
| `THal_Vp_SetSource` | `0xeaf13de5` |
| `THal_Vp_SetTNR` | `0xa4bb0747` |
| `THal_Vp_SetVideoRange` | `0x9817a1c1` |
| `THal_Vp_SetWhiteBalance` | `0xfc42fe0c` |
| `THal_Vp_StartVBI` | `0x0fe1790c` |
| `THal_Vp_StopVBI` | `0x8a0d26cb` |
| `THal_Vp_SwitchARCTXPath` | `0xe9b4464d` |
| `THal_Vp_TurnOnARCAudioPath` | `0x93965d14` |
| `THal_Vp_UnregisterCallbackOfDisplayLatencyChange` | `0x72341984` |
| `THal_Vp_UnregisterSignalChangeCallback` | `0x2692bdbe` |
| `THal_Vp_Wce_DisablePixel2PixelMode` | `0xea7ffef5` |
| `THal_Vp_Wce_EnablePixel2PixelMode` | `0x8f8a9581` |
| `THal_Vp_Wce_GetActiveWindow` | `0x7bbd5772` |
| `THal_Vp_Wce_GetWindow` | `0xfd483f67` |
| `THal_Vp_Wce_SetMirrorMode` | `0x09ffc6eb` |
| `THal_Vp_Wce_SetWindow` | `0x3356c54b` |
| `Thal_Vp_AtvIsFastSyncLock` | `0x71a4c888` |
| `Thal_Vp_SetBacklightLevel` | `0x51ad877e` |
| `Thal_Vp_SetBacklightPwmInfo` | `0xb46ce545` |

## CPU_COMM: the master-side init, recovered (2026-07-31)

Sending a call needs shared-memory structures U-Boot does not build. This is
what the firmware's own master path builds, read out of the authenticated
`display.bin` and cross-checked against `cpu_comm.h` in the 32-bit Linux tree.
Every field that both sources describe agrees.

### The master init function

`0x8b11ace8` (raw `display.bin+0x1ace8`). It is the combined init: it calls
`getCurCPUID` at `0x8b1227b4` and `bnez` sends CPU 1 to `0x8b11b118`, so this
path is the ARM master's. It is idempotent -- it reads `shared+0x90` and skips
the whole body if the magic is already `0xdeadbeef`.

```
jal 0x8b124ba4                        (1)  first init, NOT YET DECODED
jal 0x8b124d38                        (2)  comm_InitSpinLock      -- U-Boot has
memset(shared+0x75c0, 0, 0x1cb08)     (3)  call table             -- U-Boot has
    count=0, version=0, 1224 sentinels
memset(shared+0x90, ...)              (4)
sw max_cpu -> 0x4cd8                  (5)                         -- U-Boot has
jal 0x8b119bb4  (cpu 0)               (6)  per-CPU comm object    NOT DECODED
jal 0x8b1197d4  (cpu 0, dir 0)        (7)  share_seq -- decoded below
jal 0x8b1197d4  (cpu 0, dir 1)        (8)
jal 0x8b119bb4  (cpu 1)               (9)
jal 0x8b1197d4  (cpu 1, dir 0)       (10)
jal 0x8b1197d4  (cpu 1, dir 1)       (11)
jal 0x8b1190c0                       (12)  final init, NOT DECODED
    five self-referencing list heads (13)
    256-entry record loop            (14)
magic1 = magic2 = 0xdeadbeef         (15)                         -- U-Boot has
```

### share_seq addressing

`0x8b1193d8(cpu, dir, idx)`, all three arguments validated `< 2`:

```
shared + 0x98 + 9760*cpu + 4880*dir + 2440*idx
```

Eight structs of 0x988 bytes spanning `shared+0x00098..0x04CD8`. The array ends
exactly where `max_cpu` begins, which is the check that the formula is right.

| cpu | dir | idx | offset |
| --- | --- | --- | --- |
| 0 | 0 | 0 | `0x00098` |
| 0 | 0 | 1 | `0x00a20` |
| 0 | 1 | 0 | `0x013a8` |
| 0 | 1 | 1 | `0x01d30` |
| 1 | 0 | 0 | `0x026b8` |
| 1 | 0 | 1 | `0x03040` |
| 1 | 1 | 0 | `0x039c8` |
| 1 | 1 | 1 | `0x04350` |

### share_seq contents

`0x8b1197d4(cpu, dir)` writes, relative to the struct base:

```
+0x00  cpu (byte)        +0x78  rd_idx     = 0
+0x01  dir (byte)        +0x7c  wr_idx     = 0
+0x02  0    (byte)       +0x80  peak_count = 0
+0x08  0    (byte)       +0x84  track      = 1
+0x10  20   (byte)       +0x88  capacity   = 21
+0x14  -1                +0x8c  item_size  = 4
+0x68  20   (byte)       +0x90  base_addr  = ARM-phys of (struct + 0xc0)
+0x69  0    (byte)       +0x94  0
+0x6c  -1                +0x98  FIFO name string
                         +0xb8  0
```

The block at `+0x78` is the driver's `comm_fifo` field for field: `rd_idx`,
`wr_idx`, `peak_count`, `track_stats`, `capacity`, `item_size`, `base_addr`.
Capacity 21 with one slot wasted for full-detection gives 20 usable, matching
the driver's documented sequence maximum of 19.

`base_addr` is `((VA + 0xc0) & 0x1fffffff) + 0x40000000` -- the firmware
converting its own KSEG address into an ARM-visible physical one. `struct+0xc0`
is the message slot array; the slot stride computes as `104 * i`, which is
`COMM_MSG_SIZE`.

### Directly replicable today

Five self-referencing empty circular lists, each `{self, 0, self, 0}`:

```
shared+0x4d10  0x4d28  0x4d58  0x4d70  0x4d88
```

A 256-entry record array from `shared+0x4db0` to `+0x75b0`, stride `0x28`
(`0x2800/0x28 = 256`), each with the same `{self, 0, self, 0}` head plus a call
to `0x8b1234c8(2, 0, entry-0x18)`. It lands exactly on `magic2` at `0x75b8`.

### The gap, stated precisely

U-Boot memsets the whole 5 MB then writes magic, flags, spinlocks and the call
table. **The entire `0x98..0x4CD8` share_seq region is left zero** -- capacity
0, `base_addr` 0, no FIFOs at all. That is enough for the MIPS to register its
82 routines and report ready, which is why every run to date has worked, and it
is why a call would find an empty transport.

### Why reading this block is safe to trust

`getCurCPUID` at `0x8b1227b4` is two instructions and always returns 1:

```
jr    $ra
addiu $v0, $zero, 1
```

So the `bnez $v0` at `0x8b11adac` is always taken and **the firmware never
executes the master-init block above**. It is compiled-in reference code for
the ARM side. That is exactly why replicating from it has worked twice already
-- `comm_InitSpinLock` and the call-table sentinels both came from here and
both were correct on hardware.

One caveat for replication: helpers that call `getCurCPUID` internally take the
CPU-1 path when read here, so trace each helper's `cpu == 0` branch rather than
copying its literal behaviour.

### The helpers, decoded

`0x8b150948` is the assertion logger, `"ASSERT FAILED, File:%s Line:%d
Routine:%s"`. Most branching in these functions is assertion paths, not
structural work, which makes them smaller than they look.

`0x8b118ff8(cpu, dir)` -- argument validator, both `< 2`, returns 0.

`0x8b1190c0` -- loop over `dir` in {0,1}, from `./comm_request.c`, guarding
`comm_WriteRegWord`. The `cpu == dir` case falls through to the tail, so on the
master only the cross direction does work.

`0x8b124ba4(type)` -- **not shared state.** Allocates a bookkeeping object into
the firmware's own BSS and bumps a counter at `0x8b27198c + type*4`. Called
with type 0. U-Boot does not need to replicate it; the ARM side allocates its
own equivalent in its own memory.

`0x8b1234c8(2, 0, record)` -- free-list insertion. Appends the record onto the
list header at `shared+0x4d80`, anchor `0x4d88`, incrementing a `u16` count at
`+0x02`:

```
[0x4d80+0x10] = record + 0x18      ; list tail
[record+0x20] = old tail           ; back link
[record+0x18] = 0x4d88             ; list anchor
```

So the 256 records at `0x4db0..0x75b0` are a **free pool**, pre-chained at init.

`0x8b11825c(fifo)` -- the FIFO slot allocator, called on `share_seq+0x78`:

```
if (rd_idx >= capacity) assert
if (wr_idx >= capacity) assert
if ((wr_idx + 1) % capacity == rd_idx) return NULL     ; full
return base_addr + wr_idx * item_size
```

confirming the `comm_fifo` layout from a second direction:

```
+0x00 rd_idx   +0x10 capacity    +0x18 base_addr
+0x04 wr_idx   +0x14 item_size   +0x40 debug_flags
+0x08 peak     +0x0c track
```

It does **not** advance `wr_idx`; commit is a separate operation. That matters
for getting a send right.

### The two FIFO names

The share_seq initialiser copies one of these into `struct+0x98` depending on
direction:

```
0x8b1edb1c  "FreeCall"
0x8b1edb28  "FreeReturn"
```

**`idx`, not `dir`, selects which.** `0x8b1197d4` runs its body twice per
`(cpu, dir)` call: `idx 0` names the FIFO "FreeCall" at `0x8b119b84`, then the
tail at `0x8b119bac` sets `idx` to 1 and repeats for "FreeReturn". That is what
the `idx` term in the addressing formula is for, and it means all eight
structures are live rather than four. The pair is the call queue and the return
queue, which is what a synchronous RPC needs and matches the protocol doc's
"session pool, FreeCall pool, returnPipeLine".

### The message slot loop, and the complete share_seq layout

The tail of `0x8b1197d4` runs 20 iterations over a message slot array:

```
fp = share_seq + 0x168
loop i = 0..19:
    sh   i,  4(fp)                     ; slot[+0x04] = i
    sw  -1,  slot + 0x0c               ; slot[+0x0c] = -1
    *ring_entry = (slot & 0x1fffffff) + 0x40000000    ; ARM-physical
    jal 0x8b118430                     ; FIFO push/commit
    fp += 0x68                         ; 104 bytes
until i == 0x14
```

`slot[+0x04] = i` and `slot[+0x0c] = -1` are the driver's `comm_msg.slot_index`
and `comm_msg.session_id`. The arithmetic closes the structure:
`0x168 + 20*104 = 0x988`, exactly the struct size.

```
+0x000  cpu (byte), dir (byte), 0
+0x008  0
+0x010  20            +0x014  -1
+0x068  20            +0x06c  -1
+0x078  comm_fifo   rd=0 wr=0 peak=0 track=1
                    capacity=21 item_size=4
                    base_addr = ARM-phys(share_seq + 0xc0)
+0x098  name: "FreeCall" (idx 0) or "FreeReturn" (idx 1)
+0x0b8  0
+0x0c0  FIFO ring, 21 x u32
+0x168  20 message slots x 104 bytes  -> ends exactly at 0x988
```

The 20 slots are pushed onto the FIFO at init, each as its ARM-physical
address, so the ring starts full of free slots -- 20 entries in a 21-capacity
ring, which is the "one wasted for full detection" the driver documents.
`0x8b11825c` allocates a ring position, `0x8b118430` commits it.

### Firmware-local, not needed by U-Boot

```
0x8b124ba4   allocates into firmware BSS, bumps a counter at 0x8b27198c
0x8b119bb4   per-CPU object at BSS 0x8b253a98 + 1168*cpu
0x8b1190c0   validation loop only
```

`0x8b119bb4` never loads the shared-memory base -- that is only reachable
through the global at `0x8b2543d4`, which it does not touch. Both it and
`0x8b124ba4` write only firmware BSS, so the ARM side has no shared-memory
obligation for either.

### The master init is fully decoded

Nothing unknown remains. What U-Boot must add, specified to the byte:

- 8 x `share_seq` at `0x98 + 9760*cpu + 4880*dir + 2440*idx`, layout above
  -- all eight, with the name chosen by `idx`
- 5 list heads at `0x4d10/0x4d28/0x4d58/0x4d70/0x4d88`, each `{self,0,self,0}`
- 256-record free pool `0x4db0..0x75b0` stride `0x28`, chained onto `0x4d80`

## CPU_COMM: the send path (2026-07-31)

Partial. Enough is known to say where a send goes; not enough to send one.

### SendComm2CPUEx

`0x8b11fd58` (raw `display.bin+0x1fd58`), 224-byte frame. Arguments match the
Linux driver's prototype: `a0` = message pointer, `a1` = target cpu, `a2` =
flags. `a1 == 0` means auto-detect via routine lookup, and that path's work
begins at `0x8b11ffb4`. `a0 == 0` is rejected.

The function contains no msgbox constants -- the doorbell is rung by a helper.
Note this firmware runs on the MIPS, so its own notification path is
MIPS-to-ARM; the ARM-to-MIPS doorbell is the other half and comes from the
Linux driver.

### The ARM-to-MIPS doorbell

A single write, no interrupt-enable pulse. The pulse workaround in that tree is
for the ARISC path, not MIPS.

```c
raw = ((msg_type & 0x3) << 16) | (intr_type & 0xFFFF);
writel(raw, 0x03003874);
```

`msg_type` 0=CALL, 1=RETURN, 2=CALL_ACK, 3=RETURN_ACK; `intr_type` is 2 in
stock. So a CALL is `0x00000002` written to `0x03003874`.

**Verified against our own firmware.** The MIPS TX function at `0x8b121870`
forms both addresses from the msgbox base:

```
addiu $s6, $s0, 0x3864     ; FIFO count, port 1
addiu $s5, $s0, 0x3874     ; MSG_DATA,   port 1
jal   0x8b180550($s6)      ; poll the count
```

With `$s0 = 0x03000000` those are `0x03003864` and `0x03003874`, matching the
driver's constants and the protocol doc.

### The message layout, settled by the receive side

`command_action` at `0x8b120bc0` is the consumer. It resolves a share_seq via
`0x8b1195b8(cpu, ...)`, reads a slot index from `share_seq+0x10` and rejects it
unless `< 20`, then forms the message base as `share_seq + 0x168 + 104*index`.
Subtracting `0x168` from its accesses gives the layout:

```
+0x00  lhu        src/dst pair
+0x02  lhu / sh   dst_cpu        compared against getCurCPUID
+0x04  lhu        slot_index
+0x06  lhu        flags
+0x08  lhu        cmd_type       <- parameter count
+0x0A  lhu / sh   flags2         bit 3 set on receipt
+0x0C  lw         session_id
+0x20  lw         payload[0]
+0x24  lw         payload[1]
+0x28  lw         comp_id        <- 40 decimal
```

This is the Linux driver's `CPUComm_CallEx` layout, field for field:
`dst_cpu` at `+2`, parameter count in `cmd_type` at `+8`, `comp_id` at `+40`,
parameters from `+44`. **The protocol doc's 168-byte form is wrong for this
path** -- its parameter count at `+64` and parameters at `+68` are not what the
firmware parses. The 104-byte form is also what fits the slots we build.

One correction to the driver's own header: it labels `+0x02` `component_id`,
but the firmware compares it with `getCurCPUID`, so it is `dst_cpu`. The
driver's code has this right; only its struct comment is misleading.

Note this also validates our init from the consumer's side: the message base is
`share_seq + 0x168 + 104*index` with a slot index bounded by 20, which is
exactly the array we build and the value 20 we write at `+0x10` as the
out-of-range/empty marker.

### Still needed for a send

- session allocation from the 256-record free pool
- message fill, at whichever layout the receive side proves
- enqueue via `0x8b11825c` (allocate ring position) and `0x8b118430` (commit)
- the doorbell above
- polling the return ring

## Board-B OSD handoff (2026-07-31)

This section supersedes the 2026-07-30 handoff below for anything it contradicts.
The panel now lights: PF6 is the correct board-B `panel_power_en`, and with it
asserted the firmware's internal colour source is plainly visible on the screen.
What does **not** appear is the OSD framebuffer.

### The one-line state

Everything from panel power through the LVDS PHY works. The MIPS firmware owns
the final output stage and composites its configured source — `source_id=1`,
VideoDecoder, an empty stream that is black by design — rather than our OSD
layer. That is the whole remaining gap.

### Proven on hardware this session

- **PF6 is panel power.** `PF_DAT=00000040`, and cutting it mid-run visibly
  changes the panel. PH16 (`panel_gpio_0`) latches correctly too; the old
  `gpio_set_value()` flag-loss defect is gone.
- **The firmware, not the ARM, drives the output stage.** With the coprocessor
  held in reset (`h713_disp panel-test <id> noboot`), `0x051c0000..0x0c` and
  `0x051c00b0..0xcc` all read zero, the scan counter at `0x05880000` is dead,
  and nothing at all reaches the panel — not even the internal colour source.
  With the firmware running, those registers are populated (including PHY
  geometry `0x051c00bc=05000030`, `0x051c00c0=02d00016`) and the raster runs.
  The doc's long-standing claim that the ARM path is not independent of the
  MIPS is now proven with registers rather than inferred.
- **AFBD is not the fault.** It is clocked (`0x02001dc0=80000005`, set by the
  vendor prologue, not by `h713_display_prepare()`), globally enabled
  (`0x05600000=80000020`), correctly sized/strided/addressed, and its enable at
  `0x05600144` latches and self-clears when the raster runs. Every AFBD-side
  explanation is closed.
- **The firmware does not tear our OSD down.** Dumping the fetch path before and
  after re-applying DE block 5 post-readiness yields byte-identical output.

### `panel_config.ini` is decoded and implemented

Stock does not write panel settings to MMIO directly. It parses its runtime DT
into a flat 35-entry `u32` array, overwrites the same array from
`/panel_config.ini`, then **patches the LogoRegData records in place** before the
generic applier runs them. The two name tables at stock `0x4a05ae30` (DT) and
`0x4a05a4fc` (INI) are index-for-index parallel, which is what makes the
override work.

The patch helper at `0x4a024894` is a bitfield insert:

```
patch(out, in_ptr, record, shift, fieldmask):
    require (fieldmask << shift) subset of record.mask   ; else log + skip
    if (*in_ptr < 0) return                              ; negative = unchanged
    record.value = (record.value & ~(fieldmask<<shift))
                 | ((*in_ptr & fieldmask) << shift)
```

All 32 call sites in the function at `0x4a0248fc` are transcribed into
`h713_disp_panel_patch()`. The mapping was validated by bit-width agreement:
1-bit flags land in 1-bit fields, the three-bit drive currents in `0x7` masks,
the six-bit DE current in `0x3f`, `MirrorMode` (0..3) in a two-bit AFBD field.

Two traps for whoever revisits this:

- The compare at `+0x24e12`/`+0x24e26` matches **either** `0x0524c010` **or**
  `0x0525c000` and patches whichever record it found. Transcribing only one
  leaves the DE composing 1440x741 under a mixer at 1360x760. All 32 sites were
  re-scanned for this class of error; that was the only one.
- `0x0525c000` takes `PanelVTotal`/`PanelHTotal` (`0x02f80550`), not the active
  size. The helper does a straight insert with no minus-one.

Expected bench output is `18 record field(s) patched, 8 guarded by record mask`.
Any other counts mean the record framing diverged and the run is void.

`PanelLvds0Pol`/`PanelLvds1Pol` are absent from both the DT and the INI, so
their two sites are no-ops on this board. `panel_dual_port` (DT 1 -> INI 0) and
`SpreadSpectrumEnable` (DT 1 -> INI 0) are the only two fields where the INI
actually overrides the DT.

The verified artifacts are extracted to `local/mips-display/board-b-mips/`:
`panel_config.ini` (2513 B, SHA-256 `7bffff88...`, carved from `Reserve0_a` at
eMMC `0xa78a3600`) and `runtime-toc1.dtb`.

### Closed, so nobody re-runs them

- The mixer/DE geometry mismatch is fixed and was **not** the blocker.
- The AFBD module clock is **not** gated; the vendor prologue sets it. Do not
  add `h713_display_prepare()` to the fastlogo replay — it is redundant there,
  and the prologue already writes `0x02001050` and `0x02001db0/db4/db8/dc0/dd8`.
- Stock's LVDS PHY tail (`0x051c00d4..0xe0` written as a barriered group at
  stock `+0x22cca`) is now replayed, and is a no-op: the neighbouring registers
  already hold those values.
- Enumerating every MMIO literal in stock's fastlogo function (`0x4a0228d4`) and
  diffing against our sequence leaves **no remaining difference** except the
  deliberately-skipped `0x02001020` PLL_PERIPH0 write.
- `source_id=2` (Image) was patched at the correct offset — `0x4be01e48` is
  genuinely the `'1'` character. The firmware getting *less* far therefore means
  the Image path needs a registered image source, not merely a config value.

### Next, in priority order

1. **CPU_COMM.** The transport works: MIPS READY, application-ready, 82 HAL
   registrations, a validated 1224-entry call table. This is the vendor's
   designed interface for telling the firmware what to display, and it is the
   only route that addresses the actual gap.
2. **Stock register parity.** Still decisive, and now cheap: the registers that
   matter are known (`0x051c0000..0xcc`, the mixer layer words, AFBD). One dump
   from a stopped stock boot would likely settle it outright.
3. Do not spend more runs on ARM-side register archaeology. It is exhausted.

### Diagnostics available

```
h713_disp panel-test <id>            # full launch, dumps, AFBD probe, OSD
h713_disp panel-test <id> noboot     # same, MIPS held in reset -- repeatable
                                     # without a power cycle, since no launch
```

`noboot` exists because the launch rule (one per physical power cycle) does not
apply when nothing is launched. It is the cheap way to iterate on ARM-side
sequence changes.

## Board-B LCD handoff (2026-07-30)

This section is the short path for the next investigator. It consolidates the
latest board-B reverse engineering and supersedes older board-A GPIO
assumptions preserved later in the chronological log.

### Immediate conclusion

The MIPS firmware is no longer the leading bring-up blocker. With the required
shared-memory spinlocks and call entries initialized, repeated cold starts
reached:

```
CPU_COMM magic=deadbeef/deadbeef ARM=00000005 MIPS=00000005
firmware readiness proven by MIPS READY
application readiness proven
```

The recovery code also publishes a valid 1280x720 ARGB8888 buffer, can latch
the panel's 1360x760 timing, and produces electrical activity on at least one
LVDS pair. The important missing stock input was found in the **ARM-side
board-B boot artifacts**:

1. board B's runtime TOC1 DT names **PF6**, not PH19, as
   `panel_power_en`;
2. board-B stock U-Boot loads `panel_config.ini` from `/oem` and falls back
   to `Reserve0`;
3. that file changes the parsed display configuration to single-port LVDS,
   inverted DCLK, VESA mapping, 8-bit color, and PWM channel 5.

The prior PH19 power tests mixed board-B MIPS artifacts with a board-A TOC1
DT. They changed the PH19 software latch correctly but said nothing about
board-B panel power. Likewise, PB4/PWM2 is only the pre-override runtime-DT
choice and is not authoritative once `panel_config.ini` is loaded.

### Artifact identities and extraction coordinates

Keep the two boards and the two U-Boot DTs distinct:

- complete board-B eMMC image:
  `local/h713-lab/captures/board-b/board-b-mmcblk0-20260705T075628Z.img`,
  7,818,182,656 bytes;
- board-B stock U-Boot:
  `local/mips-display/board-b-stock/u-boot-stock.bin`, 638,976 bytes,
  SHA-256
  `22c9afa98503d4ce0b2b929cf8109af034d841560fbd11baf4ad851197134440`;
- board-B `display.bin`: 1,255,696 bytes, SHA-256
  `4380f1b3ed7b62aa50582e7cb16a87bdface1b4300578fe3631a416354da30ce`;
- board-B `database.TSE`: 282,464 bytes, SHA-256
  `27e2abad947f319b7b5da229f1b078a6a986592718f98dcd745215338fcd4f81`.

The relevant TOC1 begins at eMMC byte `0x00c00000`. Its runtime-DT item begins
at TOC1 `+0x11b400`, therefore eMMC `0x00d1b400`, and declares a `0x12000`
window. The DTB itself is 69,380 bytes, SHA-256
`3902567a079720921e226c9176877f49916c6bdabfb6d82885e65d9f0a7d58b0`.
(An earlier revision of this document recorded `06e5279c...` here; that hash is
wrong. All three board-B eMMC captures yield the value above at that exact
offset and size, and both byte-level facts quoted below — `panel_power_en` at
DTB `+0x9f64` and `panel_gpio_0` at `+0x9f9c` — match it.)
This is the DT parsed by the stock fastlogo path and is the authority for its
named GPIO descriptors.

Board-B stock U-Boot also embeds a **different control DT** at raw
`+0x964e8`, size `0x474b`. Its seven-cell `panel_power_en` value at raw
`+0x990d4` is `<0x0d 5 6 1 2 3 1>`, again identifying PF6, but it describes
additional panel GPIOs. Do not substitute that embedded control DT for the
runtime TOC1 DT when reconstructing the fastlogo object's descriptors.

### Exact board-B panel controls

The runtime-DT cells are:

```
panel_power_en = <0x2c 0x05 0x06 0x20>;  /* PF6, active high, pull-down */
panel_bl_en    = <0x2c 0x01 0x05 0x00>;  /* PB5 */
panel_gpio_0   = <0x2c 0x07 0x10 0x20>;  /* PH16, active high, pull-down */
```

The `panel_power_en` value is at DTB `+0x9f64`, bytes:

```
00 00 00 2c 00 00 00 05 00 00 00 06 00 00 00 20
```

It is at TOC1 `+0x125364` and eMMC `0x00d25364`. The `panel_gpio_0` value is at
DTB `+0x9f9c`, bytes:

```
00 00 00 2c 00 00 00 07 00 00 00 10 00 00 00 20
```

It is at eMMC `0x00d2539c`. The compiled board-B property string
`panel_power_en\0` begins in stock U-Boot at raw `+0x6200b`, bytes
`70 61 6e 65 6c 5f 70 6f 77 65 72 5f 65 6e 00`; its little-endian pointer is
at raw `+0x23be0`, bytes `0b 20 06 4a`. `panel_gpio_%d` begins at raw
`+0x62038`, with its pointer at `+0x23c60`, bytes `38 20 06 4a`.

H713 uses the new 0x30-byte PIO bank stride. The useful coordinates are:

```
PF6 linear GPIO       166
PF_CFG0               0x020000f0  (PF6 mux is bits 27:24)
PF_DATA               0x02000100  (PF6 data is bit 6)
PH_CFG2               0x02000158  (PH16 mux is bits 3:0)
PH_DATA               0x02000160  (PH16 data is bit 16)
```

The decoded board-B stock power method begins at U-Boot raw `+0x224e4`,
bytes `2d e9 f0 45`. On power-on it applies `panel_power_en`, walks the
present `panel_gpio_N` descriptors low with a 2 ms delay, then applies their
configured active values with a 5 ms delay. The first loop starts at
`+0x22528`, bytes `a0 46 4f f0 00 0a 58 f8 04 1b`; the second begins at
`+0x22554`, bytes `54 f8 04 1b a9 b1 38 22`. Only `panel_gpio_0` is present
in the runtime DT. The reconstructed board-B operation is therefore:

```
wait 550 ms
PF6 = high
PH16 = low
wait 2 ms
PH16 = high
wait 5 ms
wait the remaining 20 ms stock phase
```

The current recovery code implements that sequence. Its earlier PH19 version
did not.

The runtime DT also names `lcd_standby=PH15` and
`spi_cs/spi_scl/spi_sda=PH10/PH11/PH12`. Those names have no compiled
property-name occurrence in board-B stock U-Boot. They are possible inputs to
another component, but there is currently **no evidence** that the fastlogo
path bit-bangs those pins. Treat panel serial initialization as a hypothesis
to trace, not a step to copy blindly.

### The other missed input: `panel_config.ini`

Board-B stock U-Boot contains the following strings:

```
+0x61e7a  load file %s fail, try load panel_config.ini!
+0x61ea9  panel_config.ini
+0x61ec7  /oem
+0x61ef6  Reserve0
+0x61f47  load file panel_config.ini fail!
+0x61f98  PanelSetting
+0x62084  PWMSetting
+0x6208f  pwm_channel
```

The loader/distributor is around raw `+0x236ec..+0x238d4`. It tries `/oem`
first and then the `Reserve0` partition. In the board-B dump `Reserve0_a`
starts at eMMC byte `0xa7880000` and contains `/panel_config.ini`, 2,513
bytes, SHA-256
`7bffff88a8319c3cdd1a2cdba0fc26df9fdac16c01aedaea7cc20353bc618cc3`.
The file begins:

```
5b 50 61 6e 65 6c 53 65 74 74 69 6e 67 5d 0a 50
72 6f 6a 65 63 74 49 44 20 3d 20 35 32 0a
```

or `[PanelSetting]\nProjectID = 52\n`. Its relevant values are:

```
ProjectID              = 52
PanelWidth             = 1280
PanelHeight            = 720
PanelDualPort          = 0       # single port
OddEven                = 0
Mapping                = 0       # normal/VESA
ColorDepth             = 8
MirrorMode             = 0
PanelInvDCLK           = 1
PanelInvDE             = 0
PanelInvHSync          = 0
PanelInvVSync          = 0
PanelNoiseDith         = 1
PanelDCKLCurrent       = 7
PanelDECurrent         = 47
PanelODDDataCurrent    = 7
PanelEvenDataCurrent   = 7
PanelOnTiming0/1/2     = 20/550/75 ms
PanelMax/typ/MinHTotal = 1360/1360/1360
PanelMax/typ/MinVTotal = 760/760/760
PanelDCLK              = 62000000
PanelHsync/PanelVsync  = 20/2
PanelHBP/PanelVBP      = 40/20
PanelTimingWorkMode    = 2
pwm_channel            = 5
pwm_polarity           = 1       # low-level active
pwm_freq               = 40000
pwm_vs_lock            = 1
pwm_min/max/default    = 1/100/50
```

`ProjectID=52` decimal is `0x34`, while the MIPS artifact selection used in the
bench command is `0x33`. Record the discrepancy; do not assume these fields
share a namespace or silently change the proven `h713_disp ... 0x33` path.

The INI does not override GPIO names, so it does not weaken the PF6 finding.
It does override the runtime DT's `panel_pwm_ch=2`; consequently PB4/PWM2
tests are rejected as board-B brightness evidence. The runtime DT's PWM5 node
has no pinctrl properties, so the physical PWM5 route still needs static
tracing or a stock-register comparison.

### What the bench has and has not proven

Proven:

- the exact board-B `display.bin` is loaded as a raw MIPS32 little-endian image
  at ARM `0x4b100000`;
- its direct file-offset/load-address identity holds: for example raw
  `+0x88124` appeared at ARM `0x4b188124` in the earlier guarded patch test;
- firmware execution, MIPS READY, the 82-entry HAL registration set, and
  application READY all complete once 12 CPU_COMM spinlocks and 1,224 call
  entries are initialized;
- the MIPS can remain stable and does not need another speculative readiness
  patch;
- mixer and DE retain `0x02e4059f`, a size-minus-one 1440x741 internal
  processing size;
- the vendor timing table and `panel_config.ini` agree on 1360x760 total,
  1280x720 active. The recovery latch reads back
  `00000004 02f80550 02d00500 00140028 80000014 80010003`;
- the moving ARGB8888 test buffer at `0x6c100000`, 1280x720 with stride
  `0x1400`, is written, read back, and cache-cleaned;
- an internal TCON color source accepts and reads back its requested colors;
- at least one connector-side LVDS pair is driven. The 15.509-second Saleae
  analog capture has conductor means 1.1831 V and 1.2765 V, common-mode
  1.2298 V, and correlation -0.7864. Its stable per-second distribution is
  consistent with a clock pair but does not prove that identification.

Not proven:

- PF6 has not yet been tested on hardware by the corrected recovery build;
- the analyzer's former channel 2 was not on a switched 3.3 V rail. It rose
  slowly from about 0.64 V to 1.06 V and is an unidentified connector signal;
- the panel was powered during any earlier internal-color or framebuffer test;
- the current lane count, single/dual-port mode, mapping, DCLK polarity, color
  depth, and drive-current registers match the post-INI stock state;
- PWM5 reaches the backlight hardware;
- PH10/PH11/PH12 perform any required panel transaction;
- the suspected pair is definitely the LVDS clock rather than data.

Do not infer a downstream-LVDS fault from the earlier no-image runs: they used
the wrong board's panel-power GPIO. More framebuffer patterns cannot resolve
power, lane mode, mapping, or panel initialization.

The `Output_Resolution` reverse engineering is valid but not an active route.
`OUTPUT_TIMING_PROJECTOR` selector 3 maps to the 1360x760/1280x720 row and
selector 4 maps to 2200x1125/1920x1080. However, the one-shot entry marker
proved `_LoadTFDPanelTiming` is not called on this startup path. The selector
patch and marker have been removed. Do not reintroduce the raw
`display.bin+0x88124` patch; `panel-test` instead restores the known 720p TCON
values after MIPS startup.

### Current recovery build

`external/u-boot/arch/arm/mach-sunxi/h713_mips.c` now:

- drives PF6 through `0x02000100`;
- pulses PH16 through `0x02000160`;
- reports both mux and latch states;
- leaves shared fan/backlight enable PB5 asserted;
- no longer calls PB4 an authoritative brightness input or wastes six seconds
  toggling it;
- still does **not** implement the INI's single-port/mapping/DCLK/PWM5
  overrides because their final hardware writes have not been identified.

The last validated DDR3 artifact is:

```
build/out/u-boot-sunxi-with-spl-ddr3.bin
size    874009 bytes
sha256  4153a1983377eaa2e2edac85982df5aee19eae887b5405506ce2257cf30e88c1
```

It builds successfully with nine pre-existing 32-bit MMIO pointer-cast
warnings in the LogoRegData interpreter. `git diff --check` passes in both the
root repository and U-Boot submodule. The changes are intentionally uncommitted
for review.

### Resume plan, in priority order

The board was powered off at handoff. Preserve the rule: **one MIPS launch per
physical power cycle**. Plain GPIO/register reads before a MIPS launch do not
consume that run.

#### 1. Prove PF6 and the panel rail before reflashing

Cold boot the currently installed U-Boot to its prompt. Put analyzer channel 2
on the actual panel 3.3 V/VDD pin, retain channels 0/1 on the suspected LVDS
pair, and run:

```
md.l 0x020000f0 1
md.l 0x02000100 1
gpio set 166
md.l 0x020000f0 1
md.l 0x02000100 1
sleep 10
```

Expected software result: PF6's mux nibble becomes 1 and PF_DATA bit 6
(`0x40`) is set. Expected hardware result: the panel VDD rail makes a clear
step to its nominal voltage.

- If the registers change and the measured rail rises, the missing-power
  diagnosis is confirmed. Proceed to the corrected build.
- If the registers change but connector VDD does not, verify the connector
  pin, then locate the PF6-controlled load-switch input and output. The stock
  DT proves the logical control identity, not the connector pinout or health
  of the upstream regulator.
- If the PF6 registers do not change, resolve the U-Boot GPIO command/mux
  issue before involving MIPS.

#### 2. Run the corrected integrated test once

Flash the artifact identified above, physically power-cycle, start a UART log
and Saleae capture, and run exactly:

```
h713_disp panel-test 0x33
```

Record separately:

- the PF6/PF_DATA and PH16/PH_DATA printouts;
- whether panel VDD rises at the initial stock-power phase;
- whether the panel changes opacity at PF6 off/on or PH16 low/high;
- whether the suspected LVDS pair changes when the 720p timing is latched;
- whether internal white/colors appear after panel power and 720p timing;
- whether the moving framebuffer appears;
- MIPS READY and application READY;
- the final `0x05880020/+0x24` timing readback.

If this produces an image, reduce the diagnostic sequence into the permanent
boot order and then address Linux ownership. If it only changes panel opacity
or brightness, power control is solved and the remaining fault is signaling
configuration or initialization.

#### 3. If VDD is correct but no internal color appears

The best next discriminator is **stock-register parity**, not another
framebuffer:

1. If a reversible stock boot is available, stop it after the factory logo and
   capture these blocks with `md.l`:

   ```
   md.l 0x05800000 0x0c    # LVDS lane/map block
   md.l 0x05880000 0x10    # LVDS/TCON block
   md.l 0x058c0000 0x0c    # display PLL
   md.l 0x051c0000 0x08    # LVDS PHY
   md.l 0x020000f0 0x08    # PF mux/data neighborhood
   md.l 0x02000150 0x08    # PH mux/data neighborhood
   ```

   Compare them word-for-word with `h713_disp dump` after the corrected run.
   This directly exposes single/dual-port, lane-map, clock-polarity, and PHY
   differences without guessing register semantics.

2. In static analysis, continue from board-B stock U-Boot
   `+0x236ec..+0x238d4`. Recover the destination structure offsets for
   `PanelDualPort`, `Mapping`, `ColorDepth`, `PanelInvDCLK`, the four drive
   currents, and `pwm_channel`. Follow consumers of those fields to the final
   MMIO writes. Search literal/xref neighborhoods for the already observed
   blocks `0x05800000`, `0x05880000`, `0x058c0000`, and `0x051c0000`.

3. Replay only the confirmed differences in a new diagnostic, one category at
   a time:

   - single-port/lane count and odd/even selection;
   - VESA mapping and 8-bit depth;
   - inverted DCLK;
   - drive-current values;
   - PWM5.

   Keep the internal TCON white/color source active during these tests. It
   removes AFBD, framebuffer layout, cache coherency, and DE composition from
   the result.

#### 4. Resolve PWM5 independently

Do not return to PB4/PWM2. The post-INI setting is PWM5, polarity 1, 40 kHz,
default 50%, range 1..100. Because the runtime DT's PWM5 node lacks a pinctrl
route:

- follow the stock PWM channel field into its controller/pinmux calls;
- search the embedded control DT and stock pinctrl tables for a PWM5 function;
- compare PIO mux registers before and after a stock logo boot;
- only then attach the analyzer to the candidate brightness signal.

PB5 remains useful only as the shared fan/backlight-enable control. Fan motion
or tach activity does not prove the panel 3.3 V rail or PWM5 duty.

#### 5. Investigate panel-side serial initialization only with evidence

If power, 720p timing, LVDS clock, lane/mapping parity, and backlight are all
correct, trace the runtime-DT `lcd_standby` and `spi_*` pins:

- search `display.bin`, `ProjectID_0x0033.TSE`, database modules, and other
  stock binaries for the pin numbers or a software-SPI transaction;
- inspect xrefs to GPIO descriptor arrays rather than string occurrence alone;
- if stock firmware can boot, capture PH10/PH11/PH12 and PH15 during the logo
  transition and compare against the recovery run.

No compiled fastlogo property-name reference has yet tied these pins to stock
U-Boot, so this route comes after the confirmed INI and LVDS-mode work.

#### 6. Preserve established dead ends and safety boundaries

- Do not use PH19 as board-B panel power.
- Do not use PB4/PWM2 as final board-B brightness evidence.
- Do not source panel geometry from `LogoRegData.bin`; it is a register replay
  file. The projector database row and `panel_config.ini` independently give
  1360x760/1280x720.
- Do not treat mixer/DE `0x02e4059f` as TCON total geometry; 1440x741 remains
  an unexplained internal processing size.
- Do not patch `_LoadTFDPanelTiming`; the entry marker proved it dead here.
- Do not launch MIPS twice without a physical power cycle.
- Do not use the old Linux MIPS observer/loader path or touch MIPS control
  registers from Linux during bring-up.
- Do not touch `external/sunxi-tools` or the FEL/flash recovery documents in
  this display thread.

## Current status (2026-07-29)

The reviewed end state deliberately moves MIPS boot ownership out of Linux:

- the active Linux 6.18.38 series contains 31 patches; Gemini's 910-line
  `sunxi-mipsloader` patch and the later read-only MMIO observer are removed;
- the kernel, modules, both board DTBs, and bench FIT build from a fresh
  extraction;
- NSI, CPU_COMM, TVTOP, DECD, and GE2D remain disabled;
- the compiled bench DTB contains one MIPS object: a no-map reserved-memory
  pool at `0x4b100000+0x0e41000`. It has no MIPS platform device, boot-vector
  property, clock/reset handle, or control-register address;
- the linked kernel has no loader/observer symbols and Linux creates no
  `/dev/mips*` device;
- no display firmware is embedded in the kernel or root filesystem.

The current RAM-only kernel artifact is `build/out/h713-kernel.fit`
(7,701,060 bytes), SHA-256:

```
2791e08e4bc18f5b032829bb98ad869711e22ccbd9b1870b38cd0695cd66b067
```

Its embedded kernel and bench DTB hashes are, respectively:

```
3a5c27c37eabaef514a4a4b43e87d87cd4bca40ee5320aa60f7a74c35fe028e1
23d37712e9822d44152dcb93ef0923f6b382288bdfea85a3cae6ae7397df3ac7
```

U-Boot verified both hashes before the 2026-07-27 bench boot. Linux reached
the Debian root shell and `systemctl is-system-running` reported `running`.
The UART log showed four CPUs, the ext4 root, eMMC, RTC, Panfrost, Cedrus,
AIC8800, serial getty, hotspot, Bluetooth attach, and SSH coming up. The only
MIPS lines in `dmesg` were reserved-memory initialization; `/dev/mips*` did not
exist. This passed the point where the observer-equipped kernel had stopped
responding.

The observer-equipped FIT, SHA-256
`3ee4e49beef8671e3727df319b7f2f1e7c79b0f04b4d16fd417664f2f7a361ce`,
is rejected evidence and must not be reused. Although its driver performed only
a register read, the board stopped responding after Linux clock takeover. The
safety boundary is therefore stronger than "read-only": Linux does not map or
touch the MIPS control registers during this phase.

The factory cold-start sequence is substantially narrower. Reverse engineering
the stock U-Boot
`0a44d54b3683453765fdbda93744eb5510b8d68ce829d1b0481c2cf2844e28f0`
shows that it loads `display.bin` at ARM physical `0x4b100000` and writes that
physical address, not its MIPS KSEG0 alias, to boot-address register
`0x03061030`. It then drives the MIPS clock/reset registers as follows, with
12 ms between reset stages and 300 ms after release:

```
0x02001600 <- 0x80000002
0x0200160c <- 0x00000000
0x0200160c <- 0x00010000
0x0200160c <- 0x00030000
0x0200160c <- 0x00030001
0x03061030 <- 0x4b100000
0x0200160c <- 0x00070001
```

UART-controlled tests established the hardware boundary:

- Writing stock register `0x051c0010 <- 0x01800045` by itself stalled both
  ARM UART and USB ACM. This register belongs to the factory fast-logo/LVDS
  sequence, not the standalone MIPS reset primitive. A power cycle recovered
  the board, and the known-good kernel subsequently booted cleanly.
- Replaying only the MIPS clock/reset sequence remained stable and changed CPU
  status register `0x0306101c` from zero to one. Status one therefore proves
  reset release, not firmware readiness.

Static analysis supplied a separate execution witness. The reset path enters
at the firmware's MIPS BFC vector, executes `eret` to `0x8b1b0868`, and then
clears BSS from MIPS address `0x8b232c00` through `0x8bac7c28`. The firmware's
observed address translation maps these to ARM physical
`0x4b232c00..0x4bac7c28`. Witness address `0x4b600000` is inside that loop but
is the first word beyond the five-megabyte window cleared by U-Boot. The
command writes `0x4d495053` there, flushes that ARM cache line, releases the
MIPS, then invalidates the line before reading it. Only a firmware-owned store
is expected to turn the seed into zero.

The ownership boundary is now explicit: U-Boot proper loads, verifies, and
releases `display.bin` before Linux. SPL remains responsible only for DRAM and
normal boot prerequisites unless a specific clock/interconnect dependency is
later proven to require earlier setup. Linux must not reload or restart the
coprocessor; its eventual role is reserved-memory protection and post-boot IPC
or display management.

A manual U-Boot command implements this boundary without changing autoboot.
`h713_mips load` reads the exact 1,256,216-byte image from a filesystem, clears
the five-megabyte firmware window, and accepts only SHA-256
`16c74a28187f342de657828fab65145b140ac9411c40cccc02eed25047472ee9`.
Separate `verify`, `start`, `stop`, and `status` operations keep each bench
transition observable. Before reset release, `start` applies only the
bench-proven display PLL/module-clock, TVTOP-routing, and mixer prerequisites.
It deliberately excludes LVDS, PH pinmux, TVCAP, HDMI, and INCAP. `start`
requires both CPU status one and the independent BSS-clear witness; it returns
the core to reset if either check fails.

The first installed and hardware-tested DDR3 bench artifact containing the
execution-witness command was 844,537 bytes, SHA-256:

```
493c45149a84e528f04b4b5861853cbbff43543bbd7048602966aca7d920d1ce
```

The current installed DDR3 build incorporates the proven display prerequisites
and deletes the unsafe experimental `factory-start` path. It also disables the
MIPS clock in `stop` after asserting reset. It is
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (844,537 bytes), SHA-256:

```
956a03a61693add8c281f6f2678609e8d427a972b0797a3bd09b22fd8428fef2
```

The command is compiled into U-Boot proper and is absent from SPL as designed.
It is enabled only in the DDR3 bench defconfig, not the projector defconfig,
and it is manual: the normal autoboot path remains unchanged.

Bench execution validated the negative and transition paths:

- uninitialized firmware was rejected and left reset/status zero;
- the known image transferred by YMODEM produced the pinned SHA-256;
- deliberately dirtied bytes beyond the image were cleared before start;
- `start` reproduced the stock staged reset transition and reported status one
  with physical boot address `0x4b100000`;
- on three fresh firmware loads, the BSS witness changed from `0x4d495053` to
  zero while status remained one, independently proving that the MIPS fetched
  and executed its firmware startup code;
- the running firmware modifies bytes in its loaded image. A second `start`
  without restoring a pristine image produced SHA-256
  `6a7a86d23be26a712c6af9671acfd06ed4bcdb1d7216fa89949f6fca3d2bccde`;
  the pinned-image check rejected it and kept the MIPS in reset. Every new run
  must therefore use `load`/`boot` or otherwise restore the pristine image;
- UART and USB ACM remained responsive during all three runs, and `stop`
  returned reset, status, and boot address to zero.

The first post-test Linux handoff stopped producing UART output during driver
bring-up. At that point `stop` had asserted reset but left MIPS clock register
`0x02001600` at `0x80000002`, unlike its cold-boot value of zero. A follow-up
build disabled that clock after asserting reset and was hardware-verified to
return clock, reset, status, and boot address to zero. Linux nevertheless
stopped at the same point after the start/stop cycle. The lingering clock was
therefore not the sole cause. Abruptly resetting active firmware may leave an
outstanding transaction or another display/interconnect register in a state
that reset does not unwind.

Do not treat `stop` after successful execution as a clean Linux handoff. The
intended ownership-model test instead loaded and started the MIPS in U-Boot,
left it running, and booted the protected-memory Linux image. A power cycle
remains the known recovery for a failed post-execution handoff.

The initial live-MIPS handoff reached Linux but stopped deterministically in
the Panfrost probe. Panfrost printed its 864 MHz core and 100 MHz bus clock
rates, then the machine stopped before the next, normally immediate GPU-ID
line. The same boundary occurred after an execute/stop cycle and with the MIPS
left running, so the stop implementation was not the root cause. MIPS startup
needed an earlier display-fabric prerequisite before Linux's first GPU MMIO
access.

A one-boot `modprobe.blacklist=panfrost` isolation test confirmed the boundary:

- the pinned firmware passed its hash and BSS execution witness and remained
  running across the Linux handoff;
- the kernel command line contained the temporary Panfrost blacklist;
- Cedrus, AIC8800, networking, SSH, serial getty, and the Debian root filesystem
  came up;
- `systemctl is-system-running` reported `running` with no failed units;
- Panfrost and DRM scheduler modules were absent, and Linux still created no
  `/dev/mips` device.

The blacklist was transient and was not saved to the U-Boot environment or
kernel image. A normal reboot after the isolation test removed the blacklist,
left the MIPS off, loaded Panfrost, reached `systemd` state `running`, and
reported no failed units.

Register isolation then recovered the missing prerequisite. SPL already leaves
the display bus clock/reset enabled, but the video2 PLL parent and the deint,
panel, SVP-DTL, and AFBD module clocks are gated. The safe pre-start sequence:

```
0x02001050 |= BIT(31)       # video2 PLL parent
0x02001db0 |= BIT(31)       # deint, cold divider preserved
0x02001db4 |= BIT(31)       # panel, cold divider preserved
0x02001db8 |= BIT(31)       # SVP-DTL, cold divider preserved
0x02001dc0 |= BIT(31)       # AFBD, cold divider preserved
0x02001dd8 |= BIT(16)|BIT(0)

0x05700004 <- 0x00000001
0x05700044 <- 0x11111111
0x05700088 <- 0x11111111
0x05700000 <- 0xfff11111
0x05700040 <- 0x00011111
0x05700080 <- 0x00001111
0x05700084 <- 0xfff000ef
0x0525c038 <- 0x00000100
```

With only those writes, the mixer remained readable, the MIPS passed its BSS
execution witness, and Linux booted with Panfrost enabled. Panfrost read GPU ID
`0x7093`, reported one shader and one L2, registered DRM minor zero, and created
`/dev/dri/card0` plus `/dev/dri/renderD128`. Debian reached `running` with zero
failed units. The same handoff passed first as a manual register experiment and
again from the installed cleaned U-Boot implementation.

The broader factory sequence is not safe to carry forward. A diagnostic
`factory-start` path containing PH, TVCAP, HDMI, and LVDS phases wedged after
MIPS release and has been deleted. Direct INCAP access at `0x06940000` wedges
independently even after reconstructing the display and TVCAP clocks and was
also excluded. LVDS registers become ARM-accessible once the display clock tree
is prepared, but no LVDS write is required for the proven Linux handoff, so
they remain out of `h713_mips`.

The specific claim that stock register `0x051c0010 <- 0x01800045` stalls ARM
UART and USB ACM is **withdrawn**. That observation predates
`h713_display_prepare()` and was a clocking artifact, not a property of the
register. Retested on the bench on 2026-07-28 with the MIPS held in reset and
only the prepared clock tree applied by hand:

- the whole LVDS window `0x051c0000..0x051c0057` reads back zero, so the block
  is idle rather than absent;
- `0x051c0010` is readable, and the stock write lands and persists — a
  subsequent read returns `0x01800045`;
- the write is repeatable: two back-to-back writes both completed, and no other
  register in the window changed, so it behaves as a standalone enable rather
  than the entry point of a state machine;
- UART stayed responsive throughout. An observed reset during the first attempt
  was the 16 s watchdog expiring (`wdt start` does not self-service), not a
  stall; re-running the whole sequence inside a single `;`-separated line
  reproduced the writes with no reset.

The cold module-clock dividers were captured in the same session and
independently corroborate the recovered frequencies: `0x02001050` is
`0x08003101` (N=49, 1200 MHz), and deint/panel `0x00000007` (÷8 = 150 MHz) and
SVP-DTL `0x00000005` (÷6 = 200 MHz) match the documented rates. AFBD
`0x00000000` (÷1) implies 1200 MHz, not the 600 MHz recorded earlier; treat the
AFBD figure as unverified. `0x02001dd8` already reads `0x00010001` cold, so
that line of `h713_display_prepare()` is a no-op against the current SPL.

The general lesson is that "this register wedges the interconnect" has meant
"this block was unclocked" every time it has been run down. Apply the same
suspicion to the remaining exclusions — INCAP at `0x06940000` in particular —
before treating them as hardware limits.

## Firmware startup trace (2026-07-28)

`h713_mips probe-trace` instruments the authenticated image with 671 volatile
word patches — code caves plus `j`/`jal` redirection — that store marker ids to
the firmware's uncached `0xae340000` alias, visible to the ARM at
`H713_MIPS_SHMEM_ADDR + H713_MIPS_TRACE_OFF`. Markers are streamed to UART as
they change rather than dumped after the poll loop, because the failure being
chased stalls the interconnect and kills the ARM console; a post-hoc dump
returns nothing in exactly the case that matters.

A marker fires when its call is **entered**, so the last marker reported names
a call that never returned. Relevant sites:

| Marker | Site | Enters |
| --- | --- | --- |
| 17 | `0x4b152cf0` | `0x4b10e770` (config parser, passed `0xabe01000`) |
| 20 | `0x4b152d10` | `0x4b159a60` (`memset`) |
| 24 | `0x4b152d30` | `0x4b152b2c` (early system init) |
| 30 | `0x4b10d598` | `0x4b115cec` |
| 44 | `0x4b152c24` | `0x4b152a5c` (nine `0x3003xxxx` resource loads) |
| 45 | `0x4b152c2c` | `0x4b1895c4` |

### The firmware needs three artifacts, not one

The startup hang was **missing vendor artifacts**, not a hardware gate. Stock
U-Boot loads a firmware image, a config blob, and a set of TSE databases; every
earlier run staged only the firmware.

Marker 20 is `memset(cfg["sys:dbg_buf"], 0, cfg["sys:dbg_buf_size"])`. Both
arguments come from config lookups (`0x4b10d40c` and `0x4b10d444`, each fetching
a singleton at `0x8b2536bc` and calling its `vtable[0x14]` with a string key).
With no config staged the parser at marker 17 reads uninitialized DRAM at
`0xabe01000`, the keys resolve to garbage, and `memset` walks a bad pointer
until the bus stalls.

`display_cfg.xml` documents the layout, and the parser's `0xabe01000` argument
is exactly the uncached alias of its `cfg_file` LMA:

| Region | LMA | Size | Staged from |
| --- | --- | --- | --- |
| boot code + C code | `0x4b100000` | `0xc01000` | `display.bin` |
| debug buffer | `0x4bd01000` | `0x100000` | — (cleared) |
| cfg file | `0x4be01000` | `0x40000` | `display_cfg.xml` |
| TSE data | `0x4be41000` | `0x100000` | concatenated `*.TSE` |
| frame buffer | `0x4bf41000` | `0x1a00000` | — (cleared) |

The TSE window takes `database.TSE`, `projecttable.TSE`,
`ProjectID_0x0012.TSE`, and `pq_custom.TSE` **simply concatenated** in that
order (347,816 bytes; kept as `local/mips-display/tse_blob.bin`). Each file is
magic-tagged `TSE` plus a type byte, so the firmware evidently scans for the
magic rather than indexing fixed offsets. Stock U-Boot selects the ProjectID
file via a `mips_projectID` value; `0x0012` is the literal in its binary.

Stage each window with its own fastboot pass and exit with `fastboot continue`
— a warm reset destroys staged DRAM (see [flash.md](flash.md)). `probe-trace`
clears everything above the image except the config and TSE windows, so those
two survive; the firmware image must be re-staged for every run because both
the trace patches and the running firmware modify it.

### Run protocol: one probe per boot

**A `probe-trace` or `probe-ready` run leaves hardware state that breaks the
next run**, and `h713_mips_stop()` does not clean it. The symptom is a stall at
marker 12, the firmware's interrupt init. After a run, even U-Boot's `reset`
command hangs, so recovery is a physical power cycle.

This single rule accounts for every irreproducible result recorded earlier in
this document. Runs that looked like they proved TVCAP ordering, TSE damage, or
non-determinism were second-or-later runs on one boot. Bench procedure:

1. power cycle;
2. `mw.l 0x4be01000 0 0x50000`;
3. stage `display_cfg.xml`, the TSE blob, then `display.bin`;
4. `h713_mips verify` — must print `16c74a28...`;
5. exactly one `h713_mips probe-trace` (or `probe-ready`).

Treat any result from a second run on the same boot as void.

### TVCAP: the ARM does enable it, with specific values

This section previously said the ARM must leave TVCAP alone. That was drawn
from `probe-trace` A/B runs which set the gates with `|= BIT(31)` and released
them mid-run from the poll loop; both harmed firmware startup.

Stock U-Boot's fastlogo disproves the general claim. It enables TVCAP with
explicit values as part of bringing up the display:

```
0x02001d88 <- 0x00010001    bus gate + reset
0x02001d6c <- 0x80000305    TCD3
0x02001d74 <- 0x81000001    VINCAP DMA
0x02001d84 <- 0x80000000    HDMI audio
0x02001d80 <- 0xc0000000    TVCAP bus
```

So the rule is about *values and ordering*, not about ownership. Do not set
these gates by OR-ing an enable bit onto whatever the cold state happens to be.

### Current state: the MIPS never receives a timer interrupt

With all three artifacts staged and one run per boot, the firmware executes
every instrumented point: markers 10-14, 16-24, 26-53, 62-66, 68-78, 84-89,
93-96, 101-104, 111, and 130-132. The HDMI-RX byte load at physical
`0x06840093` succeeds, and the four-registration group at `0x8b128020`
completes. `status` is 1, the BSS witness is clear, both CPU_COMM magics read
`deadbeef`, and the ARM flag reads back `0x5`. An uninstrumented `probe-ready`
with a ten-second budget behaves the same.

`MIPS READY` is never set, and the trace explains why. Markers 1-9 — the entire
CPU_COMM path — never fire:

```
0x4b15257c   ThreadX thread entry           (markers 6, 7)
  0x4b12423c   CPU_COMM init                (markers 8, 9)
    0x4b123828   share-register reader      (markers 1, 2, 3)
    0x4b11abbc   spinlock + slave init      (markers 4, 5)
```

`0x4b15257c` has no direct callers; its address is materialised into `$a3` at
`0x4b152d38`/`0x4b152d44` and handed to a thread-creation call. That call sits
between marker 24's site (`0x4b152d30`) and marker 25's (`0x4b152d54`). Marker
24 fires and marker 25 does not, so the early-system-init call never returns
and the thread is never created.

The innermost stall is marker 53's call into `0x4b1839dc` (marker 54 does not
fire). Inside it, trace slots 104 and 105 — which capture the polling loop's
current and initial tick rather than marker ids — both read **zero**. The loop
is `while ((now - start) < 0x33)`, so a tick that never advances never expires.

The tick source is a software counter at `0x4b252cc0` (BSS), read under an
interrupt-disable/restore pair at `0x4b104b04` and incremented by a timer ISR.
It reads zero, so **the MIPS is receiving no timer interrupt**. The complete
chain is:

> no MIPS timer IRQ -> tick counter stays 0 -> the wait loop never expires ->
> `0x4b1839dc` never returns -> thread creation never runs -> the CPU_COMM
> thread never starts -> `MIPS READY` is never set.

The firmware does program an interrupt block: marker 12's function
`0x4b147950` clears CP0 Cause IP bits and writes `0x03061300..0x03061320` in
the MIPS control window. What is not yet established is where the timer source
lives, whether its clock or reset needs releasing from the ARM the way the
display tree did, and whether the CP0 `Status` interrupt enable is being set.
That is the next thing to recover.

The `0x4b22cf68` flag consulted before each tick read is initialised data whose
image value is `1`, so the stub path is not the issue; the real read is taken
and returns zero.

**Framing correction.** Calling "no timer interrupt" the root cause is too
strong. The tick is a ThreadX software counter incremented by the CP0 Compare
ISR, and interrupts are legitimately masked this early in startup, so a
stopped tick is expected at that point rather than a fault. The real defect is
that `Rx_HDCP14_LoadKey` polls HDMI-RX `0x06840093` for an acknowledgement
that never arrives, and its timeout — which stock relies on to recover — cannot
expire while the tick is stopped. The timer needs no CCU gate either: it is the
MIPS core's own CP0 Count/Compare, and the coprocessor cannot reach the CCU at
all, so every clock it depends on must come from the ARM.

## The ARM display path, and why it is not independent

`LogoRegData.bin` is a fourth vendor artifact that stock U-Boot parses and
applies itself before blitting its logo, as its own strings show
(`Invalid logo regbin:%s`, `create_fastlogo_inst fail!`,
`Display fastlogo finish!`). It is a masked register write-table of 16-byte
`{address, value, mask, type}` records where type 1/2/4 is the access width and
a zero address with type `0xff` carries a delay. Records are 16 bytes but only
4-byte aligned and the stream changes phase between runs, so a walker must
resynchronise rather than step a fixed lattice.

The container is **indexed**. Descriptors of `0x18` bytes start at offset `0x10`,
their count given by the header at `+0x08` divided by `0x18`. Each begins with a
project ID matching the `ProjectID_*.TSE` filenames, and two words select that
project's tables:

| Field | Selects |
| --- | --- |
| word3 & 0xffff | prologue variant, 1-based |
| word3 >> 16 | timing variant, 0-based |
| word4 & 0xffff | DE/mixer variant, 0-based |

A working configuration is a *consistent triple*, not three ranges picked by
eye; choosing them by hand produced combinations no project uses.

**The ARM path is not independent of the MIPS.** Stock's fastlogo releases the
coprocessor as an integral step of putting its logo on screen, so a boot console
cannot be reached from the ARM alone.

### Use the board's own artifacts

Everything in this project had been derived from a captured dump that is **a
different firmware revision than the bench board carries**:

| Artifact | Board | The dump previously used |
| --- | --- | --- |
| `display.bin` | 1255696 B, `4380f1b3...` | 1256216 B, `16c74a28...` |
| `LogoRegData.bin` | 15652 B, 15 descriptors | 14380 B, 13 descriptors |
| stock U-Boot | `2018.05-00027-ge159793` (Aug 2025) | `2018.05-00021-g346d3eb` (Mar 2025) |

Consequently the pinned hash, every block offset, the project-to-table mapping,
the HDCP wait address, the BSS bounds and the 671-entry trace table were all
wrong. Any conclusion measured against them is void, including the earlier
four-project sweep and the whole marker map.

The board's copies live in the stock FAT bootloader partition at `mmc 1:2`, and
`h713_disp auto <project>` reads them from there. Extracted copies are kept in
`local/mips-display/board-b-mips/`, and the board's real stock bootloader --
pulled from its TOC1 container at `0xc00800` in the eMMC capture -- in
`local/mips-display/board-b-stock/`. Slots A and B are byte-identical.

Stock's fastlogo sequence is **byte-identical between the two U-Boot builds**,
so the transcription below stands; what was wrong was the data it was pointed
at.

### Stock fastlogo, transcribed

The stock U-Boot is **Thumb**, not ARM -- its first word is only the exception
vector. Load base `0x4a000000`, verified by every string address appearing as a
literal. In the board's build `"Display fastlogo finish!"` prints at
`0x4a022c3a`.

```
0x02000150 <- 0x22ffff22    PH pin mux (PH0/1 stay UART0)
0x02001d88 <- 0x00010001    TVCAP gate/reset
0x02001040 <- 0xb8003501    PLL enable (cold state is off)
0x02001d6c <- 0x80000305
0x02001020 <- 0xb8006301    PLL_PERIPH0  -- SEE HAZARD
0x02001d74 <- 0x81000001
0x02001068 <- 0xb8002f01    PLL enable (cold state is off)
0x02001d84 <- 0x80000000
0x02001d80 <- 0xc0000000
0x06e00004/8/0 set, cleared, set again   (reset pulse)
0x06940000 <- 1             INCAP
0x051c0010 <- 0x01800045    LVDS enable
<MIPS clock/reset/bootaddr/release>
delay 300 ms
0x051c0010 <- 0x45          LVDS finalise
```

Within the table-application loop, stock also issues an LVDS FIFO reset after
the timing table -- pulse bit 8 of `0x05700088`, then **rewrite `0x0588000c`
with its saved value** -- and writes `0x0525c038 <- 0x100` before the DE table.

**INCAP does not wedge.** `0x06940000 <- 1` is safe once the fabric is
configured, on stock and on ours.

**TVCAP is enabled by the ARM**, with the explicit values above rather than by
OR-ing an enable bit onto the cold state.

**Hazard: do not write `0x02001020`.** That is PLL_PERIPH0, which clocks MMC and
the buses. Stock writes a value already in force in its own boot context; ours
runs at `0xb8003100`, and replaying stock's write powers the bench board off.
`0x02001040` and `0x02001068` are safe because both are disabled cold.

**Bench hazard: unplug USB after staging.** With the DC adapter and USB both
connected the board browns out when the display fabric comes up. Two brown-outs
were misattributed to register writes before this was identified.

### Firmware facts, re-derived from the board's image

- boot vector erets to `0x8b1b1148`
- BSS is cleared from `0x8b232c00` to `0x8bac7c40`
- `Rx_HDCP14_LoadKey` polls HDMI-RX `0x06840093` with its wait bound at
  `0x4b13d6f8`; `h713_disp ... nowait` rewrites it so the wait expires at once
- the execution witness sits *inside* BSS, so the firmware zeroes it and then
  reuses that memory. Only the seed surviving proves non-execution; a zero or
  any other value proves the write

### Where it stops

With the board's own artifacts, a consistent project triple, stock's sequence
and the coprocessor executing, the panel stays dark and the LVDS FIFO at
`0x05880FE0` never changes between consecutive reads. Projects `0x16`, `0x33`,
`0x34` and `0x35` -- the ones selecting the timing variant that matches this
panel -- were all tried, with and without the HDCP override.

`display_cfg.xml` carries an `elog_init_setting`. With `mode='2'` (buffer) and
`async_display='0'` the firmware runs and logs **nothing at ERROR level**, so by
its own account startup completes without faults. It does, however, wedge the
interconnect some seconds *after* the sequence completes, which suggests live
activity that later fails rather than a coprocessor sitting idle.

Open threads, in priority order:

1. `source_id` in `display_cfg.xml` is `1` (VideoDecoder), not `2` (Image). A
   faithfully-displayed empty decoder stream is black by design and would log
   no error. Patch it at `0x4be01e48` after `h713_disp load`.
2. Raise the elog level with `async_display='0'` and read the firmware's own
   account of what it does before it wedges.
3. Time the delayed hang; a consistent interval points at a firmware timer.
4. Rebuild the trace instrumentation against `4380f1b3...` if markers are needed
   again -- the existing 671-entry table targets the wrong image.

## Fixed: the walker dropped `type 0xfe`, and its delays were in the wrong unit

`h713_logo_walk()` in `arch/arm/mach-sunxi/h713_mips.c` understood three record
types: 1/2/4 (a masked write of that width) and `0xff` with a zero address (a
delay). Anything else it skipped by advancing four bytes and resynchronising,
which silently discarded a fourth type. The delay unit was a guess.

Both are now settled by reading the vendor applier, not by inference. Stock
U-Boot 2018.05 for this board (`local/mips-display/board-b-stock/u-boot-stock.bin`)
is **32-bit ARM, Thumb-2, load base `0x4a000000`** — not AArch64, which is why
earlier disassembly attempts produced noise. The record applier is at
`0x4a025164`, reached through the ops table at `0x4a025488+0x24`; it belongs to
the LogoRegData module, whose neighbouring strings are `LogRegData.bin version
is %u-%u-%u-%u`, `Get reg of type:%u fail!` and `null fastlogo inst!!!`.

It walks a `{?, records, count}` descriptor, stride 16, type word at `+0xc`:

| type | what stock does |
| --- | --- |
| `<= 4` | `*addr = (*addr & ~mask) \| value`, **always a 32-bit access** |
| `0xfe` | one read, then `*addr = cur & ~mask`, then `*addr = cur \| mask` |
| `0xff` | `udelay(value)` |

Three corrections fall out of that:

**`type 0xfe` is not a poll — it is a masked bit pulse.** The `value` word is
never read. Our four records all carry `mask 0x80000000` on the display PLL at
`0x058c0014`, and bit 31 there is PLL_ENABLE, so each one is a **PLL restart**:
drop enable, raise it again. They sit at container offsets `0x0ec4`, `0x1734`,
`0x1d1c`, `0x1fa4`, and the one at `0x1734` is inside **timing block 6 — the
block this panel uses** — in the middle of a divider reprogram:

```
+0x16e4 0x058c0014 <- 0x08000000 mask 0x08000000
+0x16f4 DELAY 500 us
+0x1704 0x058c0028 <- 0x00000000
+0x1714 0x058c0014 <- 0x0000001e mask 0x0000fffe   reprogram divider
+0x1724 DELAY 15000 us
+0x1734 PULSE 0x058c0014 mask 0x80000000            PLL off, PLL on
+0x1744 DELAY 15000 us
+0x1754 0x058c0014 <- 0x00002a00 mask 0x0000ffff   restore divider
+0x1764 0x058c0028 <- 0x00030000
```

We were skipping the restart outright, so everything written after that point
in the block landed on a PLL that had never been re-locked.

**The delays are microseconds.** `0x4a000d74`, the thunk the walker calls, tail-
branches to the delay core at `0x4a000d50`, which reads CNTPCT and busy-waits
`value * 0x18` ticks — 24 ticks per microsecond on the 24 MHz arch timer. The
`x1000` wrapper immediately after it at `0x4a000d78` is `mdelay`, and the walker
does *not* use it. So the old `mdelay()` path was 1000x too long before the cap
and wrong after it: the whole container is ~126 ms of delay in stock and was
about 4.6 s for us, with the two 15000 waits bracketing the PLL restart cut to
200 ms each. `H713_LOGO_MAX_DELAY_MS` is replaced by `H713_LOGO_MAX_DELAY_US`
at 100000, which only bounds a walk that has fallen into garbage — stock has no
ceiling at all, and the largest genuine value is 15000.

**The width field is vestigial.** Stock uses a 32-bit `ldr`/`str` for every
type in `0..4`. Moot for this container — all 838 write records are type 4, and
there is not a single type 1 or 2 — so the width switch is left in place.

The four `0xfe` records are also *new in this firmware revision*: the superseded
`research/bootloader_fat` extract has 774 writes, 89 delays and no `0xfe` at
all. Same for values — `+0x1664` writes `0x058c002c <- 0x00070010` where the old
extract had `0x00000010`.

### Bench result (2026-07-29): the fix works, the panel stays dark

Timing block 6 now applies `32 records, 1 pulse, 7 delays, 0 resync steps`, and
`0x058c0014` reads back `b9002a00` against the `a9002a00` the table writes. The
one differing bit is 28 — **PLL lock, set by hardware**. It cannot have been set
with the restart skipped, so the vendor's PLL sequence now completes correctly
for the first time. That is the `0xfe` defect closed, on hardware.

It did not light the panel, and it did not move `0x05880FE0`.

Two details from the same disassembly that our sequence still does not model,
both in the fastlogo state machine at `0x4a0228d4`, which applies groups
`0..count-1` where count is a `u16` at `inst->0x34 + 0x104`:

- stock's FIFO reset after group 1 is **conditional** on `readl(0x05880fe0)`
  being non-zero; `h713_disp_fifo_reset()` does it unconditionally.
- the mixer write (`0x100` to `0x0525c038`) happens *before* group 2 is applied,
  which is where we put it — that much is confirmed.

## The firmware overrides the panel timing with 1080p

Dumping the display blocks after `h713_disp auto 0x33`, with the coprocessor
running, and diffing against a replay of what prologue 3 + timing 6 + DE 5
actually wrote: **54 of 65 dumped registers hold exactly the written value.**
Eleven do not.

| register | table wrote | reads | who |
| --- | --- | --- | --- |
| `0x05700000` | `ffffffff` | `fff11111` | **ours** |
| `0x05700004` | `ffffffff` | `00000001` | **ours** |
| `0x0588001c` | `00000004` | `00000002` | firmware |
| `0x05880020` | `02f80550` | `04650898` | firmware |
| `0x05880024` | `02d00500` | `04380780` | firmware |
| `0x05880028` | `00140028` | `00290114` | firmware |
| `0x0588002c` | `00000014` | `8000003e` | firmware |
| `0x05880030` | `00010003` | `80040007` | firmware |
| `0x058c0014` | `a9002a00` | `b9002a00` | hardware (PLL lock) |
| `0x051c0014` | `18000000` | `18000040` | unattributed |
| `0x05600168` | `000003b2` | `00000002` | firmware (AFBD status) |

Reading `+0x20` as total geometry and `+0x24` as active, the LVDS group goes from
**1280x720 active / 1360x760 total** — the panel — to **1920x1080 active /
2200x1125 total**, standard 1080p60. `+0x28` moves consistently with it and
`+0x2c`/`+0x30` come back with bit 31 set.

Nothing in the container writes those values: timing block 6 is the only block
that touches `0x05880020`/`0x24` and it writes 720p, and no record anywhere in
the file writes `04650898` or `04380780` to them. The only ARM code after the DE
table is the clocks/TVCAP step, INCAP, `0x051c0010` and the MIPS release, none in
`0x0588xxxx`. So the coprocessor is the only candidate — **an inference from
exhaustion, not an observation**, and it should be treated as such.

Meanwhile the mixer, DE and AFBD stay at 720p (`mixer +0x20`/`+0x30` =
`02d00010`, AFBD `+0x20` = `02d00500`). The pipeline feeds 720p into a TCON
programmed for 1080p.

**The firmware does not defend the registers.** Re-imposing 720p after it has
run sticks — verified both with the raw table records and, when that turned out
to clear the firmware's bit 31 on `+0x2c`/`+0x30`, again with those bits
preserved. Neither changed anything observable.

The generic `h713_mips start` path calls `h713_display_prepare()` and therefore
narrows TVTOP `0x05700000` to `0xfff11111` and `+0x04` to `1`. The fastlogo
replay does **not** call that helper: `h713_disp_run()` applies the three vendor
tables, then calls `h713_mips_release_raw()`, which verifies the image, applies
only the optional HDCP wait override, and releases reset. Therefore the earlier
claim that the fastlogo replay overwrites its table-programmed TVTOP values was
stale and is withdrawn.

One replay divergence remains: stock pulses the FIFO reset only when
`0x05880fe0` is non-zero, while `h713_disp_run()` currently pulses it
unconditionally. This is the first cheap parity fix.

### The projector selector lookup — mapped, but dead on this startup path

Traced in `display.bin` (MIPS32 LE, raw image; external review, verified here
against the artifacts).

`_LoadTFDPanelTiming` builds the `Output_Resolution` selector `0x00060004` from
a hardcoded immediate pair at raw offset `0x88120`:

```
0x88120:  06 00 02 3c    lui   v0, 0x0006
0x88124:  04 00 42 24    addiu v0, v0, 4
```

Parameter 6 is `Output_Resolution`. `_LoadTFDPanelTiming` asks the TSE object for
the row count through vtable slot `+0x48`, then calls slot `+0x5c` with field
number 6 at `display.bin` offset `0x881ec`. It compares the returned value with
the compiled selector at `0x881f0..0x88204`. For a matching row it obtains the
raw row pointer and copies selected fields from the 0x54-byte row at
`0x882e8..0x88374`. There is no second lookup through the compact u16 mode lists.

`database.TSE`'s `OUTPUT_TIMING_PROJECTOR` module name begins at `0x30c77`:

```
4f 55 54 50 55 54 5f 54 49 4d 49 4e 47 5f 50 52
4f 4a 45 43 54 4f 52 00                         OUTPUT_TIMING_PROJECTOR\0
```

It has six selector predicates, followed in the same order by six 0x54-byte
rows:

| selector | predicate offset and bytes | row offset | total | active |
| --- | --- | --- | --- | --- |
| 4 | `0x30ca9: 04 00 06 00` | `0x30df0` | 2200x1125 | 1920x1080 |
| 3 | `0x30ccd: 03 00 06 00` | `0x30e44` | 1360x760 | 1280x720 |
| 1 | `0x30cf1: 01 00 06 00` | `0x30e98` | 858x525 | 720x480 |
| 2 | `0x30d15: 02 00 06 00` | `0x30eec` | 864x625 | 720x576 |
| 8 | `0x30d39: 08 00 06 00` | `0x30f40` | 1500x825 | 1366x768 |
| 11 | `0x30d5d: 0b 00 06 00` | `0x30f94` | 938x480 | 640x360 |

The decisive selector-4 row fields are:

```
0x30dfc: 98 08 00 00    2200 total columns
0x30e10: 80 07 00 00    1920 active columns
0x30e20: 65 04 00 00    1125 total lines
0x30e34: 38 04 00 00    1080 active lines
```

They explain the exact `0x04650898` / `0x04380780` register readback without
using the unrelated compact 1080 tuple in `WCEData`. The earlier cited
`0x1e86f` is inside that separate payload; its compact geometry tuple actually
begins at `0x1e877`.

The selector-3 row is equally explicit:

```
0x30e50: 50 05 00 00    1360 total columns
0x30e64: 00 05 00 00    1280 active columns
0x30e74: f8 02 00 00     760 total lines
0x30e88: d0 02 00 00     720 active lines
```

This was missed by searching for a contiguous u16
`(1360, 760, 1280, 720)` tuple: the projector timing row stores separated u32
fields. It independently agrees with `LogoRegData.bin`, whose record at
`0x1838` writes `0x02f80550` to TCON register `0x05880020` and whose next record
writes `0x02d00500` to `0x05880024`.

The compact `(1440, 741, 1280, 720)` tuple does exist at `database.TSE`
offsets `0x1f9f9` and `0x2f376`, with bytes
`a0 05 e5 02 00 05 d0 02`, in the separate `WCEData` and `THDMI_ModeList`
payloads. None of the six projector selectors reaches it.

The mixer at `0x0525c000+0x00` and DE at `0x0524c000+0x10` both read
`0x02e4059f`, a size-minus-one encoding of 1440x741. That remains unexplained
internal processing geometry; it is not evidence that the TCON should use a
1440x741 total. The actual projector lookup and the vendor TCON register table
both identify 1360x760 as the panel timing.

So the timing input is a **hybrid**: geometry in the database, selector
initializer compiled into the firmware. Rewriting the `addiu` immediate from 4
to 3 requests the database's 1280x720-active projector row if that initializer
survives the following object call. The immediate byte is at `0x4b188124` once
the raw image is loaded.

**First hardware test, 2026-07-29: changing only that byte was a no-op.** Both

```
h713_disp auto 0x33 720p
h713_disp auto 0x33 nowait 720p
```

authenticated the expected firmware, reported selector 3, proved MIPS
execution, and then read back the unchanged values:

```
0x05880020 = 04650898    2200x1125 total
0x05880024 = 04380780    1920x1080 active
```

The HDCP override therefore has no bearing on the timing result.

The reason the immediate alone is insufficient is visible at the start of
`_LoadTFDPanelTiming`. The function initializes the selector stack slot at
`sp+0x28`, then calls vtable slot `+0x70` with `a1=6` and `a2=&sp[0x28]`:

```
0x88118: 28 00 a6 27    addiu a2, sp, 0x28
0x8811c: 70 00 43 8c    lw    v1, 0x70(v0)
...
0x88158: 28 00 a2 af    sw    v0, 0x28(sp)
0x8815c: 09 f8 60 00    jalr  v1
```

That makes the compiled value an initializer for an in/out parameter, not an
unconditional final selector. The hardware result shows that either this call
replaces it or this loader is not the final writer.

The revised patch keeps the getter call but redirects its in/out pointer to the
unused stack slot at `sp+0x2c`, initialized with the same default. The actual
comparison slot at `sp+0x28` then remains forced to selector 3:

```
0x88118: addiu a2, sp, 0x28 -> addiu a2, sp, 0x2c
0x88124: addiu v0, v0, 4   -> addiu v0, v0, 3
0x88138: sw zero, 0x24(sp) -> sw v0, 0x2c(sp)
```

`sp+0x2c` is otherwise unreferenced throughout the function. The `sp+0x24`
slot is an output pointer written by the row-fetch call immediately before it
is read. U-Boot guards all three stock instructions after authenticating the
firmware and refuses the patch if any differs.

For the second test, the prediction remained
`0x05880024 = 02d00500` (1280x720 active) and
`0x05880020 = 02f80550` (1360x760 total). If those registers remained 1080p,
the loader had to be dead on this startup path or overwritten by a later
writer.

**Second hardware test, 2026-07-29: the revised selector was also a no-op.**
The command read all three patched sites back from executable DRAM:

```
0x4b188118 = 27a6002c
0x4b188124 = 03
0x4b188138 = afa2002c
```

The TCON nevertheless remained at `04650898 04380780`. This rules out an ARM
cache/write-visibility failure and rules out the vtable `+0x70` getter as the
only reason the original byte patch failed. The remaining alternatives are
that `_LoadTFDPanelTiming` is not called on this startup path, or a later writer
replaces its result.

The next build instruments function entry to separate those cases. It replaces
the prologue at `display.bin+0x8810c` with a guarded jump to the unused zero
cave at `+0x300`. The cave writes `0x7133` through the firmware's uncached
`0xae340300` alias, executes the displaced stack adjustment, and returns to
`+0x88114`. U-Boot reads the corresponding ARM address `0x4e340300` after the
run and prints:

```
H713 MIPS: _LoadTFDPanelTiming marker=0x00007133   called
H713 MIPS: _LoadTFDPanelTiming marker=0x00000000   not called
```

**Third hardware test, 2026-07-29: the marker remained zero.** The authenticated
firmware ran and again changed the TCON to
`04650898 04380780`, but U-Boot printed:

```
H713 MIPS: _LoadTFDPanelTiming marker=0x00000000
```

Therefore `_LoadTFDPanelTiming` is not called on this startup path. The
selector-to-record mapping above is valid static analysis, but the immediate at
`display.bin+0x88124` is not the source of this run's 1080p write. Both the
selector patch and its one-shot marker have been removed from U-Boot; the
`h713_disp ... 720p` modifier no longer exists.

There is a separate panel-specific timing path. `display_cfg.xml` contains the
actual panel geometry at offsets `0x729`, `0x760`, `0x794`, and `0x7b3`
respectively (the literal ASCII bytes rendered below):

```
<htotal typical='1360' min='1360' max='1360'/>
<vtotal typical='760' min='760' max='760'/>
<hde_size val='1280'/>
<vde_size val='720'/>
```

In `display.bin`, the function beginning at raw offset `0x2a6ec`
(`98 ff bd 27`, `addiu sp,sp,-0x68`) is identified by its
`load_panel_timing` log string at `0xf1470`. It loads a database timing, then
queries the parsed XML keys. For example, the htotal override is:

```
0x2a88c: 1f 8b 05 3c    lui   a1, 0x8b1f
0x2a898: 09 f8 40 00    jalr  v0
0x2a89c: 38 bc a5 24    addiu a1, a1, -0x43c8
0x2a8a0: 02 00 40 10    beqz  v0, 0x2a8ac
0x2a8a4: 48 00 a2 8f    lw    v0, 0x48(sp)
0x2a8a8: 18 00 02 ae    sw    v0, 0x18(s0)
```

The address formed in the call's delay slot is `0x8b1ebc38`, whose raw string
at `display.bin+0xebc38` is
`73 79 73 3a 70 61 6e 65 6c 3a 68 74 6f 74 61 6c 3a 74 79 70 69 63 61 6c 00`
(`sys:panel:htotal:typical\0`). The corresponding vtotal key is at
`+0xebc8c`, and the store to timing-structure offset `+0x1c` is at
`+0x2a8d8` (`1c 00 02 ae`). The direct wrapper call to this loader is at
`+0x2a1a8` (`bb a9 c4 0e`, `jal 0x8b12a6ec`).

The wrapper is the `CrtcDb` virtual method at slot `+0x14`: the vtable begins
at raw `+0xf13ac`, and its slot at `+0xf13c0` contains
`8c a1 12 8b` (`0x8b12a18c`). The higher-level CRTC initialization path loads
the `CrtcDb` object from offset `+0x4f0` at raw `+0x27e94`
(`f0 04 04 8e`), loads vtable slot `+0x14` at `+0x27e9c`
(`14 00 42 8c`), and calls it at `+0x27ea0`
(`09 f8 40 00`). This supplies a precise next marker site and call chain,
without claiming that the hardware run reached it.

This is now the next candidate to trace. Static references establish that the
path exists and consumes the correct XML totals; they do not yet establish
that it executes before the observed write or that it is the final TCON
programmer.

## `0x05880FE0` is not a scan-liveness signal

Reading the LVDS page wider than the sequence touches:

```
05880040: 3fffffff 38f8f8f8 deadabba deadabba
05880050 .. 058800f0: deadabba throughout
```

`deadabba` is the interconnect's **undecoded-read signature**. The block decodes
only `0x00..0x44`; there is no status or counter register anywhere in that page,
so "read the block twice and look for a tick" cannot work — and back-to-back
reads of the decoded window are indeed byte-identical.

`0x05880FE0` is the exception: it reads `00000000`, not `deadabba`, so it is
decoded — a real register that is simply always zero. Combined with stock gating
its reset on that register being *non-zero*, the likeliest reading is a
fault/underrun status where zero means "no fault".

**So the criterion this investigation has been measured against for months is
not a signal.** Every "the FIFO never moves" result should be re-read as "we
were watching a constant". Project selection in particular was ruled out on the
basis of a dark panel, which was never a sensitive test; `0x05880024` now gives
a direct readout and that thread should be reopened.

Also recorded from these runs: the MIPS execution witness differed between two
otherwise identical runs (`0x8baa0000` vs `0x00000000`) — both count as executed,
but firmware startup is **not deterministic**. The board hangs 5-30 s after
the sequence and has now powered itself off after multiple runs, without a
preceding UART message. Linux was never started, which rules out a Linux kernel
panic but does **not** rule out a MIPS firmware panic or exception: its logging
may be buffered, incomplete, or lost when power drops. A MIPS fault, watchdog,
power-management action, or an electrical/PMIC shutdown all remain possible.
The delayed power cut is uncharacterised and is now the practical limit on
bench iteration.

### MIPS-first recovery plan

The next objective is not merely another visible-panel attempt. It is to make
the coprocessor a known-good component before attributing any remaining display
failure to scanout, LVDS, or panel control.

#### Gate 1 — a reproducible, stock-parity launch

Build one diagnostic command around a single cold-boot run. It must:

1. load and authenticate the board's `display.bin`, `display_cfg.xml`, all four
   TSE inputs, and `LogoRegData.bin`;
2. clear only the documented firmware workspaces and preserve the staged config
   and TSE windows;
3. apply the selected project 0x33 tables with the already-fixed `0xfe` pulse
   and microsecond delay semantics;
4. gate the FIFO reset on `0x05880fe0 != 0`, matching stock;
5. prepare the CPU_COMM shared region and publish its address and size before
   reset release;
6. release the MIPS exactly once and leave it running. Do not use
   `h713_mips_stop()` as cleanup; a physical power cycle remains the only known
   clean boundary after firmware execution.

The omission of stock's `0x02001020` PLL_PERIPH0 write remains intentional:
reprogramming that live clock can power the board off. It is a documented
safety exception, not an unnoticed parity difference.

Acceptance is the authenticated hash, overwritten BSS witness, CPU status 1,
both CPU_COMM magic words intact, ARM flag `0x5`, and the MIPS READY bit set.
The existing `h713_disp auto` path proves only instruction execution because it
does not publish CPU_COMM shared memory; it cannot satisfy this gate.

The Gate-1 implementation is `h713_disp mips-test 0x33`. It automatically uses
the guarded HDCP-wait override, prepares and publishes CPU_COMM, runs the full
project-0x33 display sequence, and waits up to four seconds for both MIPS READY
and application-ready. It prints the final CPU status, execution witness, both
magic words, and ARM/MIPS flags. It deliberately leaves the MIPS running on
both success and failure: power-cycle after collecting its output, and do not
run a second MIPS command on the same boot.

**First Gate-1 hardware run, 2026-07-29: execution passed; readiness failed.**
The conditional FIFO-reset status was `0x00000002`, so the reset ran, and the
post-sequence status cleared to zero. The authenticated MIPS stayed released
and overwrote its witness, while the published CPU_COMM control words remained
intact:

```
H713 MIPS: readiness status=0x00000001 witness=0x8baa0000
H713 MIPS: CPU_COMM magic=deadbeef/deadbeef ARM=00000005 MIPS=00000000
H713 MIPS: firmware readiness not proven; core left running
```

This is not a cache-publication or reset-release failure. It establishes the
remaining boundary precisely: the firmware did not set the CPU_COMM MIPS READY
bit during the four-second window. It does not by itself distinguish a stalled
startup task from a MIPS exception.

The first `mips-trace` build incorrectly reused the known-stale 671-word trace
table from `display.bin` revision `16c74a28...`. Its guards rejected the first
moved site before reset release:

```
H713 MIPS: trace site 0x4b1238d8 is not pristine
```

That run did not execute the MIPS and produced no readiness evidence. Reusing
that table contradicted the artifact warning above; weakening its guards would
have corrupted executable code.

The corrected nine-marker trace was accepted and the MIPS executed, but every
marker remained zero:

```
H713 MIPS: handshake trace 0 0 0 0 0 0 0 0 0
H713 MIPS: readiness status=0x00000001 witness=0x00000000
H713 MIPS: CPU_COMM magic=deadbeef/deadbeef ARM=00000005 MIPS=00000000
```

Marker 6 was the ThreadX application entry and marker 7 the following
CPU_COMM call. Since marker 6 never fired, CPU_COMM is downstream of the
current failure: the application thread is never scheduled. Shared-memory
publication cannot fix that boundary.

The 26-marker run narrowed the failure to one non-returning construction call:

```
H713 MIPS: handshake trace 0 0 0 0 0 0 0 0 0 10 11 12 13 14 15 0 17 18 19 20 21 22 23 24 25 0
H713 MIPS: readiness status=0x00000001 witness=0x00000000
H713 MIPS: CPU_COMM magic=deadbeef/deadbeef ARM=00000005 MIPS=00000000
```

Marker 25 is the call to `0x8b15340c` at raw `display.bin+0x53610`;
the exact little-endian call word is `03 4d c5 0e`. Marker 26 is the following
ThreadX thread-creation call at raw `+0x53634`, bytes `25 72 c5 0e`. Marker 16
is the later scheduler call at raw `+0x1f4c`, bytes `e4 15 c4 0e`. Thus
`0x8b15340c` was entered but did not return, application construction never
reached thread creation, and the scheduler was never entered. This is upstream
of CPU_COMM and does not yet distinguish a blocking initialization call from a
MIPS exception.

The next exact-image trace has 56 markers. Markers 1-26 remain unchanged;
markers 27-56 trace every call in `0x8b15340c`, in ascending call-site order:

```
marker  raw offset  pristine bytes  original target
27      0x053444    7c 01 c6 0e    0x8b1805f0
28      0x053454    4b 35 c4 0e    0x8b10d52c
29      0x053470    09 f8 40 00    jalr v0
30      0x053478    4b 35 c4 0e    0x8b10d52c
31      0x053494    09 f8 40 00    jalr v0
32      0x0534a4    8e 01 c6 0e    0x8b180638
33      0x0534b4    8e 01 c6 0e    0x8b180638
34      0x0534c0    2e 28 c6 0e    0x8b18a0b8
35      0x0534c8    7d 25 c6 0e    0x8b1895f4
36      0x0534d0    4b 35 c4 0e    0x8b10d52c
37      0x0534ec    09 f8 40 00    jalr v0
38      0x0534fc    1e 41 c4 0e    0x8b110478
39      0x053504    cf 4c c5 0e    0x8b15333c
40      0x05350c    a9 27 c6 0e    0x8b189ea4
41      0x053520    09 f8 40 00    jalr v0
42      0x053528    ef 9e c6 0e    0x8b1a7bbc
43      0x053530    be 61 c5 0e    0x8b1586f8
44      0x053538    1e a1 c4 0e    0x8b128478
45      0x053540    c4 79 c6 0e    0x8b19e710
46      0x053548    87 73 c5 0e    0x8b15ce1c
47      0x053550    e3 ec c5 0e    0x8b17b38c
48      0x053558    af 10 c6 0e    0x8b1842bc
49      0x053560    3b 12 c6 0e    0x8b1848ec
50      0x053568    11 f3 c5 0e    0x8b17cc44
51      0x053570    c6 78 c6 0e    0x8b19e318
52      0x053578    60 b1 c6 0e    0x8b1ac580
53      0x053580    e5 4f c5 0e    0x8b153f94
54      0x053590    df 1b c4 0e    0x8b106f7c
55      0x053598    df 1a c4 0e    0x8b106b7c
56      0x0535a0    ed 23 c4 0e    0x8b108fb4
```

The 336 guarded words match the exact `4380f1b3...` image. Each direct call
tail-jumps to its original target; the four indirect sites tail through
`jr v0`, preserving the original target and call-site return address. All 30
new call sites and five-word caves have been disassembled after applying the
patch in memory. Run this trace once after a cold boot and physically
power-cycle afterward.

The 56-marker DDR3 bench image was
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (865,817 bytes), SHA-256:

```
e03823451c391b14ff03dd96644dd726fccfd060e4911a7fe39d0fe1f4cb4a4e
```

Its hardware run reached marker 38 and no later marker:

```
H713 MIPS: handshake trace 0 0 0 0 0 0 0 0 0 10 11 12 13 14 15 0 17 18 19 20 21 22 23 24 25 0 27 28 29 30 31 32 33 34 35 36 37 38 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
H713 MIPS: readiness status=0x00000001 witness=0x00000000
H713 MIPS: CPU_COMM magic=deadbeef/deadbeef ARM=00000005 MIPS=00000000
```

Marker 38 is the call at raw `display.bin+0x534fc`, pristine bytes
`1e 41 c4 0e`, targeting `0x8b110478`. Marker 39 is the immediately following
call at raw `+0x53504`. Thus `0x8b110478` was entered and did not return.

This function is `tse_init`, not an unidentified scheduler primitive. Its
diagnostic arguments reference `./tse_init.cpp` at raw `+0xec008` and
`tse_init` at `+0xec84c`; its error strings include
`pTFDHandler->InitTFDMemory FAILED` at `+0xec88c` and
`TSEXX init FAILED!` at `+0xec8b0`. Its success path has only three calls:
a global enable-byte setter, the `InitTFDMemory` virtual call, and
`tse_init_data`. Two additional calls are fatal-log paths. The 61-marker trace
assigns them as follows:

```
marker  raw offset  pristine bytes  original target / meaning
57      0x0104a0    c9 27 c6 0e    0x8b189f24, enable-byte setter
58      0x0104b8    09 f8 40 00    jalr v0, InitTFDMemory
59      0x0104c8    a4 3a c4 0e    0x8b10ea90, tse_init_data
60      0x010518    52 42 c5 0e    0x8b150948, failure log
61      0x010568    52 42 c5 0e    0x8b150948, invalid-input log
```

Interpretation is branch-sensitive. Marker 57 should be followed by 58.
Marker 58 without 59 or 60 means `InitTFDMemory` did not return. Marker 59
without marker 39 means `tse_init_data` did not return. Marker 60 or 61 means
`tse_init` selected an error path; marker 39 then shows whether the logger and
function returned. All 366 guarded words match `4380f1b3...`, and the five new
trampolines have been disassembled after applying the patch in memory.

The corresponding 61-marker DDR3 bench image is
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (865,817 bytes), SHA-256:

```
4577774aa219fdaac508556e74fa629aa18f918f9dd5eca97dcf96118febb6e0
```

That image's first hardware run diverged before `tse_init`:

```
H713 MIPS: handshake trace 0 0 0 0 0 0 0 0 0 10 11 12 13 14 15 0 17 18 19 20 21 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
H713 MIPS: readiness status=0x00000001 witness=0x8baa0000
H713 MIPS: CPU_COMM magic=deadbeef/deadbeef ARM=00000005 MIPS=00000000
```

Marker 21 is raw `display.bin+0x535f0`, bytes `d0 68 c5 0e`, calling the
firmware's optimized `memset` at `0x8b15a340`. Its address and length are the
results of the two immediately preceding configuration lookups. Their keys
are `sys:dbg_buf` and `sys:dbg_buf_size` at raw `display.bin+0xebb20` and
`+0xebb2c`; the bytes from `+0xebb20` are
`73 79 73 3a 64 62 67 5f 62 75 66 00 73 79 73 3a 64 62 67 5f 62 75 66 5f
73 69 7a 65 00`. The staged XML supplies address `0x4bd01000` at
`display_cfg.xml+0x497` and size `0x00100000` at `+0x4bc`.

This exposed a concrete ARM/MIPS coherency omission. U-Boot zeroed the config
and TSE windows, loaded their files through the ARM, but did not clean either
window after the filesystem reads. The later firmware-image flush ends at
`0x4b600000`, far below config at `0x4be01000` and TSE at `0x4be41000`.
Consequently the MIPS could observe stale or zero XML/TSE cache lines. The
lookup wrappers ignore their virtual lookup's return status and return an
output stack word unconditionally, so a failed lookup can feed an
uninitialized address or length to `memset`. This accounts for failure
movement between cold boots without assuming that each called subsystem has
an independent defect.

The next build explicitly cleans the complete 256 KiB config window and
complete 1 MiB TSE window after loading them. The 61-marker trace remains
installed. Marker 21's cave additionally records its live `a0` and `a2`
arguments, printed as `sys:dbg_buf` and `sys:dbg_buf_size`; the expected values
are the MIPS uncached alias `0xabd01000` and `0x00100000`.

The corresponding cache-publication DDR3 bench image is
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (869,913 bytes), SHA-256:

```
ee4d61e8d42b76c80a63b91cc88cbf19e3177103a8ff519f9e3e4441bfde6796
```

**The cache-publication build completed the firmware startup chain on
hardware.** Markers 2-59 all fired; marker 15 arrived later in the streamed
output but was present in the final vector. The error-only markers 60-61 did
not fire:

```
0 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26
27 28 29 30 31 32 33 34 35 36 37 38 39 40 41 42 43 44 45 46 47 48 49
50 51 52 53 54 55 56 57 58 59 0 0
```

Marker 1 is the share-address-absent path and is correctly absent because the
published share registers were accepted at marker 2. Markers 60 and 61 are
`tse_init` error logs and are also correctly absent. The live configuration
arguments captured at marker 21 were `sys:dbg_buf=0xabd01000` and
`sys:dbg_buf_size=0x00100000`. The address is correct: it is the MIPS KSEG1
uncached alias of the XML's ARM physical `0x4bd01000`, not a corrupt lookup.
This closes the config/TSE cache-publication failure and proves reset, C
runtime, application construction, `tse_init`, scheduler entry, ThreadX
application entry, share-register discovery, and CPU_COMM entry.

The CPU_COMM flag ownership is also explicit in the exact image. The
`getCurCPUID` function at raw `display.bin+0x227b4` is only:

```
08 00 e0 03    jr    ra
01 00 02 24    addiu v0, zero, 1
```

so this MIPS firmware is CPU 1. `setCPUReady` begins at raw `+0x1a3dc`; it
indexes `pComm + 0x4cdc + cpu_id*4`, making CPU 0's flag `+0x4cdc` and CPU 1's
flag `+0x4ce0`. U-Boot's ARM/MIPS slot assignment and its wait on the second
word are therefore correct.

The remaining boundary is inside the slave-side `InitCommMem` work rather than
the flag mapping. Marker 5 fires by redirecting the call at raw `+0x1b34c`,
bytes `ed 66 c4 0e`, into the first per-CPU communication-object initializer
at `0x8b119bb4`. If that call and the identical second call return,
`InitCommMem` calls `getCurCPUID` at raw `+0x1b35c`, bytes
`ed 89 c4 0e`, and then `setCPUReady(1)` at raw `+0x1b364`, bytes
`f7 68 c4 0e`, with `move a0,v0` (`25 20 40 00`) in the delay slot. The
hardware readback remained CPU 1 flag zero, so the next trace must distinguish
an initializer stall from a later flag change rather than relabeling the two
flag words.

The next exact-image trace has 88 markers. Markers 62-85 cover every non-log
call on the success path through the first initializer at `0x8b119bb4`.
Markers 86-88 cover the second initializer, `getCurCPUID`, and
`setCPUReady(getCurCPUID())`. Its 530 guarded words all match the pristine
`4380f1b3...` image, every new five-word cave disassembles as
marker-store / tail-jump / `nop`, and no patch address is duplicated. The
corresponding DDR3 bench image is
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (874,009 bytes), SHA-256:

```
906184b11b2f33a22896d443472ebc00e473932119ae40d02aeb32ea987e56b4
```

That build's hardware run reached every success marker through marker 88:

```
0 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26
27 28 29 30 31 32 33 34 35 36 37 38 39 40 41 42 43 44 45 46 47 48 49
50 51 52 53 54 55 56 57 58 59 0 0 62 63 64 65 66 67 68 69 70 71 72
73 74 75 76 77 78 79 80 81 82 83 84 85 86 87 88
```

The live debug-buffer values remained correct at `0xabd01000` and
`0x00100000`, while the final CPU 1 flag was still zero. In that trace,
markers 62-85 covered the rest of the first object initializer, marker 86 the
second initializer, marker 87 `getCurCPUID`, and marker 88 entry to
`setCPUReady(1)`. Thus neither object initializer is the boundary:
`setCPUReady` itself was entered but did not leave a READY bit set. The old
trace does not distinguish a pre-store stall from a later flag change.

A deterministic pre-store blocker is the CPU_COMM software-spinlock table.
At raw `display.bin+0x1a56c`, `setCPUReady` calls `comm_SpinLock(3)` with:

```
f1 96 c4 0e    jal   0x8b125bc4
03 00 04 24    addiu a0, zero, 3
```

Only after that returns does it write CPU 1's flag. The first READY store is at
raw `+0x1a588`, bytes `dc 4c 43 ac`; the corresponding unlock call is at
`+0x1a5a4`, bytes `fa 96 c4 0e`. `comm_SpinLock` calls the inner lock routine
at raw `+0x25bcc`, bytes `9d 95 c4 0e`, with mode 2 in its delay slot
(`02 00 05 24`). The inner routine indexes a 12-byte record from the shared
base and waits for its byte 0 type field to equal 2. The relevant comparison at
raw `+0x25170` begins with:

```
00 00 17 92    lbu   s7, 0(s0)
02 00 02 24    addiu v0, zero, 2
```

U-Boot previously zeroed the complete CPU_COMM region and populated only its
CPU count, flags, and magic words. Therefore lock record 3 had type 0, not 2,
and `comm_SpinLock(3)` cannot complete with that input. The refined trace below
will show whether that is the observed boundary as well as removing it.

The exact master-side initialization is present in the same authenticated raw
image at `comm_InitSpinLock`, raw `display.bin+0x24d38`. Its loop derives each
entry as `shared_base + index*12`; the stores at `+0x24e30` through `+0x24e44`
are:

```
01 00 43 a0    sb    v1, 1(v0)       # status = 2
08 00 45 ac    sw    a1, 8(v0)       # thread = 0x000000ff
02 00 40 a0    sb    zero, 2(v0)     # mutex = 0
00 00 43 a0    sb    v1, 0(v0)       # type = 2
04 00 40 ac    sw    zero, 4(v0)     # refcount = 0
03 00 43 a0    sb    v1, 3(v0)       # owner = 2
```

Here `v1=2` is loaded at raw `+0x24e20` (`02 00 03 24`), `a1=0xff` at
`+0x24e24` (`ff 00 05 24`), and the loop bound 12 at `+0x24e2c`
(`0c 00 04 24`). The next build reproduces this exact 12-entry layout before
publishing CPU_COMM magic, instead of bypassing synchronization.

Its trace retains the 88-slot vector but refines the last boundary:

- marker 62: enter `setCPUReady(1)`;
- marker 63: enter `comm_SpinLock(3)`;
- marker 64: lock acquired and READY stores complete; enter unlock;
- marker 65: unlock returned; enter the final log call;
- marker 66: `setCPUReady` returned to `InitCommMem`;
- markers 67-87: retained initializer/get-CPU trace sites;
- marker 88: enter the later `setCPUAppReady` wrapper.

All 530 guarded words match the pristine `4380f1b3...` raw image, no patch
address is duplicated, and the six revised five-word caves disassemble as the
intended uncached marker store followed by a tail jump to the original target.
The next cold-boot run should set CPU 1 READY at marker 64 and may advance it to
the application-ready value after marker 88. This remains a hardware
prediction until the new build is run.

The corresponding CPU_COMM-spinlock DDR3 bench image is
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (874,009 bytes), SHA-256:

```
75dc804d8d963f681ac2f7be545c57c410544daeab2ee8044f9a71786e1540f3
```

**The CPU_COMM-spinlock build passed Gate 1 on hardware.** Markers 62-66 all
fired, proving entry to `setCPUReady(1)`, entry and return of
`comm_SpinLock(3)`, execution of the READY stores, return of the unlock, and
return to `InitCommMem`. The retained markers continued through marker 87.
The final control words were:

```
H713 MIPS: CPU_COMM magic=deadbeef/deadbeef ARM=00000005 MIPS=00000001
H713 MIPS: firmware readiness proven by MIPS READY
```

This validates the reconstructed spinlock layout and closes the CPU_COMM READY
failure. Marker 88 was still zero in the final vector, but that sample does not
establish an application-ready failure: `h713_mips_wait_ready()` exits its poll
loop immediately when MIPS flag bit 0 appears, then prints the trace. The
marker-88 call and MIPS flag bit 2 occur later in the same application thread.

While that one MIPS instance is still running, its later state can be checked
without violating the one-launch-per-power-cycle rule:

```
md.l 0x4e304cdc 2; md.l 0x4e34015c 1
```

The first pair is the ARM and MIPS CPU flags; the second read is trace slot 87,
where marker 88 stores `0x00000058`. An eventual MIPS flag `0x00000005` and
marker slot `0x00000058` prove application-ready. These are read-only
observations, not a second MIPS launch.

The delayed read remained at MIPS flag `0x00000001` and marker-88 slot zero:

```
4e304cdc: 00000005 00000001
4e34015c: 00000000
```

READY is therefore stable, but the application thread does not reach
`setCPUAppReady`. The exact post-`InitCommMem` path in the application function
contains only five calls before the marker-88 call:

```
marker  raw offset  pristine bytes  original target
67      0x052ec8    9d 71 c5 0e    0x8b15c674
68      0x052ed0    6e 2b c4 0e    0x8b10adb8
69      0x052ed8    9d 71 c5 0e    0x8b15c674
70      0x052ee4    61 21 c5 0e    0x8b148584
71      0x052eec    32 21 c5 0e    0x8b1484c8
88      0x052ef4    2c 91 c4 0e    0x8b1244b0, setCPUAppReady wrapper
```

The second call is `hal_adapter_init`: its success log passes the name at raw
`display.bin+0xeb61c` (`68 61 6c 5f 61 64 61 70 74 65 72 5f 69 6e 69 74 00`)
and source filename at `+0xeb630`
(`2e 2f 68 61 6c 5f 61 64 61 70 74 65 72 2e 63 70 70 00`). It walks nine
groups of callback objects and repeatedly calls the helper at raw `+0x24918`.
That helper constructs a communication request and submits it at raw
`+0x2486c`, bytes `55 89 c4 0e`, to `0x8b122554`. A request that expects an
ARM-side CPU_COMM consumer is now a leading candidate, because U-Boot
publishes the shared transport and ARM-ready flags but does not service its
message queues. This is a candidate, not yet a hardware-localized conclusion.

The next trace repurposes the already-proven markers 67-87:

- markers 67-71 cover the five post-`InitCommMem` calls above;
- markers 72-80 cover each registration group in `hal_adapter_init`;
- markers 81-82 cover its final registration and return log;
- trace slots 90-92 count registration-helper entries and retain the latest
  object and callback pointers;
- markers 84-86 cover formatting, request construction, and the request call;
- marker 87 covers the final registration lock;
- marker 88 remains the application-ready wrapper.

The repeated-helper trampoline is eight instructions and increments an
uncached counter rather than merely storing a constant marker. Together, the
last outer-group marker, call count, object/callback pointers, and marker 86
will distinguish an unserviced request from a stall before or after
`hal_adapter_init`.

For this diagnostic only, `h713_mips_wait_ready()` continues streaming after
MIPS READY until either application-ready bit 2 appears or the existing
four-second display-readiness window expires. `mips-test` retains its original
READY-only exit behavior. The trace reports application readiness separately
without turning the already-proven READY result into a failure.

All 533 guarded words match the pristine `4380f1b3...` raw image, no address is
duplicated, and every replacement cave—including the eight-instruction
counter/capture cave—has been disassembled after applying the patch in memory.
The corresponding post-READY/hal-registration DDR3 bench image is
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (874,009 bytes), SHA-256:

```
612dad5b4d4c9ea04065dafff383807fd0fec6c56c0288b2f954cc825ec73043
```

**The post-READY trace localized the next boundary to the first registration
request.** MIPS READY remained proven (`ARM=5`, `MIPS=1`), and the post-init
markers reached `hal_adapter_init` at marker 68. Its first registration group
fired marker 72, the repeated helper count reached one, and markers 84-86
showed formatting, request construction, and entry to the request call. No
later registration group or application-ready marker fired:

```
... 62 63 64 65 66 67 68 0 0 0 72 ... 84 85 86 0 0
hal registrations=1 object=0x8b22e890 callback=0x8b109d20
CPU_COMM magic=deadbeef/deadbeef ARM=00000005 MIPS=00000001
```

The marker-86 site is raw `display.bin+0x2486c`, bytes `55 89 c4 0e`,
calling the request routine at `0x8b122554`. That routine's first non-log call
is at raw `+0x225dc`, bytes `7c 71 c4 0e`, and enters
`0x8b11c5f0`. The next calls are at `+0x22614`, bytes `82 73 c4 0e`, and
`+0x22658`, bytes `8d 73 c4 0e`. Since the old trace only marked entry to the
outer request, the hardware result by itself does not distinguish those three
inner stages.

Static analysis of the exact image exposes another deterministic master-side
initialization omission before an ARM message consumer is relevant.
`0x8b11c5f0` reads the shared call-entry count at raw `+0x1c694`, bytes
`c4 75 23 8e`, and bounds it to 1224 at `+0x1c698`, bytes
`c8 04 63 28`. After taking software spinlock 2 at `+0x1c7a8`, bytes
`f1 96 c4 0e 02 00 04 24`, it tests a per-entry word against `-1`:

```
0x1c7f0: c4 75 97 8e    lw    s7, 0x75c4(s4)
0x1c7f4: ff ff 05 24    addiu a1, zero, -1
0x1c7f8: 2a 00 e5 16    bne   s7, a1, failure
0x1c800: c8 75 84 24    addiu a0, a0, 0x75c8
0x1c804: 60 00 06 24    addiu a2, zero, 0x60
```

The computed entry address begins at `shared+0x75c8`, has stride `0x60`,
and the tested word is entry offset `+0x5c`. U-Boot had zeroed every such
field, so the first insertion could not observe the required free-entry
sentinel.

The exact ARM-master initializer in the same firmware confirms the complete
layout. At raw `+0x1ae4c..+0x1ae58`, bytes
`01 00 06 3c c0 75 c4 27 08 cb c6 34 ad f4 c6 0e`, it clears
`shared+0x75c0` for `0x1cb08` bytes. It then zeroes the count and version and
constructs the sentinel loop:

```
0x1ae60: 02 00 04 3c    lui   a0, 2
0x1ae64: 24 41 84 24    addiu a0, a0, 0x4124
0x1ae68: c4 75 c0 af    sw    zero, 0x75c4(fp)
0x1ae6c: 24 76 c2 27    addiu v0, fp, 0x7624
0x1ae70: 21 20 c4 03    addu  a0, fp, a0
0x1ae74: c0 75 c0 af    sw    zero, 0x75c0(fp)
0x1ae78: ff ff 05 24    addiu a1, zero, -1
0x1ae7c: 00 00 45 ac    sw    a1, 0(v0)
0x1ae80: 60 00 42 24    addiu v0, v0, 0x60
0x1ae84: fe ff 82 54    bnel  a0, v0, 0x1ae80
0x1ae88: 00 00 45 ac    sw    a1, 0(v0)
```

The loop writes `0xffffffff` from `shared+0x7624` through
`shared+0x240c4`, exactly 1224 `+0x5c` fields. The rejected CPU_COMM Linux
patch agrees with these dimensions, but it is corroboration only; the bytes
above from authenticated `display.bin` are the source of truth.

The next build reproduces that exact call-table initialization before
publishing the magic words. It also repurposes markers 73-77:

- 73: enter the shared call-table insertion at raw `+0x225dc`;
- 76: enter its `comm_SpinLock(2)` call at raw `+0x1c7a8`;
- 77: the entry was copied and counted; enter `comm_SpinUnlock(2)` at raw
  `+0x1c838`, pristine bytes `fa 96 c4 0e`;
- 74: insertion returned; enter result lookup at raw `+0x22614`;
- 75: the result pointer was absent; enter the alternate cleanup/removal call
  at raw `+0x22658`.

Markers 78-82 retain later registration groups and the return path. All 533
guarded words match the pristine `4380f1b3...` image, no address is duplicated,
and the five replacement caves disassemble to the intended uncached marker
store and original tail call.

The corresponding call-table-initialization DDR3 bench image is
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (874,009 bytes), SHA-256:

```
68c8cf7e10d0dc3f275c1d5721e115a75c721feb8275972af928e43846fdf301
```

This defers the missing-ARM-consumer hypothesis. If marker 77 and then marker
74 fire, the deterministic insertion defect is closed; only a later boundary
can establish whether the request actually requires an ARM-side responder.
The trace summary also prints the live call-table version, count, and entry
zero's `+0x5c` link field.

**The call-table build passed complete application readiness on hardware.**
The first registration traversed every new inner marker: 73 entered the table
insertion, 76 entered spinlock 2, 77 proved the entry was copied and counted,
and 74 proved insertion returned into result lookup. Marker 75's alternate
cleanup/removal path also fired at least once during the complete registration
sequence, but it did not prevent progress. All retained later registration and
return markers through 82 fired, followed by marker 88 at `setCPUAppReady`:

```
... 67 68 69 70 71 72 73 74 75 76 77 78 79 80 81 82 0 84 85 86 0 88
hal registrations=82 object=0x8b22d030 callback=0x8b10ac98
call table version=164 count=82 first-next=0xffffffff
CPU_COMM magic=deadbeef/deadbeef ARM=00000005 MIPS=00000005
firmware readiness proven by MIPS READY
application readiness proven
```

The table accounting is exact: each successful insertion increments the
version word twice. The first sequence is raw
`display.bin+0x1c7b4/+0x1c7c4/+0x1c7cc`, bytes
`c0 75 25 8e` / `01 00 a5 24` / `c0 75 25 ae`; the second is
`+0x1c828/+0x1c830/+0x1c834`, bytes
`c0 75 22 8e` / `01 00 42 24` / `c0 75 22 ae`. Thus version 164 is
precisely twice the 82-entry count. The first entry's restored
`0xffffffff` link confirms the sentinel invariant after use. This closes the
call-table defect and disproves an ARM-side request consumer as a prerequisite
for these startup registrations.

Gate 1 first passed with the instrumented image: the authenticated firmware
executed, initialized CPU_COMM, completed all 82 HAL registrations, set MIPS
READY and application-ready, and left the ARM console responsive through the
four-second trace window.

The lower-risk confirmation also passed on hardware. Ordinary
`h713_disp mips-test 0x33` applied none of the 533 trace patches and reported:

```
CPU_COMM magic=deadbeef/deadbeef ARM=00000005 MIPS=00000005
firmware readiness proven by MIPS READY
application readiness proven
```

This run still used the separately guarded HDCP timeout-bound override, printed
as `HDCP key-load wait defeated`; "no trace patches" does not mean the loaded
image remained byte-for-byte pristine after authentication. It does prove that
the startup trampolines were not a condition of success. Gate 1 is therefore
fully passed.

The corresponding uninstrumented-application-readiness DDR3 bench image is
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (874,009 bytes), SHA-256:

```
4794550b6fe38a92a7738e283c49945b95ac5bb673fc0e0eab6ec51e4efbeff0
```

#### Gate 2 — distinguish a MIPS fault from a board-level power cut

The exact firmware provides a natural heartbeat. Its ThreadX tick function
loads, increments, and stores the word at MIPS `0x8b252cc0`:

```
display.bin+0x4b74: 25 8b 02 3c    lui   v0, 0x8b25
display.bin+0x4b78: c0 2c 53 8c    lw    s3, 0x2cc0(v0)
display.bin+0x4b7c: 01 00 73 26    addiu s3, s3, 1
display.bin+0x4b80: c0 2c 53 ac    sw    s3, 0x2cc0(v0)
```

The live exception vectors are also identified rather than assumed. Startup
sets EBase to `0x8b101000` at raw `+0xb11ac..+0xb11b4`, bytes
`10 8b 08 3c 00 10 08 25 01 78 88 40`. Therefore the cache-error and
general-exception vector words are raw `+0x1100`,
`79 6f c5 0a` (`j 0x8b15bde4`), and raw `+0x1180`,
`4a 6f c5 0a` (`j 0x8b15bd28`). The general handler disables interrupts at
raw `+0x5bd34`, bytes `00 60 62 41 c0 00 00 00`, calls the register saver at
`+0x5bd3c`, bytes `f6 6e c5 0e`, and ultimately loops forever at
`+0x5bddc`, bytes `ff ff 00 10 00 00 00 00`. The saver itself reads CP0
`Status`, `Cause`, `EPC`, and `BadVAddr` at raw
`+0x5bc54/+0x5bc5c/+0x5bc64/+0x5bc6c`, bytes respectively
`00 60 1b 40`, `00 68 1b 40`, `00 70 1b 40`, and `00 40 1b 40`.

`h713_disp mips-stability 0x33` now installs 34 guarded words after the
SHA-256 identity check. The tick instruction at raw `+0x4b7c` is redirected to
the zero cave at raw `+0x300`, whose bytes are:

```
01 00 73 26 34 ae 1a 3c 00 10 53 af e1 12 c4 0a c0 2c 53 ac
```

That cave performs the displaced increment, writes the new tick through the
uncached MIPS alias `0xae341000` (ARM `0x4e341000`), preserves the original
tick store, and resumes at raw `+0x4b84`.

The general and cache vector words are redirected from
`4a 6f c5 0a` / `79 6f c5 0a` to `c8 00 c4 0a` / `d8 00 c4 0a`,
respectively. Their zero caves at raw `+0x320` and `+0x360` save CP0 state to
the same uncached record, store exception type 1 or 2 last, then jump to the
original fatal handler. The cache path records CP0 `ErrorEPC` in the EPC field.
No normal interrupt vector is changed.

After both CPU_COMM ready bits appear, U-Boot samples the heartbeat, exception
record, core status, and MIPS flags once per second for 60 seconds. It does not
arm or pet a watchdog. If an exception appears, it immediately prints
`Status`, `Cause`, `EPC`/`ErrorEPC`, and `BadVAddr`. If the heartbeat stops
while the ARM remains responsive, it reports a MIPS stall. If the board loses
power while the last UART samples still show an advancing heartbeat and no
exception, the next evidence must come from reset-cause/PMIC/electrical
investigation rather than calling the silence a MIPS panic.

Acceptance is no exception marker, a continuing heartbeat, a responsive U-Boot
console, and no uncommanded shutdown for 60 seconds on three cold boots.

The corresponding Gate-2 DDR3 bench image is
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (874,009 bytes), SHA-256:

```
b097cbe2bd314003bf6991396253ac22f11f779b7d3809e680a2e7037f4ad51c
```

**The first Gate-2 stability run passed on hardware.** Starting at tick 210,
all 60 one-second samples advanced by 1005--1008 ticks. CPU status stayed one,
the MIPS CPU_COMM flags stayed `0x00000005`, and the exception type stayed
zero. The final tick was 60665, U-Boot remained responsive, and the board did
not shut down during the window. Two more cold-boot passes remain before the
three-run acceptance criterion is complete, but this run establishes that a
running, application-ready MIPS is not inherently causing the earlier
uncommanded shutdown.

#### Gate 3 — identify the live timing path

Only after Gate 1 works, add two one-shot probes to the same diagnostic run:

1. mark entry to `load_panel_timing` at raw `display.bin+0x2a6ec`
   (`98 ff bd 27`), reached through the `CrtcDb` call at `+0x27ea0`;
2. trace stores that target TCON `0x05880020` and `0x05880024`, recording the
   value and caller/return address before allowing the original store.

The entry marker answers whether the XML-aware loader is live. The write trace
answers which later function wins. Patching the dead `_LoadTFDPanelTiming`
selector again cannot answer either question.

Once the final writer is known, correct its input structure or database
selection rather than overwriting the registers after the fact. The expected
panel result is:

```
0x05880020 = 02f80550    1360x760 total
0x05880024 = 02d00500    1280x720 active
```

The mixer/DE value `0x02e4059f` remains an internal 1440x741 processing size,
not the target TCON total.

#### Gate 4 — return to the physical panel

With MIPS READY, no exception/shutdown, and stable 720p TCON timing, test the
physical output:

1. assert board-B PF6 and verify the panel VDD rail at the connector;
2. with PF6 and PH16 correct, use the internal TCON color source after latching
   the 720p timing;
3. compare the recovery and stock LVDS lane/mapping, single-port, DCLK
   polarity, color-depth, drive-current, and PHY registers;
4. trace and validate the post-INI PWM5 route while leaving PB5 asserted;
5. only if those are correct, seek evidence for any PH10/PH11/PH12/PH15
   panel-side transaction before attempting to replay it.

This orders the work so a dark panel cannot be used as the sole verdict on
MIPS, scanout, signaling, and illumination at the same time. Re-checking the
other three `0xfe` timing-table sites can wait until the project-0x33 MIPS path
passes these gates.

The live project-0x33 dump now identifies the scanout buffer without probing
the PCB. Its selected DE block 5 contains these exact `LogoRegData.bin`
records:

```
file offset  bytes                                      meaning
0x32e4       50 01 60 05 ff 04 cf 02 ff ff ff ff 04... AFBD+0x10 = 02cf04ff
0x3344       70 01 60 05 00 14 00 00 ff ff ff ff 04... AFBD+0x30 = 00001400
0x3354       74 01 60 05 00 14 d0 02 ff ff ff ff 04... AFBD+0x34 = 02d01400
0x3364       78 01 60 05 00 00 10 6c ff ff ff ff 04... AFBD+0x38 = 6c100000
```

The corresponding live reads were `AFBD+0x10=0x02cf04ff`,
`AFBD+0x30=0x00001400`, `AFBD+0x34=0x02d01400`, and
`AFBD+0x38=0x6c100000`. Thus the selected OSD is 1280x720, four bytes per
pixel, stride `0x1400`, at ARM physical `0x6c100000`; the complete buffer is
`0x384000` bytes. Manual writes to its first and last bands read back
correctly, but that run was not watched at the panel and did not flush the ARM
data cache, so it is not a visible-scanout result.

The stock U-Boot image also contains its `bootlogo.bmp` lookup text at raw
offset `0x60e5c`, bytes
`62 6f 6f 74 6c 6f 67 6f 2e 62 6d 70`. Our fast-logo replay applies the
register records but does not load logo pixels. A new
`h713_disp panel-test 0x33` closes that gap deterministically: it fills and
flushes a moving ARGB8888 color-bar pattern at `0x6c100000`, completes the
authenticated MIPS/CPU_COMM launch, animates for five seconds with the
firmware-selected timing, then writes and latches project 0x33 timing block
6's 1360x760-total/1280x720-active values and animates for another 15 seconds.
That first image intentionally did not change panel GPIOs or PWM, so its
scanout/timing result remained separate from panel power and backlight.

The corresponding pixel/timing-only panel-test DDR3 bench image is
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (874,009 bytes), SHA-256:

```
8aafab3f830aa58890c0ee42d1099837244f213625332ef41a3371532c07b36a
```

**The first panel-test hardware run produced no visible change in either
phase.** It nevertheless completed MIPS READY and application-ready
(`ARM=5`, `MIPS=5`), published and cache-cleaned all 21 moving patterns, and
read back the requested phase-2 TCON values:

```
00000004 02f80550 02d00500 00140028 80000014 80010003
```

Missing framebuffer contents and the 1080p-versus-720p TCON mismatch are
therefore not sufficient explanations for the dark panel. This does **not**
prove that AFBD fetched the buffer or that LVDS pins carried the changing
pixels; neither has a software liveness counter.

### Stock panel-power sequence recovered

**Board correction, 2026-07-30:** the earlier analysis in this section mixed
the board-B MIPS artifacts with the older board-A TOC1 DT. The board-B runtime
TOC1 DT is a separate item in the eMMC dump at TOC1 offset `0x11b400`,
SHA-256 `3902567a079720921e226c9176877f49916c6bdabfb6d82885e65d9f0a7d58b0`.
(An earlier revision of this document recorded `06e5279c...` here; that hash is
wrong. All three board-B eMMC captures yield the value above at that exact
offset and size, and both byte-level facts quoted below — `panel_power_en` at
DTB `+0x9f64` and `panel_gpio_0` at `+0x9f9c` — match it.)
It lists **PF6**, not PH19, as `panel_power_en`; `panel_gpio_0` remains PH16.
Both are active-high with pull-down flags (`0x20` is `GPIO_PULL_DOWN`;
polarity bit zero is `GPIO_ACTIVE_HIGH`):

```
panel_power_en = <0x2c 0x05 0x06 0x20>;
panel_gpio_0   = <0x2c 0x07 0x10 0x20>;
```

The exact board-B DTB property records begin at DTB offset `0x9f58`. The
`panel_power_en` value is at `+0x9f64`, bytes
`00 00 00 2c 00 00 00 05 00 00 00 06 00 00 00 20`; the
`panel_gpio_0` value is at `+0x9f9c`, bytes
`00 00 00 2c 00 00 00 07 00 00 00 10 00 00 00 20`.
In the complete eMMC dump those values are at `0x0d25364` and `0x0d2539c`.

The matching compiled property references are present in the board-B stock
U-Boot `22c9afa98503d4ce0b2b929cf8109af034d841560fbd11baf4ad851197134440`.
`panel_power_en\0` begins at raw `+0x6200b`, bytes
`70 61 6e 65 6c 5f 70 6f 77 65 72 5f 65 6e 00`, and its
little-endian pointer appears at raw `+0x23be0`, bytes `0b 20 06 4a`.
The `panel_gpio_%d` format begins at raw `+0x62038` and its pointer appears at
raw `+0x23c60`, bytes `38 20 06 4a`.

The fastlogo state dispatch is a Thumb `tbb` at raw `+0x22886`, bytes
`df e8 02 f0`; its five-entry table at `+0x2288a` is
`1b 03 0b 0f 0f`. State 0 applies every LogoRegData group and loads the delay
at configuration offset `+0x88` at raw `+0x22902`, bytes
`02 9b d3 f8 88 30 c8 e7`. The extracted DT supplies that
`panel_poweron_delay1` as `0x226`, or 550 ms. State 1 calls the object's
panel-power method with argument one at raw `+0x22890`, bytes
`43 69 01 21 98 47`, then loads configuration offset `+0x84` at
`+0x22896`, bytes `02 9b d3 f8 84 30 07 93`; the DT supplies
`panel_poweron_delay0=0x14`, or 20 ms.

The power method itself begins at raw `+0x224e4`, bytes
`2d e9 f0 45`. For power-on it:

1. applies the `panel_power_en` descriptor from object offset `+0x48`;
2. walks the four possible `panel_gpio_N` descriptors from object
   `+0x4c..+0x58`, forces each present pin low, and waits 2 ms — the loop
   starts at raw `+0x22528`, bytes
   `a0 46 4f f0 00 0a 58 f8 04 1b`;
3. walks the same descriptors using their configured active value and waits
   5 ms — the second loop starts at raw `+0x22554`, bytes
   `54 f8 04 1b a9 b1 38 22`.

Only `panel_gpio_0` is present in the runtime TOC1 DT. Thus the reconstructed
sequence must drive PF6 high, drive PH16 low for 2 ms then high, wait 5 ms,
then wait 20 ms before the
display-clock/MIPS phase.

The raw literal pair at `+0x22c60` is
`50 01 00 02 22 ff ff 22`, encoding
`0x02000150 <- 0x22ffff22`. The earlier interpretation that this disabled
PH16 and PH19 was wrong. H713 banks are 0x30 bytes apart, making
`0x02000150` **PH_CFG0 for PH0..PH7**; PH16 and PH19 are in PH_CFG2 at
`0x02000158`. The write configures PH0/PH1 and PH6/PH7 as function 2 and
disables PH2..PH5. It does not touch either panel GPIO.

Stock U-Boot's compiled fastlogo code parses `panel_power_en`,
`panel_gpio_%d`, `panel_bl_en`, and the PWM properties. The strings
`lcd_standby`, `spi_cs`, `spi_scl`, and `spi_sda` occur in the extracted stock
DT but have no compiled property-name occurrence in the U-Boot code. Treat the
old claim that stock fastlogo bit-bangs PH10/PH11/PH12 as an unproven
hypothesis, not an established panel-initialization step.

The first stock-panel-power build used PH19 and is now rejected as a
cross-board test. Its brief panel response remains an observation, but it
cannot validate the board-B power rail. That build,
SHA-256 `3cf25e3df12d259bc2a100401db95a983f4a6711326096fa3fd70b05cce97875`,
produced the first physical panel response seen in this investigation: a very
brief flash that looked as though the LCD stopped obscuring the illuminated
backlight. Its exact point in the sequence was not observed. The serial
diagnostic also proved that this was **not yet the intended reset release**:

```
stock GPIO phase complete: PH19 cfg=1 latch=1, PH16 cfg=1 latch=0
post-stock PH mux:          PH19 cfg=1 latch=1, PH16 cfg=1 latch=0
```

The board-A PH19 pin was asserted, while PH16 remained actively driven low for the
rest of the run. The cause is the legacy GPIO compatibility API in this
DM_GPIO build. `gpio_direction_output()` constructs a temporary descriptor
with output flags, but the later `gpio_set_value()` constructs a new descriptor
without those retained flags. The sunxi driver implements `.set_flags` rather
than `.set_value`, so that later high request does not enter its output path.
The PH16 low-to-high pulse was therefore lost in software, exactly as the data
latch reported.

The first corrected `h713_disp panel-test 0x33` still used the wrong board-A
power pin: it wrote PH19 through `0x02000160`. The board-B correction instead
sets PF6 through PF data register `0x02000100`, then pulses PH16 through
`0x02000160`. It still leaves PB5 high because this U-Boot enables the shared
fan/backlight rail in `board_init`, and dropping it for sequence parity would
defeat the cooling interlock.

The corresponding corrected stock-panel-power DDR3 bench image is
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (874,009 bytes), SHA-256:

```
c4a7ca24b83ce782f05e5547e7a38db2fdb4494cd617afac58f41b6de6a95dbb
```

The corrected-GPIO hardware run proved the requested state survived the whole
sequence:

```
stock GPIO phase complete: PH19 cfg=1 latch=1, PH16 cfg=1 latch=1,
                           PH_DAT=00090000
post-stock PH mux:          PH19 cfg=1 latch=1, PH16 cfg=1 latch=1
CPU_COMM:                   ARM=00000005 MIPS=00000005
```

There was no visible change in either pattern/timing phase. This result says
nothing about panel power because PH19 is not the board-B power pin. The
earlier flash occurred only in the defective build that left PH16 low; treat
it as a power/reset transient, not as proof of valid pixels.

### Firmware hardware-blue-screen discriminator

Static analysis closes the remaining framebuffer-format question. The stock
U-Boot BMP blitter at raw `u-boot_real2.bin+0x24014`, bytes
`96 78 03 32 12 f8 03 3c 43 f0 7f 43 43 ea 06 43`
followed by
`12 f8 02 6c 43 ea 06 23 41 f8 04 3b`, reads three source bytes,
sets the high byte to `0xff`, and stores one 32-bit destination pixel. Thus
the stock 24-bit BMP path produces the same `0xffRRGGBB`-class words used by
`panel-test`; an unexpected compressed framebuffer format does not explain
the negative result.

Stock U-Boot also does not perform a hidden hardware commit when it supplies
the framebuffer. Its method at raw `+0x2481c`, beginning
`f0 b5 0e 46 85 b0 15 46`, enumerates the parsed 16-byte register records,
compares each address against the first address plus `0x178`, and stores the
surface pointer into that record's value field (`45 60` at raw `+0x24868`).
For DE block 5 that is the already identified `0x05600178` record whose file
bytes contain `00 00 10 6c`. The ordinary LogoRegData replay is the operation
that later writes it to hardware.

The MIPS firmware contains a better probe-free split. Its
`EnableHWBlueScreenPanel` implementation begins at raw `display.bin+0x16600`.
At `+0x16610..+0x1664c`, bytes
`1c ba 02 3c b8 00 43 8c ... 84 31 a3 7c ...`
and
`04 10 83 7c ... c4 28 83 7c`, it read-modify-writes MIPS panel register
`0xba1c00b8`, setting bit 6 and both three-bit fields to seven. Under the
firmware's MMIO mapping this is ARM `0x051c00b8`. Its color setter at raw
`+0x17a68` begins
`d8 ff bd 27 1c ba 02 3c` and packs three 10-bit components into
`0xba1c00b0` and `0xba1c00b4` (ARM `0x051c00b0/+0xb4`).

`panel-test` reproduces those exact hardware-blue-screen writes only after MIPS
application readiness. It cycles four internal colors for three seconds each
and restores all three saved registers exactly. Once the TCON is at the
panel's 720p timing, this removes AFBD, DE, the framebuffer address, cache
coherency, and pixel format from the test:

- visible hardware colors mean LVDS and the physical panel path work, leaving
  the OSD/DE path as the fault;
- no hardware colors **at the panel timing** put the fault downstream of DE,
  in panel/LVDS signaling or panel initialization/power.

The corresponding DDR3 bench image is
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (874,009 bytes), SHA-256:

```
0b0e2374738c7f9d7259b8e4bebca75941be77043498e3bca4e26f3cbcc9816a
```

**The first hardware-blue-screen run accepted every register write but
produced no visible change.** The baseline and four readbacks were:

```
blue-screen baseline: 00000200 00000000 00000038
hardware colour 1/4:  3ff00000 3ff00000 0000007f
hardware colour 2/4:  000003ff 000003ff 0000007f
hardware colour 3/4:  000ffc00 000ffc00 0000007f
hardware colour 4/4:  3fffffff 3fffffff 0000007f
restored:             00000200 00000000 00000038
```

MIPS READY and application-ready were both still proven. The test then latched
`02f80550 02d00500` and ran the moving framebuffer for 15 seconds, also
without a visible response.

That run does **not** yet prove the failure is downstream of DE. The internal
color phase preceded the 720p latch and therefore ran while the firmware's
1920x1080-active timing was still selected. A 1280x720 panel is not expected to
display that signal. The next build moves the internal colors after the
1360x760-total/1280x720-active latch before using their visibility as an LVDS
discriminator.

The same run added a panel-power/readiness phase while internal white was
selected. It left PB5—the shared fan/backlight enable—asserted throughout,
but it still used the board-A PH19 assignment:

1. drives PB4, the stock `panel_pwm_ch=2` input, statically low and high for
   three seconds each (the unambiguous PWM duty extremes);
2. holds PH16 reset/enable low for three seconds, then high for three seconds;
3. asserts PH16 low, toggles PH19 for three seconds, restores it, and replays
   the stock 2 ms PH16 release.

Each step printed the PB4/PB5/PH16/PH19 mux and data-latch readback. The PF6
correction above invalidates PH19 as a panel-power discriminator.

The corresponding 720p/power-control DDR3 bench image is
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (878,105 bytes), SHA-256:

```
8fa2c6e7c037f746388b04b0426be0359c01ce239a29ede72571698b0a388364
```

**The 720p/board-A-power-control run produced no visible response in any
phase.**
MIPS reached READY and application-ready, the TCON read back
`02f80550 02d00500`, and the internal-color registers read back each requested
value. PB4 then read back low and high, PH16 read back low and high, and PH19
read back low for three seconds before the stock power/reset release restored
both PH19 and PH16 high. PB5 remained configured as an asserted output
throughout. The operator saw no color, brightness, flash, opacity, or other
output change.

This moves the pixel-source boundary downstream of AFBD/DE, but it does not
move the panel-power boundary: PH19 is not the board-B `panel_power_en`.
The next useful evidence is the corrected PF6 run:

1. assert PF6 and measure the panel's DC supply at the connector;
2. if the supply falls and returns, check one LVDS clock pair for continuous
   differential activity during the 720p internal-color phase;
3. only if both power and clock are present should the investigation move to
   lane mapping/polarity, panel initialization, or connector pinout.

No additional framebuffer pattern can distinguish those cases.

**A Saleae Logic Pro 8 analog capture now proves that at least one physical
LVDS pair is active.** Channels 0 and 1 were clipped to the suspected pair,
with a shared board ground, during `h713_disp panel-test 0x33`. The retained
15.509 seconds cover the final moving-OSD phase after the 720p timing latch.
Across 48,468 exported samples:

```
channel 0 mean = 1.1831 V
channel 1 mean = 1.2765 V
pair common-mode mean = 1.2298 V
channel correlation = -0.7864
```

Both conductors moved throughout every one-second pattern interval and were
strongly complementary. That is an electrically driven LVDS pair, not two
inactive GPIOs. Its nearly invariant per-second distribution is consistent
with the operator's identification as the clock pair, but the capture cannot
prove that classification: the Logic Pro 8 analog front end is only 5 MHz,
and its available single-ended digital thresholds do not sit at the pair's
approximately 1.23 V common-mode. A high-speed digital capture consequently
reported both conductors low and is discarded for waveform/frequency analysis.

The third Saleae channel in this run was attached to the wrong connector pin
and remained near zero; it is explicitly **not** panel-power evidence. The
native capture is preserved locally at
`local/mips-display/h713-lvds-ch0-ch1-active-20260730.sal`.

A second, lower-rate capture retained the complete 73.186-second cold-boot
run. Channels 0 and 1 rose from approximately zero to an active differential
state at 8.1 seconds and remained driven through the prompt. At 43.83 seconds
their sampled distribution changed sharply from one stable differential state
to complementary motion around 1.23 V common-mode, proving that a later test
phase changes the pair electrically. Without a simultaneous UART/GPIO marker,
this capture does not assign that transition to a specific printed phase.

The repositioned third channel began near 0.64 V and slowly rose to
approximately 1.06 V; it never behaved as a switched 3.3 V supply and did not
drop during the run. It is therefore still an unidentified connector signal,
not panel-VDD evidence. This full capture is preserved locally as
`local/mips-display/h713-lvds-full-run-ch2-unknown-20260730.sal`.

This result rules out a globally silent LVDS PHY and cable-side absence of all
lane drive. The next discriminator is the corrected PF6 panel-power run,
followed by the panel-side PH16/reset level. If both controls respond correctly,
attention moves to lane/clock identification, mapping/polarity, and any
panel-specific initialization rather than AFBD/DE.

### Board-B `panel_config.ini` is another stock input

The board-B eMMC dump also contains the file that its stock U-Boot explicitly
tries to load. `Reserve0_a` starts at eMMC byte `0xa7880000` and is FAT16.
Its `/panel_config.ini` is 2513 bytes, SHA-256
`7bffff88a8319c3cdd1a2cdba0fc26df9fdac16c01aedaea7cc20353bc618cc3`.
The corresponding stock U-Boot strings are at raw offsets `0x61e7a..0x61f47`:
`load file %s fail, try load panel_config.ini!`, `panel_config.ini`,
`/oem`, `Reserve0`, and `load file panel_config.ini fail!`.

This file does not override the panel GPIO names, so it does not weaken the
PF6 conclusion. It does override several display settings after the DT is
parsed:

```
PanelDualPort = 0
Mapping = 0
ColorDepth = 8
PanelInvDCLK = 1
PanelHTotal = 1360
PanelVTotal = 760
PanelDCLK = 62000000
pwm_channel = 5
pwm_polarity = 1
pwm_freq = 40000
```

The existing TCON table and the manually latched phase already reproduce the
1360x760 timing. The single-port setting and PWM5 route have not yet been
traced to their final hardware writes. They are the next stock-parity items
after proving that PF6 restores the panel rail; PB4/PWM2 testing came from the
pre-override DT and is not authoritative for board B.

The corrected recovery path now drives board-B PF6 instead of board-A PH19,
and the panel control diagnostic no longer presents PB4 as an authoritative
brightness test. The corresponding DDR3 image is
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (874,009 bytes), SHA-256:

```
4153a1983377eaa2e2edac85982df5aee19eae887b5405506ce2257cf30e88c1
```

### Where the display stands, for a cold start

Hardware is an **LCD panel** (`HY200-1-3-W`, 1280x720) over LVDS. It is known
to work: the stock firmware displays a logo.

Everything needed is on the board and loaded automatically:

```
h713_disp mips-test 0x33       # full launch plus CPU_COMM/app-ready proof
h713_disp mips-trace 0x33      # same launch, streaming startup markers
h713_disp mips-stability 0x33  # same launch, 60s heartbeat/exception test
h713_disp panel-test 0x33      # 720p colors, power controls, then moving OSD
h713_disp auto 0x33            # load from eMMC, run the full sequence
h713_disp test 0x33            # same, plus config patches, timed sampling, log
h713_disp list 0x4e000000      # project -> prologue/timing/DE table
h713_mips log                  # scan the firmware workspace for its own text
```

Verified: artifacts load from `mmc 1:2`, `display.bin` verifies against
`4380f1b3...`, the coprocessor executes (witness overwritten), the replay
follows stock's group order and is now faithful record-for-record, the display
PLL locks, and 54 of 65 dumped registers hold exactly what the tables wrote.
Every "not working" result recorded before 2026-07-29 predates the `0xfe` and
delay-unit fixes, so the replay that produced them was not faithful.

Not working: the panel stays dark. **Do not use `0x05880FE0` as the criterion** —
it is decoded, reads `0x00000002` before the conditional reset and zero after,
and is most likely a fault status where zero means "no fault"; see the section
above.

**Correction (2026-07-31): there is a scan-liveness signal, and it is
`0x05880000`.** Its two halves advance continuously while the raster runs and
read `0x00000000` when it does not, which is exactly the instrument this
investigation lacked for months. Use it, not `0x05880FE0`. The earlier claim
that the block "only decodes `0x00..0x44`" stands for the *upper* page; it does
not mean the decoded window is static.

Ruled out: table selection (`0x16`, `0x33`, `0x34`, `0x35` all tried, with and
without the HDCP override), `source_id` (2 is invalid — the board's own
`display_cfg.xml` already carries 1, and forcing 2 makes the firmware log
`Element name=source_` and get *less* far), and the HDCP key-load wait.

**Each of those was judged on "the panel stayed dark", which was never a
sensitive test.** Table selection especially deserves re-testing, now that
`0x05880024` gives a direct readout of what timing the firmware settles on.

At ERROR level the firmware logs nothing, so by its own account
startup succeeds. Its elog `route='0'` means uart, so raising the level does
not put anything in memory; capturing it properly needs the elog buffer
addresses re-derived for `4380f1b3...`.

## Safety rules

- Keep a known-good FIT available and preserve UART as the recovery path.
- Do not enable `cpu-comm`, `tvtop`, `decd`, or GE2D in the recovery image.
- Do not map or access the MIPS control registers from Linux until their clock
  and power-domain behavior is independently understood.
- Do not mix unrelated GPU, filesystem, WiFi, or DVFS changes into display
  experiments.
- Treat `display.bin` and vendor image extracts as local-only research inputs.
  Record their hashes, but do not embed workstation-specific paths in defconfig.
- Every patch-series edit must pass a fresh `build/build.sh kernel`; cached or
  previously published artifacts are not proof of the current tree.
- A driver must return an error when its hardware does not become ready. Probe
  success and log messages must not conceal a failed reset/clock/firmware step.

## Milestone 0 — preserve evidence and restore a buildable series

Actions:

1. Keep the experimental GE2D patch and reverse-engineering inputs out of the
   active series while they are reviewed.
2. Repair all malformed or stale new-file hunk counts.
3. Remove the absolute `CONFIG_EXTRA_FIRMWARE_DIR` and rootfs dependency on
   `tmp/`.
4. Restore the bench overlay to its known boot-safe state: reserve the firmware
   DRAM, but expose no MIPS control device to Linux.
5. Revert unrelated GPU IRQ and ext4 `norecovery` changes.

Acceptance:

- `build/build.sh kernel` applies every patch from a clean extraction.
- `Image`, both board DTBs, modules, and the bench FIT are published.
- The bench DTB has no enabled MIPS/display device and contains only the
  no-map firmware DRAM reservation.
- No MIPS/display firmware is compiled into the recovery kernel.

## Milestone 1 — verify the recovery kernel on the bench

Boot the Milestone 0 FIT over the existing safe path before writing it to eMMC.

Acceptance on UART:

- U-Boot hands off to Linux and Debian reaches the normal login target.
- Root ext4 mounts normally, without `norecovery`.
- Fan, UART, eMMC, RTC/reboot-mode, and the existing WiFi fixes show no
  regression.
- Save the complete UART log and FIT SHA-256 as the new display-recovery
  baseline.

## Milestone 2 — U-Boot firmware loader

Keep the operation in U-Boot proper while it needs filesystem access and
SHA-256. Do not place the proprietary firmware in SPL or the U-Boot image.
Keep the command manual until firmware readiness has a bounded independent
witness.

Required behavior:

- hold MIPS reset before modifying its DRAM window;
- accept only the known size and SHA-256 of `display.bin`;
- clear the complete factory five-megabyte load window before copying;
- flush ARM caches before releasing the external processor;
- use the recovered physical boot address and staged reset sequence;
- prepare only the proven display clocks, TVTOP routing, and mixer register;
- exclude LVDS, PH pinmux, TVCAP, HDMI, and INCAP;
- return to reset after a bad hash, short read, or unexpected CPU status;
- print reset status separately from firmware readiness.

Acceptance:

- The command is present only in the DDR3 bench U-Boot proper image and absent
  from SPL and the projector defconfig. **Passed on 2026-07-27.**
- A rejected or missing firmware image leaves CPU status zero. **Passed on
  2026-07-27.**
- The known image produces the expected hash and reset transition without
  disrupting UART, USB ACM, or eMMC. **Passed on 2026-07-27.**
- A second observable witness, such as a firmware-owned memory word or bounded
  IPC acknowledgement, proves instruction execution before autoboot is added.
  **Passed on 2026-07-27:** the cache-coherent BSS-clear witness passed on three
  pristine firmware loads.
- The complete recovery kernel reaches userspace with the MIPS running.
  **Passed on 2026-07-27:** the installed minimal display preparation makes the
  live-MIPS handoff safe with Panfrost enabled; DRM and the render node register
  and Debian reports `running` with zero failed units.
- A bounded firmware mailbox/IPC acknowledgement proves higher-level readiness
  before autoboot or Linux clients are added. **Pending.**

## Milestone 2b — Linux post-boot ownership

Enable only the no-map MIPS firmware reservation. Do not instantiate a Linux
MIPS loader, observer, or management driver. Keep CPU_COMM, TVTOP, DECD, GE2D,
and their extra framebuffers disabled.

Acceptance:

- Linux reaches userspace when U-Boot has not started the MIPS. **Passed on
  2026-07-27.**
- Linux reaches userspace with MIPS running and Panfrost transiently
  blacklisted. **Passed on 2026-07-27; diagnostic configuration only.**
- Linux reaches userspace with MIPS running and Panfrost enabled after U-Boot
  applies the minimal display prerequisites. **Passed on 2026-07-27; installed
  U-Boot and unmodified kernel command line.**
- Linux never loads `display.bin`, rewrites the boot vector, or toggles the
  MIPS reset sequence.
- The compiled DT contains no MIPS control-register address and Linux creates
  no MIPS platform or character device. **Passed on 2026-07-27.**
- `dmesg` reports only the no-map firmware reservation, not a MIPS probe.
  **Passed on 2026-07-27.**

## Milestone 3 — CPU_COMM address model

Do not enable CPU_COMM until its address domains are explicit:

- native kernel virtual addresses use `uintptr_t`/pointers and are never stored
  in protocol `u32` fields;
- shared-memory protocol fields contain 32-bit MIPS-visible physical addresses
  or offsets, converted through checked helpers;
- no helper reconstructs a pointer by OR-ing a fixed arm64 VA prefix;
- kernel-only lists use native `struct list_head` or native-width storage;
- shared structures retain the vendor ABI with compile-time layout assertions.

Add host-side KUnit or equivalent tests for FIFO wrap/full/empty behavior,
physical↔virtual conversion bounds, list insertion/removal, and malformed
shared-memory values.

Acceptance:

- The CPU_COMM objects build without pointer-to-int or int-to-pointer warnings.
- The platform driver is present in the linked image and probes exactly once.
- Invalid shared pointers return errors rather than reaching `BUG()`.
- With MIPS running, ARM and MIPS exchange a bounded ping/ack before any
  synchronous display RPC is attempted.

## Milestone 4 — TVTOP and DECD

Enable TVTOP first, then DECD. Keep GE2D disabled. Define resource ownership so
shared display clocks, resets, IRQs, and overlapping register windows have one
clear owner. Child population must propagate errors and be paired with
depopulation.

Acceptance:

- Both drivers can defer and reprobe without leaked PM, IRQ, clock, reset, or
  character-device state.
- No IRQ is requested non-shared by two active devices.
- CPU_COMM ping/ack remains reliable while TVTOP and DECD probe.

## Milestone 5 — GE2D and visible panel path

Review the GE2D patch as a separate feature series. Probe must not issue
synchronous MIPS RPC until CPU_COMM reports ready, and every RPC result must be
checked. Start with framebuffer/IRQ/backlight side effects disabled, then enable
one at a time.

Acceptance:

- GE2D can probe without changing fan/backlight GPIO state unexpectedly.
- Panel initialization, PWM configuration, and framebuffer scanout are separate
  observable steps.
- The LVDS path produces a stable test pattern before compositor or GPU
  integration begins.

## Artifact organization

After Milestone 0 builds:

- discard one-off top-level `fix_*.py`, `patch_editor.py`, `wait.sh`, and saved
  build stdout/stderr;
- move useful vendor extracts, firmware, disassembly, and analysis scripts under
  ignored `local/mips-display/`;
- keep the inactive GE2D patch in a clearly named local research location until
  it passes review and has reproducible provenance.

Nothing under `local/` is published or force-added to Git.
