# `dtv get_fb` — a shell-reachable path into `GetFrameInfo`

Static RE. Found by pulling the device-framework thread left open in
[viddec-stm-live-state](viddec-stm-live-state-2026-09-05.md).

## The chain

The shell's top-level `dtv` command (handler `0x8b146ad4`, entry at
`0x8b20dd60`) has a subcommand table at **`0x8b1f8a70`**:

| subcommand | handler | help |
| --- | --- | --- |
| `dtv set_ds` | `0x8b14806c` | `set dtv stop` |
| **`dtv get_fb`** | **`0x8b147fc4`** | **`get dtv frame info`** |

`get_fb` does:

```
jal  0x8b184334          ; device-manager getter
a0 = v0 ; v0 = [v0]      ; its vptr
a1 = 1
v0 = vptr[0x0c]          ; slot 3
jalr v0                  ; GetDevice(1)   <- 1 == VideoDecoder
...
a0 = result ; v0 = [a0]
v0 = vptr[0x38]          ; slot 14
jalr v0  (a1 = -1)       ; THidTVPro slot 14
```

and `THidTVPro` slot 14 (`0x8b14713c`):

```
a0 = [self + 0x5a8]      ; the CVidDecSignalDetector
v1 = (a1 < 4)            ; bounds-check the slot index
v0 = [a0]                ; detector vptr
v0 = vptr[0x18]          ; slot 6 = GetFrameInfo
jalr v0 (detector, sp+0xbc, index)
```

**So `dtv get_fb` makes the firmware read the VideoInfo descriptor out of the
AFBD slot registers and report it.** Passing `-1` fails the `< 4` test and takes
the all-slots path at `0x8b1471b4`.

`0x8b184334` is the **device-manager getter** — the framework the earlier caller
hunt was missing, and the thing that presumably also drives the STM.

## Why this matters

It is the first way found to make the firmware *read our frame info on demand*,
from outside, with no code change:

- it proves or disproves that `GetFrameInfo` accepts our descriptor, using the
  firmware's own validation rather than our reading of the disassembly;
- it exercises the exact read path the signal state machine depends on;
- its output is the firmware's own parse of the 144 bytes, which cross-checks
  the descriptor decode.

It does **not** by itself run the state machine — that is `THidTVPro` slot 16,
still uninvoked. But if `GetFrameInfo` succeeds here while the STM stays idle,
that isolates the remaining fault to the poll alone.

## How to run it

Requires the full live-core setup: `h713_disp init 0x34`, the DECD FIT, a frame
submitted with `ring_writes_max=1` so the ring is populated without the 60 Hz
rewrite, then over the ARM-side pump:

```
mips-shell.py --cmd "dtv get_fb"
```

Watch both the shell reply and the elog `dtv`/`vdd` tags, and check the
detector's buffers at ARM `0x4b830ea8 + 0xb0` for a non-zero latch — the tighter
signal noted previously. Note the object addresses are per-boot; re-read the
singleton at ARM `0x4b27266c`.
