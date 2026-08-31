# Plan: a CPU_COMM routine client

Written 2026-08-30, for whoever picks this up next (human or model).

The transport is finished and the routine map is known. A guarded userspace
client now exists at `tools/display/cpu-comm-probe.c`; the remaining work is to
recover routine signatures and encode them without producing another invalid
negative.

## Linux client update (2026-08-31)

The client is implemented and hardware-verified. It resolves names from the
live table, rejects ambiguous prefixes, requires `--id` for raw ids, refuses
the confirmed `EnableScreenCover` hazard by resolved id, limits calls to ten
arguments, zeros the result area, and reports elapsed time plus meaningful
`errno` values.

The first Linux calls also corrected the window-getter ABI:

- `GetSource` takes no arguments and returned one value, source `0`.
- `Wce_GetActiveWindow` takes **two ARM physical output addresses**, not a
  leading dummy plus addresses. It returned a first 1920x1080 struct and a
  second, active 1280x720 struct.
- `Wce_GetWindow` takes **three ARM physical output addresses**. It returned
  two 1920x1080 structs and scalar `2`.

The older U-Boot test passed `0` first, so the adapter's first pointer was null
and the address called `p1` actually received its second output. That was enough
to discover 1280x720, but not enough to establish the parameter indexing.
Linux wire capture settled it: the adapter receives a pointer to message
`+0x28` (the component id), and its loads from `+4`, `+8`, `+12` therefore read
the first, second and third values copied to message `+0x2c`.

That capture found and fixed one driver bug as well: the channel-addressing
path zeroed message `+0x34`, which is parameter 3, and `CPUComm_CallEx` also
treated the same payload word as a tgid before copying arguments over it. The
tested fixed module is SHA-256
`60bbddeab6c985607b7feb7e3d2f15d4e98704016ce8773e10a2b52bdb689608`.
All regression calls completed CALL -> ACK -> RETURN -> RETURN_ACK with zero
WARN/BUG/Oops.

## Where things stand

`/dev/cpu_comm` accepts a CALL and completes a full round trip to the MIPS:
CALL -> CALL_ACK -> RETURN -> result, reproducible, ~17-30 ms, zero
WARN/BUG. The driver discovers the firmware channel itself at probe, so no
module parameters are needed.

Prerequisite for every experiment below: the coprocessor must be alive.
`0x0306101c` must read `1`. A normal boot leaves it `0` because U-Boot's
default `preboot` runs `h713_disp auto 0x34 logo`, whose last act is to
quiesce the MIPS. The recipe, which needs no environment change:

```
reboot bootloader          # from Linux, lands at the U-Boot prompt
h713_disp init 0x34        # leaves the firmware running
boot
```

Then `insmod /root/hy310-cpu-comm.ko && insmod /root/cpu-comm-enable.ko`.
The shim is one-shot per boot; re-running it fails with `-ENODEV` because
the OF node stays `OF_POPULATED`. To iterate on the driver without
rebooting, `rmmod hy310_cpu_comm` and re-insmod the driver alone -- it
re-probes against the platform device the shim already created.

## The ioctl ABI

`ioctl(fd, 0xC0087F26, buf)` where `buf` is **168 bytes**. Only three
regions matter; the kernel copies the whole buffer back on success.

| offset | field |
| --- | --- |
| `+40` (0x28) | `u32 comp_id` -- the only field read out of the message area |
| `+64` | params: `params[0]` = count (**max 10**), `params[1..count]` = `u32` args |
| `+120` | results: `result[0]` = count, `result[1..count]` = `u32` values |

Two traps in that layout, both worth encoding in the client rather than in
a comment:

- **Zero the result area before every call.** The kernel only writes it
  when the firmware's returned count is `<= 10` and not `15`
  (`cpu_comm_rpc.c`, "Copy result values"). Any other count leaves the
  buffer untouched, so an uninitialised client reads its own stack and
  reports it as firmware output.
- **`errno` is now meaningful.** It used to be flattened to `EFAULT` for
  every failure. Today `ETIME` (62) means the firmware ACKed the call and
  never sent a RETURN, and `ESRCH` (3) is what you get with the MIPS
  parked. Print the symbolic name; the difference is diagnostic.

## Prerequisite: DONE

