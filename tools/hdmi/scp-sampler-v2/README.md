# Resident SCP sampler, version 2

Prepared diagnostic for the current H713 Linux boot. **Preparation does not
authorize loading or capture.** The first prototype remains rejected and must
never be installed. This replacement uses a kernel companion and a resident,
one-shot SCP monitor. Its default command only verifies the sealed package and
prints an offline plan.

## Preservation protocol

The companion loads inertly. On an explicit capture request it pins the existing
signal owner through public module/kobject APIs, takes the owner's public kernel
parameter mutex, and checks canonical boolean readiness parameters while holding
that mutex. The installed owner's stop setter takes this same mutex. The
companion never looks up private kernel pointers or replaces the owner.

Before changing SRAM it compares the entire 20 KiB preimage. Aligned word writes
are restricted to the original wait-loop patch sites, two reviewed scratch
fragments and a 128-byte output area. ARM maps only SCP SRAM; it never maps the
receiver's unsafe MMIO, reset controls or GPIO. The SCP monitor performs exactly
14 whitelisted receiver loads and no peripheral stores. GP6/GP7 and PB5 are not
touched.

The initial instruction-fetch problem is addressed before entering new code.
Individually safe replacements in the existing loop observe its zero register,
archive an unused register, and obtain a fresh supervision-register sample.
Unsafe cache/MMU/interrupt/shadow-context bits cause a retained refusal. No
instruction writes the supervision register. After staging scratch code, a
fresh SRAM-only acknowledgement proves execution of a pipeline synchronization
and entry into an existing-address park loop. Only then is the park redirected
to scratch. The monitor synchronizes again and restores the borrowed register.

Entry and data completion are separate from return proof. The host changes a
challenge after entry and again after data completion. The monitor can echo each
fresh challenge only after returning through the original loop and revalidating
its context. A consumed command plus a retained one-shot latch prevent duplicate
sampling if a stale hook is fetched. After success the original entry word is
restored; the scratch image and an SRAM-only guard remain resident. No executing
code is erased or reclaimed on an assumption about cache visibility.

## Retained lifecycle

Both success (`status=8`) and an ambiguous failure (`status=10`) retain the
owner mutex and the companion's own module reference. A stalled receiver load
cannot be recovered automatically without risking the bad state. There is no
reset, retry, timeout cleanup, automatic release or unload in the capture driver.
An SSH failure also leaves retention in force. A failure during bootstrap can
leave the temporary loop/register state resident; it must be reported without
attempting cleanup.

After capture, **do not read the original signal owner's sysfs parameters or run
the ordinary startup checker**: those accesses wait for its held parameter
mutex. Read the companion's status/result and saved SRAM instead. A future,
separately authorized release may end preservation after successful capture;
that operation can unblock a queued owner stop. Frozen failure has no release
path. Remaining resident SRAM is ultimately owned by the original driver and
is not an allocation the diagnostic may erase.

## Files and offline verification

`build.py` binds the monitor to the exact boot, SRAM, original firmware and
resident owner build. `core.h` and `owner.h` are compiled unchanged into the
kernel companion and native test adapter. `model.py` decodes the emitted binary
independently, models delayed store visibility and mixed old/new instruction
views, and rejects unreviewed accesses. `remote_test.py` executes the exact
remote Python program over simulated SSH pipes and connects its fake sysfs to
the native C transaction. No test touches hardware.

The private package includes the matching-kernel AArch64 module, baseline,
generated header, binary listing, 56 installed-file/metadata pins, source copies,
test/build evidence and SHA-256 ledger. It contains raw SRAM and must stay in
ignored local storage. Verify with:

```sh
python3 PACKAGE/test.py --packet PACKAGE
python3 PACKAGE/test.py --packet PACKAGE --mutations
python3 PACKAGE/capture.py --packet PACKAGE
```

The live driver requires a separate `--execute-approved` action and a new private
output directory. It checks cached host disconnected/no-EDID state, board boot
and builds, file pins and SRAM again; durably saves the preimage on the host
before an inert memfd load; and durably records capture intent before the single
trigger. No persistent board file is installed. Do not execute that mode as part
of preparation.

Offline tests establish behavior within the stated instruction, ordering and
kernel API models. They are not H713 silicon qualification or proof that a
receiver read cannot stall. A later live attempt is explicitly guarded and may
remain frozen while preserving the diagnostic evidence.
