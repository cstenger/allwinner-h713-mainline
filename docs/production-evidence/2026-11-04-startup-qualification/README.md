# Repeated startup qualification — held at cold 2 frame-rejection gate

Five ordinary warm boots pass digital qualification. Cold 1 passes; cold 2
returned the desktop but failed the strict zero-rejection gate with two
rejected frame copies. Cold 3 was not run. That uninstrumented boot series was stopped pending investigation/disposition.
No further optimization was installed. A subsequent
[matched diagnostic comparison](../2026-11-05-matched-startup-trace/README.md)
completed three cold boots per startup arm with zero new rejections. Its trace
module is now installed and the board is running the optimized sequence. This
separate instrumented experiment does not waive the cold-2 strict failure.
[Machine-readable progress](results.json).

Chris authorized repeated cold and warm boot testing of the installed
completion-aware MIPS checks and parallel capture startup, before any further
optimization. Installed code/configuration is held fixed.

Planned scope: five ordinary warm reboots and two additional physical cold
cycles, adding to the already-recorded combined-stage cold boot
4943b6a8-a036-4f03-95a1-f2f778f1238d (three cold boots total).
Cold cycles require power and board-side UART/USB disconnected for over one
minute; no source/cable setting changes, reseats or manual board-service
recovery. No abrupt reset or power-loss qualification is implied.

Each boot gets the accepted RC runtime audit with only the exact authorized
startup deltas added: 73 file/metadata/symlink pins, kernel configuration,
package set, four CPUs, eMMC identity/root partition geometry and protected
boot/environment readback, all four HDMI bundle manifests and startup health.
No test program is installed on the board; read-only collection runs over SSH
stdin. The host-side driver controls one requested warm reboot at a time.

Additional evidence requires five complete MIPS replies, automatic HDOK/GP7
acknowledgement, same-boot prepare adoption and observed overlap with the user
session. Eight HDMI units must remain active, successful and restart-free;
720p source lock and RUNNING capture/playback PCMs are required.
At least 30 seconds of sampled stability must show increasing frames, at
least 50 fps, no service identity changes, no frame rejects, audio xruns,
bad guards or invalid pairs. Detection retries are recorded separately.

Every transition checks the preceding persistent journal for signal/DDC
restoration, 22 DSP and 15 TVFE words restored, terminal MIPS parking and
receiver removal. The observed shutdown order must be consumers → signal →
capture → prepare/user session. Stop on a failed board check; no automatic
recovery, module reload, forced detection or second reboot request.

The first warm request's SSH connection closed with status 255 before command
acknowledgement; the second old connection stalled until its 20-second driver
timeout. Both original driver failure receipts remain preserved. UART proves
exactly one restart per run and new boot IDs; collection resumed read-only
without another reboot. The host driver was amended to bound SSH keepalive
and observe a new healthy boot plus preceding shutdown after a connection
close/timeout, never to resend the command. A regression exercises both
transport cases and proves one request and refusal to reuse a run directory.
No installed board code changed. Subsequent warm runs completed directly
under this observation policy.

Current completed digital results:

| Run | Boot ID | Result |
| --- | --- | --- |
| Combined-stage cold 1, rechecked | 4943b6a8-a036-4f03-95a1-f2f778f1238d | 73 pins; stable 59.72 fps; zero errors/restarts |
| Warm 1 | 77e2e862-2402-478f-8604-c6c9916a646e | Full audit/shutdown order; stable 59.72 fps; no detection retry |
| Warm 2 | 47a69dfc-87bb-4c89-867f-7d305f4c23c2 | Full audit/shutdown order; stable 59.69 fps; no detection retry |
| Warm 3 | 0d52969b-b5b5-43c4-bf4c-40449a23b65b | Full audit/shutdown order; stable 59.69 fps; no detection retry |
| Warm 4 | 3a479719-1f52-41be-b842-48fe4e315ef3 | Full audit/shutdown order; stable 59.69 fps; no detection retry |
| Warm 5 | 5ba7d4a0-29e8-41d4-b07e-5634f9ea5022 | Full audit/shutdown order; stable 59.73 fps; no detection retry |

Across the five warm runs: capture ready at Linux 14.401–14.864 s, renderer
active at 16.081–16.567 s, and observed user-session overlap 3.242–3.303 s.
Each stability window ran at least 36 seconds and all eight HDMI services
retained their identities with no restarts. All sampled frame/audio/guard/
pair counters were zero. Every boot logged five complete MIPS responses and
automatic HDOK with GP7 zero, and capture adopted the prepared backend.
All five preceding shutdowns restored signal/DDC ownership, 22 DSP words and
15 TVFE words, parked MIPS and removed the receiver in the required order.