`CPUComm_CallEx` used to open with `BUG()` on `!params`, `!result` and
`param_count > 10`, all reachable straight from the ioctl with
caller-supplied data -- a client sending a count of 11 would have taken the
kernel down, and a client is precisely what starts sending varied argument
counts. These now return `-EINVAL`, plus a `param_count < 0` guard that was
never there: `params[0]` is read as a signed `int`, and a negative count
skipped the copy loop but still got truncated into the `u16` at `msg+0x08`,
putting a garbage argument count on the wire.

Verified on hardware:

```
over max            count=11        rc=-1 errno=22 (Invalid argument)
absurd              count=1000000   rc=-1 errno=22 (Invalid argument)
negative            count=-1        rc=-1 errno=22 (Invalid argument)
valid (regression)  count=0         rc=0  ok
survived: no panic
```

Zero WARN/BUG/Oops, and the round trip still passes afterwards. The client
should still validate `0 <= count <= 10` itself, but it is no longer the
only thing between a typo and a panic.

### The standing liability

**About 90 `BUG()` calls remain** in the cpu_comm sources -- roughly 23 in
`cpu_comm_rpc.c`, 21 in `cpu_comm_channel.c`, 20 in `cpu_comm_mem.c`, the
rest spread across `hw`/`dev`/`proto`. Six have been fixed so far and
**every one of them was reached the moment real traffic first touched its
path**:

| where | what it did |
| --- | --- |
| `CPUComm_CallEx` wait | a plain SIGTERM panicked the kernel |
| `ReleaseWaitComm` | deadlocked unkillably on first use (wrong semaphore offset) |
| `command_action` RETURN path | panicked the instant a RETURN first arrived |
| `CPUComm_CallEx` entry (x3) | the above |

Only the ones on the client's immediate path have been audited. The
remainder are not known-good, they are merely unexercised -- in particular
the `Set*`, notify and callback-registration paths, which the client is
about to reach for the first time. **Treat every inherited `BUG()` as a bug
until shown otherwise**, and when a new path is exercised, read its `BUG()`s
first rather than discovering them with the board.

## What the client must do

1. **Resolve routines by name, not by hex.** `/proc/cpu_comm/routines`
   gives `comp_id` and a 32-byte name for every routine the running
   firmware publishes. The client should accept `GetSource`, match it
   case-insensitively against that file (allowing the `THal_Vp_` prefix and
   the `_1_000` suffix to be omitted), and refuse an ambiguous prefix
   rather than picking one. A raw `0x...` id should still be accepted, but
   only behind an explicit flag -- typing a hex constant is how the wrong
   routine gets called.

   Names in that file are truncated to 32 bytes
   (`THal_Vp_Wce_DisablePixel2PixelMo`), so match on prefix, not equality.

2. **Refuse `0x0152f134` in code.** `THal_Vp_EnableScreenCover`, confirmed
   by name from the live table. It wedges CPU_COMM -- afterwards the no-op
   that round-tripped in 1 ms is never accepted again -- and U-Boot's
   `reset` then produces no output at all. **Physical power cycle only.**
   The blacklist belongs in the binary, not in the operator's memory, and
   should be keyed on the resolved id so a name lookup cannot smuggle it
   past.

3. **Bound and report.** The driver already caps the wait at 5 s and
   returns `ETIME`, so the client needs no timeout of its own, but it
   should print elapsed microseconds for every call. Latency is currently
   the only signal distinguishing "firmware did work" from "firmware
   returned immediately".

4. **Default to zero arguments.** The routine table gives names, not
   signatures. Nothing currently known says how many arguments any routine
   takes or what they mean -- see the open question below.

## The open question the client must not paper over

**Argument signatures are unknown.** The table publishes names and ids and
nothing else. For `Get*` routines a zero-argument call is a reasonable
first guess and the result count tells you how many values came back. For
`Set*` routines it is a guess with side effects on a live display pipeline.

The honest way to close this is the firmware, not experimentation: the
adapter for each routine is reachable from the same table, and
`tools/mips/disasm.py` already exists for exactly this kind of question
(base `0x8b100000`, MIPS VA `0x8b1xxxxx` = ARM physical `0x4b1xxxxx`). Read
the argument handling before calling anything that sets state.

