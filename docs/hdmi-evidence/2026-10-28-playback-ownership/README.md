# HDMI priority and unsupported 640×480 — October 28

**Installed and accepted, with the scope documented below.** Chris authorized
installation and an HDMI video restart, and confirmed the moving pattern,
colours and continuous tone afterward. HDMI priority is active in the installed
launcher/player; 640×480 stays disabled. No reboot or firmware source change
was performed. Sources, tests and verification records are included in the
requested policy commit; no push. [Machine-readable result](ACCEPTANCE-RESULT.json).

Target compile passes with warnings treated as errors. Both staged and
installed direct policy checks and auto/plane/GPU launcher dry runs refuse
local playback before decoding. The video/ring restart recovered HDMI at
59.63 fps with zero rejected frames and capture xruns. All five services are
active with zero automatic restarts. Capture, signal and speaker start times
are unchanged; only ring/video were deliberately restarted. The saved 40 ms
calibration is unchanged. See `installation.txt`, `post-install-health.txt`,
`live-flow.txt`, `final-health.txt` and `operator-confirmation.txt`.

The initial operator observation was the host desktop. A projector-only
host mpv source then supplied the previously validated moving-pattern/440 Hz
tone clip. Its display and audio routing were checked (`host-player-health.json`).
The operator confirmed motion, colours and clear continuous tone. The test
player is now stopped; host projector volume is restored to raw 22937/35%,
unmuted (`cleanup.json`). Board left on. The board clock remains incorrect;
tar emitted future-timestamp warnings during verified extraction. Clock repair
belongs to the separate production cleanup item.

Playback backup: `/var/lib/h713-playback-policy/backup.iw1NyX`.
Video-generation backup: `/var/lib/h713-hdmi-video/backup.qqVRof`.
A host copy of both is saved and fingerprinted in `backups.json`.

## Ownership behavior

`h713-play` calls `gst-plane-play --check-playback-policy` before ffprobe,
DRM queries, the VP9 Cedrus capability probe, route selection or player launch.
The same check runs in direct `gst-plane-play` invocations before GStreamer
initialization. All plane routes, the GPU fallback, forced routes, dry runs
and the later keystone handover inherit this policy. A missing/old plane
player fails closed; install the launcher and player together.

The read-only check refuses when either device-tree HDMI handoff path, any
of the receiver/audio/signal/bridge modules, or the HDMI session state file
exists. Errors other than a missing path also refuse. No MMIO is read, no
decoder is opened, and no firmware calls or service changes are made.
`--playback-policy-version` prints `hdmi-priority-v1` for installation checks;
this metadata-only option does not authorize playback.

The immutable handoff covers startup before the modules load, signal loss,
unsupported input, renderer failure and stopped services. MIPS remains live
through these states. A runtime transition back to local playback has not
been qualified, so HDMI priority covers the **whole HDMI boot/session**.
Unplugging HDMI does not permit local decode; use a normal local-playback
boot with firmware parked. No MIPS parking/source change or bootloader change
is introduced. Session markers intentionally remain a refusal even when
their saved phase is stopped or failed.

This is the supported launcher/player policy, not a kernel ban on decoder
opens. Raw mpv, gst-launch or diagnostic decoder programs bypass it and must
not be used for local decode on an HDMI boot. Manually starting firmware
after a local-playback boot is outside this policy; diagnostics must stop
local players before firmware launch. The production firmware launches in
U-Boot before Linux players exist, and the handoff remains immutable, so a
signal arriving during local playback cannot race this production guard:
local playback was already refused on that boot.

## 640×480

The production ring unit and observation script explicitly pass
`allow_480p=0`. The kernel default was already false; the bridge and EDID
are unchanged. Unsupported 640×480 never makes the udev device ready and
the existing console fallback remains. No 480p enablement is deployed.

## Validation

* `policy-tests.txt`: six tests pass, with 13 implementation mutations caught.
  The real C player is compiled against a fake root; the launcher uses that
  player with command stubs. Tests cover every independent ownership marker,
  stopped/failed sessions and signal states, unknown ownership, early refusal
  across all routes/dry-run, ordinary local route selection and both 480p
  load paths. Mutations happen only in temporary source copies.
* `installer-tests.txt`: all 16 existing fake-root HDMI installer checks pass
  against the newly built video bundle, including backup/update/removal and
  no-write refusals.
