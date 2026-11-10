# SCP sampling safety review — October 31, 2026

**Safety review complete: NO-GO for live insertion of the first prototype.**
Live-capture preparation remains blocked; this is not an armed or executable
capture package. No live insertion/installation was attempted. The required
current bad state remains intact: same boot, identical SCP SRAM bytes, host
HDMI disconnected/zero EDID, board signal none. No reseat, HPD pulse, peripheral
write, service restart, SCP reset, reboot or UART arming occurred.

[Machine-readable verdict](RESULT.json), [execution gate](LIVE-CAPTURE-GATE.json),
[tests](tests.txt), [ownership audit](OWNER-AUDIT.json).
[Reproducible offline review tool](../../../tools/hdmi/test-scp-capture-safety.py).

## What passed, and what failed

The independent review consumes the emitted binary and exact SRAM snapshot;
it does not call the original assembler's simulation. Twelve test groups pass,
including 400 nominal register/loop-phase combinations and 14 injected stalled
reads. Nominal runs preserve general registers/F, match all 14 captured words,
self-restore the hook and store only in bounded SRAM. Before-bytes, canaries,
corrupt return/branch and an injected peripheral-store mutation are checked.
This remains a restricted Python instruction model, not an independent CPU,
cache implementation, kernel-runtime or hardware qualification.

The tests reproduce these **counterexamples**, rather than hiding them behind
a nominal pass:

| Condition | Concrete result |
| --- | --- |
| Stop at first valid completion marker | Original hook word already restored, but context still changed and PC is 0x4ea8 inside scratch code. Completion is not return proof. |
| Restore scratch bytes at that marker | Subsequent execution encounters unreviewed instructions. Early cleanup is unsafe. |
| Permit a stale cached hook fetch | Done marker and original hook memory value can coexist with a second probe entry. A RAM readback is insufficient instruction-fetch proof. |
| Stall each of the 14 peripheral loads | SCP remains in the probe, done absent, hook not restored. No non-reset recovery has been proven. |
| Stop request becomes pending | The probe still performs its reads. It is not interlocked with owner teardown. |

These are adversarial model executions, **not claims that this board currently
has an enabled instruction cache, a stalled bus or a concurrent stop**. The
400 nominal cases cannot rule them out. The early-marker failure is present
in the actual emitted instruction order without a cache/stall assumption.

## Ownership and coherency review

The installed signal owner has SHA-256
`0a6987ced911cc12f2a36ff2a9550e397c1c0f5889f4b65e8453b298cefe4497`.
It reserves SCP SRAM 0x00100000–0x00104fff and reset control
0x07000400–0x07000403. Its stop setter takes a private `signal_lock` and can
restore HPD/DDC, stop SCP and restore the page. A raw userspace mapping does
not take that lock or serialize with the kernel parameter store. Sampling
state/ready flags before a patch does not close the race.

The kernel exports `kernel_param_lock`/unlock, and its parameter-store path
uses them. A correctly integrated companion might use that path, with safe
module lifetime handling and verified ABI/address binding. No such validated
companion exists here. Discovering private section/symbol addresses is not
an approved ownership protocol; no private kernel pointers were used to write
or acquire locks. We did not replace or restart the installed signal owner.
The available kernel build reports #2 October 24 while the running kernel is
#1 October 16; matching `6.18.38` alone is not a new companion's ABI proof.

[OpenRISC architecture 1.1](https://openrisc.io/or1k.html), sections 4.6, 7.2
and 9.2, describes reset cache-enable bits, memory ordering and instruction
synchronization. It permits instruction caches that are not coherent with
other processors. The reference reset state disables caches, but that and a
readback of current SRAM are insufficient H713-specific evidence of live
fetch visibility. Another OpenRISC implementation's defaults are not proof
of this hardware's current state. ARM I/O accessors also do not by themselves
invalidate an SCP instruction cache. No speculative cache-control instructions
or direct ARM receiver-register reads were attempted.

## Requirements for a replacement live path

1. Bind to the exact boot, running kernel ABI, installed owner and source bytes.
   Own module lifetime and serialize from preflight through capture/egress
   with the owner's existing stop path. Do not bypass private ownership.
2. Establish H713-specific instruction-fetch visibility, aligned insertion and
   interprocessor ordering; include faults for stale/prefetched instructions
   and delayed stores. A completed data transfer is not a fetch guarantee.
3. Add a fresh post-return acknowledgement on the original wait-loop path,
   observed after context restoration. Reject stale generations and partial
   returns. Do not infer safe code removal from the existing done marker.
4. Specify failure containment with **no automatic HPD/peripheral writes,
   restart, retry or core reset**. A stuck peripheral load cannot be timed out
   by the SCP itself while that load is stalled. Leave ambiguous scratch code
   intact and preserve evidence; cleanup needs a separately proven safe point.
5. Validate the actual kernel transaction and replacement payload together,
   including ownership races, every insertion phase, all bounded writes,
   transfer/fetch failures and acknowledgement/cleanup faults, before a new
   package can claim live readiness.

These requirements are not a relaxation of the operator's state-preservation
constraint. No live execution command or force/override flag is provided.
The first prototype is quarantined as REJECTED-PROTOTYPE-DO-NOT-WRITE.

## Package and reproduction

Private package: `local/recovery/2026-10-31-scp-capture-safety/`.
It contains original/current byte-identical SRAM snapshots, all prototype
before-bytes, its rejected binary, the independent review tool and results,
read-only owner evidence, source references and SHA256SUMS.
`scp-capture-safety-review.tar.gz` seals this review; **it is not installable**.
Earlier sealed migration and UART-controller packages remain unchanged.

From the extracted private package:

```sh
sha256sum -c SHA256SUMS
python3 test-scp-capture-safety.py \
  --snapshot baseline-snapshot-private.json \
  --prototype REJECTED-PROTOTYPE-DO-NOT-WRITE \
  --output /tmp/scp-capture-safety-result.json
```

A test-suite exit status 0 means the safety findings reproduced. It does not
mean live capture is approved; inspect live_capture_ready=false and the
NO-GO verdict. Raw SRAM and runtime kernel addresses remain private/ignored.
Source changes and this review are uncommitted; no push was performed.