Do not infer a signature from a call that returned successfully. A CALL
whose key matches is dispatched regardless of whether the arguments are
sensible.

## Test protocol

This project has already produced one confidently wrong negative, and the
cause is worth restating because the client makes it easy to repeat.

The 2026-08-30 suppression test called `EnableBlackScreen` and friends,
observed no change, and concluded they were inert. The test was invalid:
the logo on screen renders on the **OSD** channel (`0x05600140`), while
those are *video-processor* routines acting on the **video** channel
(`0x05600100`), which was empty in that state. The experiment could not
have detected success.

So, before any call that is supposed to change the picture:

1. **Establish an observable that can show the change.** For video-path
   routines that means DECD actually submitting -- source 0 at
   `0x03000413`, DECD IRQs advancing at ~60/s -- not a static boot logo.
2. **Run a control first.** `GetSource` (`0x24efc7c9`) is read-only and
   should be the first real call ever made: it exercises the argument and
   result path and tells you what the firmware believes is active, with no
   state change. `GetImageBufferAddr` (`0x2f02f7dd`) is the known-good
   no-op already used by the probe.
3. **Change one thing.** Both the geometry work and the RETURN hunt were
   solved by single-variable steps, and both were briefly derailed by
   changing two at once.
4. **Capture registers, not impressions.** A dump before and after is
   evidence; "the panel looked the same" is what made the suppression
   result unsafe.

## Suggested first experiments, in order

| # | call | why |
| --- | --- | --- |
| 1 | `GetSource` | read-only; first real routine ever invoked; validates the result path |
| 2 | `GetImageBufferAddr` | already round-trips; compare its result shape against #1 |
| 3 | `Wce_GetActiveWindow OUT1 OUT2` | typed read-only call; use verified scratch addresses such as `0x4d830000 0x4d830010`; OUT2 is the active `1280x720` window |
| 4 | `GetSignalInfo`, `GetDisplayLatency` | more read-only surface, still free |
| 5 | anything `Set*` | **only after** the disassembly answers signatures, and only with DECD live |

Everything in 1-4 is read-only and safe to run repeatedly.

## Operational hazards

- **`0x0152f134` wedges the SoC.** Power cycle. Blacklisted in the client.
- **After a module Oops, never `reboot`.** The Oops leaves `rmmod` stuck in
  `flush_work` at refcount `-1`, and a clean `reboot` or `reboot
  bootloader` from that state hangs the board with no console and no ssh --
  physical power cycle. Instead: `sync`, then
  `echo b > /proc/sysrq-trigger`, which resets immediately and does work.
- **`sysrq-b` does not sync.** An `scp`'d module still in page cache is
  lost and the board comes back running the *previous* build, which looks
  exactly like a code bug. `sync` first, and check the on-board sha against
  the host before trusting a result.
- **DECD plus a live MIPS has hard-locked repeatedly inside frame submit.** A
  2026-08-31 attempt locked when CPU_COMM was already loaded before the submit;
  the immediate retry succeeded when DECD submitted first and CPU_COMM was
  loaded only after interrupts were advancing. A later attempt using that same
  order locked less than 500 ms after `FRAME_SUBMIT` returned, before the
  delayed CPU_COMM load even began. The order reduces one overlap but is not a
  cure. Do not keep retrying this live-dwell recipe.
- **Shared memory is mapped uncached.** `memcpy` on it takes an alignment
  fault (`FSC 0x21`) on arm64 Device memory; aligned `u32`/`u16` reads are
  fine, byte arrays need `memcpy_fromio`. This already cost one Oops.
- **Check the on-board module against the host build before believing a
  result.** `sha256sum /root/hy310-cpu-comm.ko` versus the build tree. A
  stale module has already produced one confident, entirely fictional
  measurement in this work.

## Files

- `tools/display/cpu-comm-probe.c` -- the existing no-op probe; the new
  client should replace it rather than grow beside it
- `tools/display/mmio-rw.c` -- general MMIO read/write/dump, needs `cc` on
  the board
- `docs/reference/cpu-comm-routine-table-2026-08-30.txt` -- captured table
- `/proc/cpu_comm/routines` -- regenerates it live, and reflects whatever
  the firmware has brought up, so re-read it rather than trusting the
  capture
