# Immediate command-boundary sampling, 2026-10-13

**Eight complete graph apply/restore cycles passed; cycle9 failed the probe's
completion-clear check despite an expected response value in the port.**
No further DSP command was issued after failure. Diagnostics are unloaded,
MIPS responds, and physical cold boot is required before another DSP test.

The user cold-cycled and manually stopped at U-Boot. Guarded single MIPS
launch, live PID, source3 worker, preserved FIT and RAM-only IRQ correction
verified; Linux6.18.38 and source3/canaries verified after boot. No listener
was started and no boot artifact flashed or environment saved.

## Tested path and result

[Tested build](build-manifest.json) SHA256
60a2059069cc6f6494c61a8be1b5f10a8b311e0e32eedcd50685e0fcfeaf0d2b
moves deadline calculation before request publication, continuously polls clear,
and logs the raw command/response port on failure without accepting it.
The compiled path has no function call between request write and first status
read. `tested-probe.c` and `tested-completion.h` preserve the tested source.

Cold versions0/0, stock masked initialization, all724 pinned patch pairs and
versions1/1 passed;13 fast clear observations, zero slow observations/timeouts.
A20-cycle bounded loop then applied and restored the22-word graph with readback
on every write, stopping immediately on an error. Eight cycles fully passed.

Cycle9 saved all original words and verified the first13 graph writes.
The next write set007c to8081. Its readback timed out at completion-clear after
50,100us, status00000120. The raw command/response port held00008081 rather
than the published request007c0000. The preceding accepted response was0000
for8017. This is strong evidence that the read completed with the expected
new value while the observer missed the clear edge; it does not establish the
precise pulse width or independently measure DSP service timing.

See [full kernel trace](graph-kernel.log), [failure snapshot](failure.log),
[cycle counters](graph-cycles.log) and [summary](summary.json). There were594
fast clear observations, one slow attempt and one clear timeout. No PCM capture
was run in this investigation; earlier capture/recovery results remain valid.

[Cleanup](cleanup.log) confirms diagnostics removed, peripherals restored and
MIPS responsive. The ninth graph is partial and the volatile patch remains;
physical cold boot is required. The failure latch was not bypassed.

## Prepared next test: stock completion protocol

The next build offers `stock_completion=1`, default off. It follows the preserved
vendor routine: hold ownership, wait busy-clear, publish request, wait done-set,
then consume response. It does not require sampling done-clear. Busy and done
waits are bounded50ms and command failure still latches the module failed.
Graph values remain checked against the expected saved/applied values.
No status register is manually cleared and no automatic retry was added.

The shared helper's native tests cover an immediately completed new reply,
a delayed new reply with old completion initially set, device1's done mask,
and bounded timeout without consuming/changing the response output. These are
fake-MMIO protocol controls, not proof of actual hardware freshness.
The old clear-poll controls also still pass. LLVM W=1 passed.

[Next build](next-build-manifest.json), module SHA256
fddb6f9acea61cbd8bebb5b7c4244ed23f5259ddf852c669df8aedc6dd2d3070,
is retained at host `build/hdmi-dsp-stock-completion`. Source hashes and
compiled disassembly are preserved alongside. **It has not been tested on the
board.** After a new physical cold boot, verify versions, initialize/patch,
then repeat the graph cycles with `stock_completion=1`; on success, rerun real
ALSA capture and graph restoration. Do not yet integrate it into automatic
production DSP ownership.
