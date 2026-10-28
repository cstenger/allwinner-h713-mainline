# Warm shared-startup repeats: offline preparation, October 24

Status: **OFFLINE ONLY. No SSH, serial access, board staging, reset or install performed.**
Live runs need explicit operator approval and `ready`. This runbook describes
all planned writes, including temporary checker files, RAM loading and resets.
The installed production startup and GP6 semantics remain unchanged.

## Review findings and changes

The October 23 test proved warm capture/audio and showed logo then console;
it predated the installed route B panel path. Two repeats remain.
The old runner supported only orderly reset. The checker sampled PCM flow,
not audio content, despite older preparation wording about RMS. No extra
capture reader should compete with the production speaker.

* Added `--reset sysrq-b`: boot-ID and HDMI health guarded, detached
  `setsid nohup python3 -c ...` with output to `/run/h713-warm-shared-reset.log`.
  Calls `os.sync()`, rechecks guards, emits a UART marker, writes `b` to
  `/proc/sysrq-trigger` once. No orderly teardown. This is a **synced abrupt
  reset**, not power-loss or an unsynced filesystem test.
* Added `--require-video`: both sessions require `locked 1280x720`, active
  ring/video units, produced/delivered counters advancing over three seconds,
  no added rejected frames, and bridge boot messages. Preserves the existing
  startup/DSP/audio checks. Captures full unit status, start timestamps,
  monotonic unit journal and bridge dmesg in each health JSON.
* Records reset intent before sending, so a failed/uncertain request blocks
  resume. A failed final comparison now exits nonzero. UART stage markers
  receive host timestamps. Installed kernel/FIT/script pins and census stay.
* Candidate `build/hdmi-warm-shared-repeat-2026-10-24/warm-shared.scr` is
  byte-identical to October 23 (`4c1ee8c0be5624c20195edfb79b4a043946957aa17e85142a98119dfbb568947`).
  No boot-time slimming or production changes.

## Offline validation

`python3 tools/hdmi/test-warm-shared.py`: 32 tests PASS (26 existing, 6 new).
The existing resume fixture emits TemporaryDirectory ResourceWarnings;
no test failures or skipped tests. `tests.log` contains the full output.
`python3 docs/hdmi-evidence/2026-10-24-warm-shared-repeat-preparation/mutation-check.py`:
8/8 deliberate in-memory code mutations caught, covering each new test;
see `mutations.json`. Mutations never invoke real SSH, UART or reset writes.
`cmp` confirms old/new RAM images identical. `git diff --check` clean.
`manifest.json` pins the FIT, RAM image and tools.

## Exact live sequence (two separate cold-to-warm trials)

These are proposed commands, **not executed**. Keep HDMI connected with a
moving 1280x720@60 picture and continuous audible tone from this host. No
host logout/reboot. Do not play local Cedrus video on the projector.

### Trial A: orderly reboot

1. Operator removes board power, serial and USB for at least one minute.
   Host-side serial adapter stays attached to host. HDMI remains connected.
   Operator says `ready`; board stays unpowered.
2. Assistant starts the sole UART reader, using a fresh output directory:

   ```sh
   python3 tools/serial/run-warm-shared.py run --reset orderly --require-video \
     --prepared build/hdmi-warm-shared-repeat-2026-10-24 \
     --output docs/hdmi-evidence/2026-10-24-warm-shared-repeat-orderly
   ```

3. Assistant confirms `OPEN` in events.log. **Only then**, operator connects
   serial to the board first, then mains. Leave board USB disconnected.
4. Runner watches the installed cold boot uninterrupted. Requires one SPL,
   all-zero preboot census, source-3 timing re-latch, handoff, kernel/login.
   Waits for SSH. Checker writes Python and unchanged check-startup.sh only
   under `/run`, runs it, waits for speaker playback, samples audio/video,
   records status/journal. No PCM recording, module loading or service restart.
5. Only if cold digital health passes: record reset intent; send one
   `systemctl reboot --no-block`. Watch for real orderly restart, one warm
   SPL, expected GP6/MIPS/GP7 census; send one autoboot interrupt before logo.
6. At U-Boot prompt: verify bootcmd, read only GP6/GP7/MIPS-status/PPU census
   words; FAT-load the production FIT to RAM `0x50000000`, verify size/CRC.
   YMODEM-load candidate to RAM `0x52000000`, verify CRC; execute **one**
   `source 0x52000000`. No saveenv, media install, or GP6/GP7 writes.
7. Same proven logo -> MIPS -> source 3 -> 720p re-latch -> handoff sequence.
   Require expected UART markers, no extra reset, new Linux boot ID.
   Repeat health checks. Capture start timing from unit properties/journal;
   ~21 s is the prior cold baseline, not a guaranteed warm deadline.
8. Runner leaves board running. Operator reports **both cold and warm**
   picture (moving HDMI / console / logo / black), approximate appearance
   time, correct colour, and audible tone. Digital PASS alone is provisional.
9. With the described trial's approved shutdown, assistant runs once:

   ```sh
   python3 tools/serial/run-warm-shared.py poweroff \
     --output docs/hdmi-evidence/2026-10-24-warm-shared-repeat-orderly
   ```

   Confirm `reboot: Power down`; operator removes power/serial/USB.

### Trial B: SysRq-b

After reviewing trial A, obtain a new `ready` for trial B. Use a fresh cold
cycle and repeat steps 1–9 with output `docs/hdmi-evidence/2026-10-24-warm-shared-repeat-sysrq-b`
and `--reset sysrq-b --require-video` on `run`.

Step 5 changes only: after passing cold health, dispatch the detached guarded
trigger once. It syncs storage, verifies same boot and healthy active HDMI,
writes its marker to `/dev/ttyS0`, then `b` to `/proc/sysrq-trigger`.
UART must show `H713_WARM_SHARED_SYNC_DONE`, `sysrq: Resetting`, exactly one
warm SPL and the expected census. No service-stop or orderly reboot first.
All other transfer, launch, warm digital and operator checks are identical.
The final poweroff uses the trial B output directory.

## Stop conditions and recovery

Any unhealthy baseline, unexpected census/FIT, missed prompt, deadline,
transfer error, extra reset or startup failure stops; no automatic retry,
second source, fallback launch or resume. If stopped at U-Boot, leave it
there and report. If stopped in Linux, leave it running and report.
Do not interpret SSH disconnection as proof of reset; UART is required.

If black: record it even if digital checks pass, stop the trial, and report.
Known recovery is unplugging HDMI **at the projector** then rebooting;
request approval for that separate recovery before issuing a command. A
wedge may need a full cold cycle. Never hold PB5 low manually. No prohibited
register reads/writes or real negative hardware tests.

No full acceptance until repeated warm video + audible audio, including the
abrupt trial, are confirmed. GP6 production guard/health ack and unattended
soak remain future work requiring separate installation/policy approval.