Operator picture/audio observations are recorded separately from digital
health. RUNNING PCMs alone do not prove audible content.

Private logs and exact verifier/source snapshots:
local/recovery/2026-11-04-startup-qualification/.
Host driver: tools/hdmi/startup-qualification.py. Five offline tests cover
remote parsing, missing/invalid evidence, frame/boot/service regressions,
shutdown restoration/order and SSH-disconnect handling without retry.
The two original transport failures and their read-only continuations are
separate receipts (warm-01/ and warm-01-observed/, warm-02/ and
warm-02-observed/). All five warm requests are recorded once each. This is
ordinary warm-start coverage, not abrupt-reset or complete release
requalification.

## Checkpoint before cold cycle 2

After warm 5 passed, the 73-file/runtime audit and current startup evidence
were checked again, then one clean poweroff was requested. UART confirms
Power down at Linux 158.881952 s, host UTC 2026-11-05T02:43:36.109596Z.
The board is off and passive UART capture remains armed. A closed copy of
the warm-series UART evidence and hashes is preserved separately from the
ongoing recorder. No further board control is queued.

Next: operator disconnects supply and board-side UART/USB for over one minute,
reconnects UART with HDMI/source unchanged, then powers on. Collect cold 2
with preceding boot 5ba7d4a0-29e8-41d4-b07e-5634f9ea5022, including its shutdown
restoration/order, audit and stability interval. If it passes, arrange one
more identical cold cycle for cold 3. Picture/audio observations for the warm
series were requested at this checkpoint. Chris subsequently reported:
"I saw the desktop, didn't notice any issues." This records desktop visibility
and no reported issues during the series; individual per-boot observations
and audible source content were not separately enumerated. Automated audio
flow and xrun checks passed on every warm run.

## Cold 2: strict frame gate failed; no further cycle

Chris confirmed power and board-side UART/USB disconnected for over one minute,
then UART reconnected before power-on, and the HDMI desktop returned.
Boot ID: f410f943-cb9a-4e72-8ee7-2c8a9c2cc650.

The 73-file/runtime identity audit passes, including kernel/package/boot-storage
checks and all four HDMI manifests. All eight HDMI units are active with zero
restarts. Five full MIPS replies, automatic HDOK and prepared-backend adoption
are present. There was no HDMI retry. The preceding warm-5 shutdown passes
restoration and the required consumer/signal/capture/prepare/user ordering.

However, the first error snapshot, Linux uptime 156.52 s, reported two rejected
copies after 8,372 frame-production events. Audio xruns, bad-guard and
invalid-pair counters were zero. The strict test stopped before starting its
qualification stability window. The exact event times were not logged; do
not label this an immediate startup failure or attribute it to the startup
changes without evidence.

Three subsequent read-only observations at uptimes 221.98, 232.93 and 243.92 s
show the rejection count unchanged at two. Frame production continued at
59.71 fps, signal remained locked, and all sampled service identities and
other counters stayed healthy. This is diagnostic follow-up, not a replacement
passing qualification window.

The audited driver runs in pair-completion mode. Its rejection increment is
the protective branch that discards a copy when source content changes or the
capture pair advances/changes during the copy. It retains the buffer for a
later valid copy instead of submitting the rejected one. The previous
[GF1 disposition](../2026-11-04-guarded-discard-disposition/README.md) reviewed
one such historical event and explicitly did not grant a blanket waiver for
new events. These two are preserved as a new strict-test failure. They do not
by themselves prove corruption reached the display or that either startup
change caused the event.

Initial SSH connections timed out and then returned without any network,
service or host-route change. UART showed SSH active and the expected address;
host ping saw a reply and one lost packet. Exact SSH readiness/transport cause
was not established. All connection attempts and diagnostics are preserved.

No service restart, module reload, source change, poweroff, reboot or
optimization followed the failed check. The board remains on in the same boot.
Only the host's passive UART recorder was closed to seal the evidence. Cold 3
is deferred, and the overall repeated-startup qualification is incomplete.
Private cold-2 result, failure receipt and follow-up observations are under
local/recovery/2026-11-04-startup-qualification/cold-02/.

Subsequent [read-only investigation](../2026-11-04-rejected-copy-investigation/README.md)
confirms the exact same guard/source as the prior GF1 event, with the count
remaining two after more than 133,000 production events and normal delivery.
Whether the startup timing changes influence its incidence is unresolved.
A guard-preserving diagnostic source package is prepared/tested only; no
driver installation or further boot has occurred.
