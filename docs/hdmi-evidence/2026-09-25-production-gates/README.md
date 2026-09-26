# Production-gate evidence, 2026-09-25

This directory records bounded board-B runs against Linux 6.18.38
`#1 SMP Thu Sep 24 01:45:24 PDT 2026`. The HDMI source used the deterministic
256-frame, 60 Hz motion pattern at 640×480. All runs released HPD and restored
the panel console. The board was finally returned to the original U-Boot
proper image, SHA-256
`47ebcfa6dbfd646b2eab83fc1e5206086a2a1226cb5d840512051cbbf6e9e95d`,
with MIPS alive, source 3 verified, `/dev/video1` using full verification, and
the SCP probe absent.

## Gate 1 repeat

The `gate1-full` and `gate1-sparse` directories are the exact logs from:

```sh
python3 tools/hdmi/run-panel-preview.py --input-api read --display-fps 20
python3 tools/hdmi/run-panel-preview.py --input-api read --display-fps 20 \
  --sparse-verify
```

Both 120-frame runs exited successfully and restored framebuffer ID 40 and
AFBD scanout control `0xffc00000`. Full verification delivered about 15 fps;
sparse verification delivered about 31 fps. No new time-aligned optical clip
was recorded, so the visual part of gate 1 remains open despite the successful
software and restoration evidence.

## Gate 2 completion correlation

The temporary U-Boot proper candidate changed 273 bytes, all inside one
existing 672-byte MIPS patch table. Its input/output hashes and unchanged
relocation census are in `gate2/candidate-manifest.json`. SPL was never
written. `gate2/emulator.log` records all eight event-mask cases passing with
all general-purpose registers and the stack pointer preserved.

Two bounded motion trials then sampled only reserved trace DRAM and sparse
pages in the known frame ring; ARM never read capture-domain registers. The
second trial bracketed each Y/UV pair separately. Its analyzer result is
`gate2/trial2/analysis.json`:

- 480 `cap-vde` and 480 `cap-vs` events in 8.003 seconds;
- zero mode-change events;
- 481 observed write epochs, each changing exactly one Y/UV pair;
- 480/480 contiguous pair transitions followed `0→1→2`, with no errors;
- all 481 epochs shared one stable counter-to-pair phase offset (zero in this
  particular boot; later testing showed the absolute offset is boot-specific);
- `cap-vde` always preceded `cap-vs`;
- 111 stable hash windows fit between VDE and VS, with zero ring changes.

Thus `cap-vde` is the earliest observed safe completed-pair boundary;
`cap-vs` is a later redundant boundary. The compressed JSONL inputs are kept
beside the analysis. Their SHA-256 values are:

```text
3034da0f274373a5211897a551ab6f23b6f432a4b9f23fbb2b7197cbd65d5251  trial1/cap-ring.jsonl.gz
117e430271c8f88a689e1dcf2958efd9fab3a4fbd95fc26513508c359211d1bf  trial2/cap-ring.jsonl.gz
```

## Event-gated V4L2 prototype

The tested bridge consumed only on the proved VDE counter, bootstrapped the
rotating producer pair from ring changes, retained source-sequence gaps, and
exposed produced/delivered/overwritten/rejected counters. Follow-on work keeps
the learned per-boot phase across stream reopen so a static stream does not
need to rediscover it. The bridge refuses to bind unless the guarded mailbox
and exact VIncap hook words are present.

The full-plane oracle run (`gate2/event-full`) captured 120/120 valid moving
frames with zero band or stripe mismatches and zero rejected or unstable
copies. It counted 162 produced, 121 delivered, and 41 overwritten frames;
the diagnostic double-read cost about 20.4 ms per copy.

The sparse run (`gate2/event-sparse`) counted 121 produced, 121 delivered,
zero overwritten, zero rejected, and zero unstable. Its 120 captured frames
had zero skipped IDs and zero band or stripe mismatches; one duplicate ID came
from the source presentation. Copy plus sparse verification averaged about
8.0 ms. The large raw streams remain in `/tmp`; their hashes are recorded in
`gate2/capture-sha256.txt` rather than committing 148 MB to Git.

These results validate the completion mechanism and show 60 Hz capture at the
existing signal in sparse mode. They do not yet establish a 60 Hz panel path,
native 1280×720 input, optical latency, hardware-validated static-image
startup, or long-duration disconnect/restart endurance.

Follow-on testing found that this run's zero counter-to-pair offset is not
universal across boots. The bridge now learns a boot-specific phase and has
passed bounded static-source reopen and moving reconnect tests; see
[the September 26 evidence](../2026-09-26-static-restart/README.md).
