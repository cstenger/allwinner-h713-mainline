# Clean and abrupt reset comparison — October 20, 2026

The five sampled words are identical after the clean and synced SysRq-b
resets, at each of the three proper-only probe stages. Both recorded warm
boots retain GP6, initialize and quiesce the logo firmware, then enter Linux
with MIPS parked. This is a reset-state observation, **not automatic HDMI
recovery**. No production policy or firmware was changed during these trials.

## Conditions and provenance

User-authorized trials followed the [staged procedure](../../hdmi-reset-instrumentation-2026-10-20.md)
after the [offline ext4 repair](../2026-10-20-ext4-repair/README.md).
Each trial started from its own operator-confirmed physical cold cycle, with
power and USB/UART disconnected for at least 60 seconds and the same HDMI
source connected afterward. Input resolution/rate was not supplied; the
fixed 48-kHz capture format does not establish the input format.

Installed proper SHA-256:
`314d81a3e17646c0250bbbadaac38762560acad8378e1f8b0b141487b068664c`.
[Artifact preflight](artifact-preflight.txt) verified the fixed-layout boot,
SPL, environment and rescue regions and rollback package. SPL, BL31, DTB,
boot script and saved environment were not changed. Optional SPL probes
were not installed. The complete passive capture and full Linux collectors
remain local under `build/hdmi-reset-paired-2026-10-20/`; hashes and extraction
byte offsets are retained in [result.json](result.json) and the trial records.

## Healthy cold baselines

| Trial | Starting Linux boot ID | Startup |
| --- | --- | --- |
| Clean | `c805a755-a1ea-4df4-839a-212692bc98a0` | All three HDMI units active; capture RUNNING; DSP failure N; XRUNs 0 |
| Abrupt | `c7a1bbac-b6a6-4b55-ae49-be372459f0f5` | Same software checks; DSP versions 0/0 → verified 1/1 |

Both cold UART sequences began with GP6 zero and contained the expected two
workspace loads. Root reported clean and growfs succeeded in both Linux
baselines. These are software/digital-path observations, without a new
operator-confirmed audible or visual pass. See the compact cold-state JSON
snapshots and `*-cold-health.txt`.

## Reset methods and observations

The clean trial used one ordinary `systemctl reboot`, guarded by boot ID,
active services and DSP health. The exact prior-boot service journal records
speaker stop, signal/SCP/SRAM/DDC restoration, all **22 DSP and 15 TVFE words
restored**, terminal parking and receiver removal. It reached the new Linux
boot `18f37fd5-1962-4abc-9509-cf80a11b1144`; the handoff was absent and all
three HDMI units were inactive due to their conditions. Root remained clean
and growfs succeeded. See [clean-shutdown-and-health.txt](clean-shutdown-and-health.txt).

The abrupt trial ran the archived [trigger](abrupt-reset-trigger.py.txt):
check the fresh boot ID, active units, both running PCMs and DSP health; sync
filesystem writes; recheck guards; write a UART marker; then write `b` to
`/proc/sysrq-trigger`. The kernel recorded `sysrq: Resetting` at
**51.716272 seconds**. There was no normal service/device teardown request.
The marker was cut off/interleaved by reset; preserve that limitation rather
than reconstructing missing bytes. See [trigger interval](abrupt-trigger-interval.serial.log)
and [trigger output](abrupt-reset-request.txt). This is not a hung-kernel or
actual autonomous watchdog-expiry test.

The recorded abrupt boot completed logo and entered Linux with MIPS parked.
Ext4 reported journal recovery complete, without the prior orphan error.
Journald replaced `user-1000.journal` as corrupted or uncleanly shut down;
that message does not prove an ext4 consistency failure or lossless logging.
No offline fsck was performed after the abrupt trial.

The original recording ends at login. Before work resumed, the user powered
the board down after a usage limit. The later observed live-HDMI boot
`c21ffe52-9f0e-4bb5-9e2a-f823e6a721af` must **not** be attributed to the
recorded abrupt reset. UART and SSH cross-checks agree on that later boot.
The intervening journal boot `75feb00e-aa3a-46b1-8c7a-360dc313f273` records
all three HDMI units skipped because the handoff was absent, consistent with
the saved abrupt UART trace. Its identity was not captured directly on that
UART interval. See [intervening-boot-journal.txt](intervening-boot-journal.txt).
Board wall time resets, so wall-clock journal ordering alone is insufficient.

## Stage comparison

[Analyzer output](reset-comparison.json) uses one extracted raw boot per
method, with exactly one `proper_preboot` marker in each. All values below
were identical in the two trials:

| Stage | GP6 | GP7 | MIPS clock | MIPS reset | MIPS status |
| --- | --- | --- | --- | --- | --- |
| Proper before preboot | `48444d49` | `00000000` | `00000000` | `00000000` | `00000000` |
| Before logo workspace clear | `48444d49` | `00000000` | `00000000` | `00000000` | `00000000` |
| After logo/quiescence | `48444d49` | `00000000` | `80000002` | `00000000` | `00000000` |

The clean shutdown explicitly parked MIPS, but the abrupt reset reached the
same sampled MIPS state without that teardown. Thus these five words at
proper initialization do not distinguish whether orderly HDMI restoration
ran. SPL/BL31/earlier initialization have already happened; these probes do
not establish the exact hardware reset-entry state or the reset domain
responsible. No post-reset DSP version/lock, SCP state or receiver reset
contract was measured before logo initialization overwrote evidence.

## Next work and release status

Keep GP6 and all shutdown/version/lock guards intact. The next measurement
must distinguish DSP, SCP and receiver freshness before logo/workspace
initialization, rather than repeating these five-word probes alone:

1. Audit the powered clock/reset windows and protocol effects of each proposed
   observation. DSP version reads are protocol operations, not passive MMIO.
   Prefer reviewed owner/passive trace mechanisms; do not probe unpowered
   receiver registers or invoke a DSP command on the skipped warm path.
2. Prepare narrowly staged instrumentation and an exact rollback. If earlier
   SPL hooks are needed to locate when MIPS reset occurs, validate them as a
   separate artifact/control pair; they still do not measure DSP freshness.
3. Repeat paired trials with immediate UART boot-ID capture and a completed
   Linux snapshot before ending the recording. Stop on unexplained failure.
   Include an uninterrupted instrumented cold control for any new accesses.
4. Only after a verified reset/adoption contract, implement bounded recovery
   and run the planned repeated warm, abrupt and actual-watchdog gates.

The current release blocker remains automatic warm-reboot HDMI recovery.
These measurements narrow the MIPS question; they do not justify clearing
GP6, accepting DSP version 1/1, relaunching source3 or removing the hold guard.
