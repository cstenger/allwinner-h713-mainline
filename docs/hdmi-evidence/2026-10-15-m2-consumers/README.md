# M2: user-session capture consumer at shutdown, plus the stop race, 2026-10-15

**Result: PASS.**

**Deploy** (boot `534aa29d…`, `update.log`): `update-signal-owner.sh`
installed the M2 wrapper. A read-only check of its helpers on the board
resolved the capture device `/dev/snd/pcmC1D0c`, found no holders, and
reported `shutting_down` as False.

**Injection** (`run-hold-failure.sh consumer`, `inject.log`):
- The production check passed and the `no-reclaim` bench knob was absent.
- `pw-record` ran as `media` against WirePlumber's default HDMI source,
  ordered `Before=h713-hdmi-signal.service`. The PCM was `RUNNING`, and its
  only holder was the user's **`pipewire`**.
- The poweroff was requested at 04:07:05. The board was unreachable from
  04:07:08.

**Shutdown journal** (`injected-boot.extract`):
1. The signal `ExecStop` logged `shutdown: closing HDMI capture consumers
   [328]`, the PipeWire daemon. It released on SIGTERM without needing
   SIGKILL, and `pw-record` exited.
2. With the capture device held exclusively, the module stop completed with
   no exception or error. The readback equals the originals, then SRAM,
   vectors and SCP were restored and the receiver client released. DDC
   returned to `io_disabled` (`mux ffffff, original ffffff`), and the unit
   stopped cleanly.
3. The backend restored 22 DSP and 15 TVFE words, parked MIPS, and removed
   the receiver. Then systemd powered off.

**Next cold boot** (`595ea002…`): `run-hold-failure.sh verify` PASS
(`verify.log`, `next-boot-check.log`).

Before M2, the same consumer made the stop refuse, which ended in an
unparked, guard-protected poweroff (H2 run 1). Now the shutdown reclaims the
consumer and tears down cleanly. On a running system the stop still refuses
while anything is capturing.
