# SCP sampler v2 — offline qualification and live preparation

The replacement sampler is prepared for a separately authorized, guarded live
attempt. **It has not been loaded or executed on the board.** Final read-only
checks confirm the same boot, byte-identical SCP SRAM, all 56 installed-file
pins, board signal `none`, and host HDMI disconnected with zero EDID. There was
no reseating, HPD pulse, service restart, SCP reset, board reboot or UART TX.

[Result](RESULT.json), [capture gate](LIVE-CAPTURE-GATE.json),
[tests](tests.txt), [mutation tests](mutations.txt),
[module build](module-build.txt), [module audit](module-audit.json), and
[source/protocol](../../../tools/hdmi/scp-sampler-v2/README.md).
The [first prototype's NO-GO review](../2026-10-31-scp-capture-safety/README.md)
remains valid for that prototype; its sealed artifacts were not changed.

## Changes that address the blockers

| Previous blocker | Replacement behavior |
| --- | --- |
| Completion published before context restore/return | Separate entry/data markers and two fresh challenge echoes. The post-data echo requires a return through the original loop and context revalidation. |
| RAM readback does not establish instruction visibility | A bootstrap in existing instruction locations dynamically observes safe cache/MMU/interrupt state. A fresh park acknowledgement proves pipeline synchronization after staging and before the first scratch fetch. Unsupported or stale synchronization cannot release the park to scratch. |
| Possible stale hook entry after apparent unhook | Monitor remains resident. Command consumption and a one-shot latch prevent duplicate sampling. No executing code is erased. |
| No serialization with original owner stop | Public kobject/module lifetime APIs plus the owner's public kernel parameter mutex. Readiness is checked under that mutex; queued stop remains blocked after success and ambiguity. |
| No matching-kernel companion ABI proof | Cached kernel GNU build ID matches the running kernel. Companion builds against its generated inputs; all imports are exported; module layout is compile-asserted and forced unload is disabled. |
| Stalled receiver load cannot be safely cleaned up | No automatic cleanup, release, retry or reset. Retain the image, owner mutex and companion reference; report frozen failure. |

The ARM companion maps only SCP SRAM `0x00100000..0x00104fff`. Its writer uses
whitelisted aligned 32-bit stores and barriers. Receiver registers are loaded
only by the SCP, with the same eight control/configuration words used by the
existing firmware and six words from its EDID banks. There are no peripheral
stores in the monitor. GPIO, reset and clock APIs are absent. GP6/GP7 and PB5
are untouched.

## Evidence and limits

All **50 tests pass** and all **13 deliberate safety mutations** are detected
by behavioral failures.

The suite compiles the actual C transaction and owner coordinator into a native
adapter and independently decodes the emitted SCP binary. It exercises all four
original-loop phases, varied register contexts, delayed/out-of-order visibility
of stores to different words, mixed old/new bootstrap instruction views, stale
hooks/markers, canary collisions, unsafe SR bits, all 14 stalled receiver loads,
every nominal host-write failure position, owner pin/unload races, queued stop,
corrupt context/bytes, and explicitly authorized later release failures.

The complete host/remote protocol also runs over simulated SSH pipes, fake
sysfs/device files, real host memfd transfer and the native C adapter. Both held
success and frozen failure are checked, including durable before-bytes and
capture intent and absence of any release call. Mutation testing must produce
behavioral test failures; compiler or import failures do not count as detection.

The matching-kernel build uses `ARCH=arm64 LLVM=1 W=1 KCFLAGS=-Werror`. Kbuild's
compiler-version notice is retained: the kernel used clang 23.1.1 and the
companion uses 23.1.4. No source warning occurred. Kernel configuration, symbol
versions and generated identity inputs remained unchanged.

This is offline qualification within the documented instruction/order/API
models, not H713 silicon qualification. A receiver load can still stall. Such a
failure must stay frozen while preserving evidence; it is not a successful
sample and does not permit a reset under the current instruction.

## Prepared private package

`local/recovery/2026-10-31-scp-capture-v2/package/` contains the boot-bound
AArch64 companion, baseline SRAM, generated monitor/listing, source copies,
56 file/metadata pins, source audit, build/test evidence and checksum ledger.
The adjacent archive and archive checksum preserve the final packet. Raw SRAM
and installed-file details remain in ignored local storage.

The default driver verifies the packet and prints an offline plan. A later
explicit execution would recheck host/board identity and the preimage, durably
back up SRAM on the host, load an inert companion through a memfd, record intent
durably, and submit exactly one capture request. Preparation did none of these
live steps. The packet refuses another boot or changed SRAM and offers no retry.

After a live attempt, use only the companion's status/result and saved SRAM.
**Original signal-owner parameter reads and ordinary startup checks block while
the owner mutex is held.** Success retains the scratch image and an SRAM-only
guard until separately authorized release ends preservation; that release may
unblock a queued stop. Frozen failure has no release path. Do not unload,
restore the baseline, rerun a capture, or reset as an automatic follow-up.

U-Boot save-path validation remains on hold until the HDMI investigation and
its separate readiness requirements are resolved.
