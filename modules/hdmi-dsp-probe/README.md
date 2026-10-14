# Bounded H713 DSP diagnostic

Current protocol,2026-10-13: stock busy-clear/request/done-set completion is
now the default. The previous extra clear-edge requirement intermittently
rejected completed reads; the new default passed24 full graph apply/restore
cycles and three real ALSA captures, with cleanup. See
[completion evidence](../../docs/hdmi-evidence/2026-10-13-dsp-completion/attempt3/README.md).
This remains a diagnostic helper. The ALSA driver now manages DSP state by
default; load this helper only for explicit external-helper diagnostics. Both
modules now reserve the DSP command/ownership resources and exclude each other.

## Prerequisites and ownership

Use the guarded physical cold boot, single MIPS launch and source3 transition,
verified trace canaries, TVFE/TVCAP power and four receiver clocks, stock-order
TVFE hold, and the ALSA driver's audio clock/IHB/AudioTop initialization.
See [ALSA instructions](../hdmi-audio/README.md). Load after the audio driver
and unload before its audio clocks or TVFE hold are removed. Exclude other ARM
DSP diagnostic clients. Module loading issues no DSP command.

Load with `armed=1 live_source3=1 audio_ready=1 lock_window_ready=1`.
The real stock lock maps05001530(peer) and05001534(ARM): wait for peer!=55,
publish ARM55, recheck peer, release ARMaa. Never write the peer word.
The shared lock header has native contention/race/timeout/readback controls.
Historical02031078/02032078 lock claims were incorrect; do not use them.

`dsp_word` accepts only logical0077/0130/fff7/80ff on device0 and encoded
180ff for device1's80ff. Device0 reads use command+10, busy bit4/done bit5;
device1 uses+18,busy bit7/done bit8. Ownership covers the entire transaction.
Busy-clear and done-set waits are each bounded50ms. Completion may finish
before the first sample; no visible clear edge is required or manually forced.

Any DSP timeout blocks later commands for the lifetime of the module.
**Physical cold boot is required before another DSP trial after timeout.**
Reloading is never a recovery for the failure latch. On failure, raw port
observations are evidence only and never accepted as a completed response.

For historical comparisons only, `stock_completion=0` selects the older
clear-then-set requirement. `dense_clear_poll=1` additionally samples clear
continuously with a precomputed deadline and initial100-us IRQ-off bound.
Both old paths can miss a fast clear and reject an otherwise completed read.

## Optional pinned patch and graph build

`tools/hdmi/build-dsp-probe.py` creates an isolated optional build, accepting
only the recovered2896-byte patch with SHA256
8e31db199e0078d142f622436ff0b7249b333dbb6df8ec3fbabc0d8fea6ea0c5.
It generates724 exact big-endian pairs in the build directory. The ordinary
module has no proprietary patch table or graph parameters.

`stock_patch=1` is a sysfs-only one-shot operation. It requires versions0/0,
verifies stock masked initialization at00ee/8034/8017, sends the stock prefix
and724 pairs with1ms pacing/bounded busy waits, then verifies versions1/1.
The volatile patch has no inverse; cold boot clears it.

The optional `stock_graph=1 graph_chain=1` mode saves all22 original words,
applies the fixed stock route8f processing chain and verifies each write.
The `graph_chain=1` acknowledgment is an insmod argument; `stock_graph` is
sysfs-only. Explicit `stock_graph=0` restores saved words in reverse order with
readback. Restore while audio clocks and TVFE remain held, before module
removal. If any command fails, stop; do not attempt DSP restoration after the
failure latch. Partial state requires cold boot.

Alternative direct-route `capture_route` and `dtvout_second` diagnostic
parameters remain mutually exclusive with `stock_graph`; they are not the
validated capture graph. They save and restore their own words on explicit0.

## Repeatable checks

Build both ordinary and pinned variants against the exact installed kernel.
Native controls: `tools/hdmi/test-dsp-lock.py`,
`tools/hdmi/test-dsp-stock-response.c`, and `tools/hdmi/test-dsp-completion.c`.
The latter two compile with ordinary `cc -Wall -Wextra -Werror` and run without
board access.

For graph-cycle testing, keep ALSA closed, `graph_ready=N`, `stock_graph=N`,
and require `stock_completion=Y`, `graph_chain=Y`, `stock_patch=Y` from successful
setup. Run on the host:

```sh
python3 tools/hdmi/run-dsp-graph-test.py --cycles 20 /tmp/h713-dsp-cycles
```

It stops immediately on error, records read-only evidence in finally, and
checks68 completed reads per full cycle. It never loads modules, patches the
DSP, retries a timeout or resets a failure latch. Real capture remains tested
by `tools/hdmi/run-alsa-capture-test.py` after graph verification and explicitly
setting the ALSA driver's `graph_ready` acknowledgment.