* `signal-tests.txt`: existing signal state scenarios and five recorded trace
  replays pass, including unsupported 640×480 and 720p lock/loss. This existing
  fixture intentionally omits zero fields in aggregate initializers; compile
  with `-Wno-missing-field-initializers` alongside `-Wall -Wextra -Werror`.
  An initial attempt without that exception failed on those existing fixtures.
* Native and target arm64 player builds pass `-O2 -Wall -Wextra -Werror`.
  Shell syntax checks and `git diff --check` pass. Staged and installed live
  policy refusals pass, using only read-only checks and launcher dry runs.
  Rootfs creation already copies this C source and launcher and
  compiles the player in the target, so new images include the policy pair.
  The first target staging attempt stopped after successful compilation because
  `file` is absent; the corrected staging script validates the ELF header with
  Python. Both outputs are retained; no installed files changed on that attempt.

Reproduce from repository root:

```sh
python3 tools/video/test-playback-policy.py --mutations
python3 tools/hdmi/build-hdmi-video.py build/hdmi-playback-policy-2026-10-28/hdmi-video
sh tools/hdmi/test-install-hdmi-video.sh build/hdmi-playback-policy-2026-10-28/hdmi-video
cc -O2 -Wall -Wextra -Werror -Wno-missing-field-initializers \
  -o /tmp/h713-signal-state tools/hdmi/test-signal-state.c
/tmp/h713-signal-state
python3 tools/hdmi/test-signal-traces.py /tmp/h713-signal-state
```

## Read-only board preflight and prepared update

`board-read-only-preflight.txt` records boot
`c8f3308e-5c02-4be1-bc0e-3ee5991761e8`, HDMI handoff present, active capture,
ring and video services, and `allow_480p=N`. Target cc and GStreamer/video
1.26.2 development metadata are available. Installed bridge SHA-256
`582d16ac58f325c92b8abafb6d6072fda6fda353515f96ea146de3ae97b0b14e`
matches the host bundle exactly. This preflight captured the pre-policy player
pair; the installation log and acceptance result record the new fingerprints.

Prepared artifact directory:
`build/hdmi-playback-policy-2026-10-28/bundle/`, with player/launcher sources,
the full checksummed HDMI video bundle and an outer `SHA256SUMS`. Its hash
list is retained as `prepared-SHA256SUMS`. The host executable is deliberately
excluded from the board bundle.

Chris explicitly approved the following bounded sequence, now completed.
The exact executed scripts are `compile-and-guard.sh` and `install-policy.sh`;
their output is retained alongside them. The deployment procedure was:

1. Check the prepared manifest, board identity, boot/session and preflight
   file hashes. Transfer the bundle to `/run/h713-playback-policy`; verify its
   manifest again. Refuse an unexpected installed generation.
2. Build `gst-plane-play.c` there with target cc and
   `-O2 -Wall -Wextra -Werror` plus GStreamer/video pkg-config flags. Verify
   `--playback-policy-version`. Test only `--check-playback-policy` and a
   launcher `--dry-run` using a dummy file; both must refuse due to HDMI
   ownership, before decoding. Do not run a real local decoder as a negative
   test. Save compilation and refusal output.
3. Back up both installed playback binaries, ownership/modes and hashes under
   `/var/lib/h713-playback-policy/`. Install the new player and launcher via
   temporary sibling files and rename; keep their executable modes. Recheck
   installed checks/refusals. The pair is also the reproducible rootfs source.
4. Run the existing HDMI installer `--dry-run --update`, then `--update` from
   the bundled `hdmi-video` directory. It backs up the previous full video
   generation and maintains its recorded copies/checksums. This briefly
   stops/restarts the video consumer and ring to apply explicit 480p disable;
   capture/signal/audio owners and the saved 40 ms setting are untouched.
5. Read back `allow_480p=N`, installed hashes, service health, frame rejects
   and audio xruns. Ask the operator to confirm normal picture/sound. No
   reboot or firmware source/parking operation belongs to this sequence.

A real local-playback boot and a physical 480p source test are not included
in this acceptance sequence; those remain separately qualified by the offline
route/state tests and existing signal traces. Report this boundary explicitly.

Rollback: restore the prior launcher/player pair and prior complete video
bundle from their backups, verifying fingerprints. The old pair lacks the
HDMI guard, so never exercise local playback on an HDMI boot after rollback.
Use the existing video installer's `--update` with the previous generation;
do not hand-edit its recorded manifest. Preserve the receiver/signal/audio
owners and saved calibration throughout.
