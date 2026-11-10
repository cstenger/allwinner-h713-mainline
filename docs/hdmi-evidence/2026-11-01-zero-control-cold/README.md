# Matched 0 ms cold-start control passed

**PASS: one cold start with the matched 0 ms control.** The operator reported:
“The board booted and showed the host's desktop.” The loaded service and journal
confirm `--bench-delay-ms=0`. HDMI locked at 1280×720 and Linux is healthy.

The [two-second cold run](../2026-11-01-startup-delay-cold/README.md) also passed.
Therefore the deliberate two-second wait was unnecessary for this observed cold
boot; its causal benefit remains unproven. One success per condition cannot
establish comparative failure rates.

## Cold-start conditions and recorded sequence

Fresh recorders were armed before one ordinary poweroff from boot
`e6ccc77a-dfb2-411c-a2cf-139c35d4dceb`. The guarded request verified the exact zero
control, file/runtime pins, backup and ready ownership, created an exclusive
receipt, synced and called `systemctl poweroff` once. UART captured
`[ 1550.208721] reboot: Power down`. Both original host recorders remained live.

The operator confirmed power was removed for at least 60 seconds and the board
was still off. Recorders and sole read-only UART ownership were verified before
prompting one power-on. Physical supply removal is operator-confirmed, not a
software voltage measurement. Requested conditions were HDMI connected and host
settings unchanged. No agent recovery/reseat/forced detection/display change ran;
no intervention was reported by the operator.

UART captured exactly one SPL/proper startup, no kernel restart, migrated U-Boot
loading its environment from MMC offset `0x93d80000` successfully, and Linux
login. The new boot ID is `275f5bce-8d22-4d20-9ba8-9551b05dac7f`.

## Measured startup

The journal contains exactly one zero-control start/completion pair for this
boot, with no retry. Its **21.638583 ms** interval includes the unchanged
completion checks. It is not a configured wait; the zero path immediately moves
through the deadline check into those checks. The wrapper/helper/module hashes
match the tested package.

| Milestone | Linux uptime, seconds |
| --- | ---: |
| DSP graph verified | 22.687333 |
| Zero-control interval start | 23.176962051 |
| Zero-control interval complete | 23.198600634 |
| Kernel EDID/HPD ready | 23.240379 |
| Initial signal none | 23.860193 |
| Signal acquiring | 24.323575 |
| Signal locked, 1280×720 | 24.547561 |

These are kernel/monotonic times, not the board wall clock. The actual loaded
ExecStart specifies 0 ms; production ExecStop is unchanged.

The cached host monitor recorded shutdown to disconnected/empty EDID and then
disabled output. On cold startup, it observed connected with a 256-byte EDID at
**09:40:45.353286 UTC**, then connected/enabled at **09:40:45.604091 UTC**, November 1.
It stayed connected through recorder closure at **10:00:08 UTC**. Cached
attributes are sampled sequentially; these are observation timestamps, not
physical HPD-edge or DDC transaction timestamps.

The EDID header and both 128-byte checksums pass. SHA256
`edab9bfc48547939fcb26f7775558c94569a11abb4beb1132e22f2ad4c173d34`
exactly matches the unchanged board payload and the two-second tests.

## Linux, frame flow and integrity

Linux reports running, multi-user target active, zero failed units and a ready
session belonging to this boot. Capture, signal, ring, speaker and video services
are successful with zero restarts. Signal owner is ready, failed N, restored N,
recovery zero. The normal startup check and on-disk unit verification pass.

At uptime 1,105 seconds, video was locked with 64,493 frames produced and 64,489
delivered. At 1,155 seconds it remained locked with 67,485 produced and 67,481
delivered. Signal transitions stayed two, bad guards/invalid AFBD stayed zero,
and rejected/overwritten counters stayed two each across these snapshots. This
validates startup and sustained frame flow, not a separate lossless-media or
audio stress qualification.

All **56 production file/metadata pins**, **five private runtime files**,
**eight protected storage ranges**, **both installed migration regions** and
saved backup files match the pre-test staging evidence. No diagnostic module,
service recovery, extra boot or additional configuration change was introduced.

## Comparison and interpretation

| Cold-start variant | Requested wait | Logged bench interval | Graph → EDID/HPD-ready | 720p lock at Linux uptime | Desktop |
| --- | ---: | ---: | ---: | ---: | --- |
| Matched delayed | 2,000 ms | 2.021728 s | 2.548278 s | 26.283372 s | Yes |
| Matched zero control | 0 ms | 0.021639 s | 0.553046 s | 24.547561 s | Yes |

The zero run locks about 1.74 seconds earlier, while both outcomes succeed.
This removes the basis for treating the two-second wait as an established fix.
The failure may be intermittent or dependent on startup/source history. Common
instrumentation overhead also remains a candidate: zero control retains its
checks/logging, and its graph-to-ready interval was about 0.553 s versus about
0.425 s in the earlier failed uninstrumented production cold boot. This does
not prove that the extra approximately 0.128 s is beneficial either.

Actual supply-off durations were not independently measured or equalized beyond
the operator-confirmed minimum. Both new tests followed an orderly shutdown from
a working HDMI session, which need not reproduce the original failure history.
Repeated matched cold trials and reproduction of the failure are needed before
isolating a specific board/DDC/HPD timing mechanism or adopting a production fix.

## Closure and remaining configuration

Both original passive recorders stopped cleanly; UART is released. No UART
reopen/disconnect or cached-reader error occurred. Raw recordings, EDID,
read-only snapshots, sources, receipts and comparison are checksum-sealed under
`local/recovery/2026-11-01-hdmi-zero-cold-validation/` and its sibling archive.
Earlier warm/cold/package/staging evidence remains unchanged.

The board is left running with HDMI locked and the host desktop visible. The
temporary **0 ms override remains installed**. Review/remove or change that
single override before another unplanned boot using the
[zero-stage backup/reversion record](../2026-11-01-zero-control-stage/README.md).
No reversion or extra power action was performed during validation.

Evidence: [result](RESULT.json), [comparison](COMPARISON.json),
[signal journal](signal-journal.txt), [UART milestones](uart-excerpt.txt),
[operator observations](OPERATOR-OBSERVATION.json) and [recorder closure](RECORDER-STOP.json).
