# Candidate h713-hdmi-signal lifetime cycle (H1 readback), 2026-10-14

**Result: PASS.** One load → stop → rmmod cycle of the candidate module
(build-id `166a2ca8…a9d9`, payload `--verify-restore`) on a normal automatic
cold boot. The procedure was [hdmi-signal-lifetime-bench.md](../../hdmi-signal-lifetime-bench.md),
and boot `771d1181-8059-4a81-b960-35b79460cf2f` was operator power-cycled.

- **Gate:** `check-startup.sh` passed at about 60 s uptime. The installed owner
  (build-id `d55db279…52cb`) stopped cleanly through its unit: `inactive
  success`, both modules gone, receiver `clients=1`.
- **Swap:** the candidate started through a runtime drop-in. It reached
  `ready=Y failed=N restored=N` with `clients=2`, DDC held, and the loaded
  build-id equal to the candidate's. All 8 readback words were still
  `ffffffff` at ready, and the originals matched the known-good probe values.
  The active snapshot matched the bounded-probe evidence exactly.
- **Source side (host `card1-HDMI-A-1`):** while the candidate held the signal,
  the host read `connected` and a 256-byte EDID byte-identical to
  `tools/hdmi/fixtures/hdmi-audio-edid.hex`. After stop it read `disconnected`.
- **Stop:** status `marker=48444d49 ready=48444d49 exception=0 error=0
  done=48444d49`. **Readback equals the originals for all 8 registers:**
  `1014=00000007 1b00=00a0a0a0 1b04=07000000 1b08=00606060` and IO
  `1020/1030/1034/1038=0`. SRAM and vectors were restored, the SCP stopped,
  the client was released, and the DDC helper logged a successful idle
  restore. The unit ended `inactive success` and `clients=1`, with no
  `WARNING`, `BUG` or `Oops` in dmesg.

**Not exercised:**
- the tone-capture test (optional; skipped);
- a readback mismatch on hardware (host-simulated only);
- a second cycle in one boot;
- poweroff from this state;
- H2.

Files:
- `target/<boot>/`: `swap.log`, `stop.log`, `check-startup.log`, and the dmesg
  excerpt from each phase marker.
- `manifest.json` and `SHA256SUMS`: the staged bundle.

## Poweroff from the post-stop state

Pre-check (uptime 2136 s):
- capture backend active, signal unit inactive;
- no signal, DDC or probe module loaded;
- receiver `shutdown_ready=Y`, `clients=1`;
- PCM closed.

`systemctl poweroff --no-block` was requested at 21:07:40, with a
`h713-signal-lifetime: operator-watched poweroff requested` kmsg marker. The
board was unreachable from 21:07:46, and its access point stayed gone through
21:10:44 (about 3 min): there was no reboot. The shutdown journal for this
boot is persistent; read it with `journalctl -b -1` on the next boot.

Lamp/fan: **the operator confirmed both went off and the board stayed off.** This
is the same parked-poweroff path as `2026-10-14-normal-startup/poweroff-1/`, reached
after a candidate-module lifetime.
