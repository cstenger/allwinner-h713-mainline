# Deploy of the readback-verified signal owner, 2026-10-14

**Result: PASS.** The H1 signal owner (build-id `166a2ca8…a9d9`, commit
`2893e3c`) is installed and starts automatically on cold boot.

## 1. Update (boot `76e0c300…`, operator cold boot)

The bundle was `build/hdmi-startup-signal-owner` from `build-startup.py`;
`bundle-SHA256SUMS` records it. `update-signal-owner.sh` did the following
(`update.log`):
- verified the bundle and the installed generation;
- confirmed every out-of-scope file is byte-identical;
- replaced only `h713-hdmi-signal.ko`, `h713-ddc-pins.ko`,
  `h713-hdmi-signal.py`, its own script and `SHA256SUMS`;
- kept the previous files in
  `/var/lib/h713-hdmi-startup/signal-owner.20260413T193913` (the board's RTC
  reads April).

The installed tree then verified. The running owner was untouched: it was
still the old build-id `d55db279…`, with the unit active.

## 2. Poweroff after the update

`deploy-boot-shutdown.log` shows the new wrapper's `ExecStop` restoring the
**old** in-memory module (the stop protocol is unchanged). After that:
1. the DDC pins returned to inputs;
2. the signal unit stopped cleanly;
3. the backend restored 22 DSP and 15 TVFE words, parked MIPS, and removed
   the receiver;
4. the board powered off.

The board was unreachable 3 s after the request and stayed down. The operator
confirmed lamp and fan off.

## 3. Unattended cold boot (boot `9ce0916d…`)

Serial and USB were unplugged, power was off for at least 1 min, and nobody
touched the board. Results:
- `check-startup.sh` **PASS** at 48 s: handoff verified, both units active,
  DSP 0/0 → 1/1, receiver `clients=2`, signal `ready=Y failed=N restored=N`.
- The loaded signal build-id is `166a2ca8…`, the new owner
  (`verify.log`).
- At ready, the readback area was intact (all `ffffffff`).
- The originals and the active snapshot match the earlier bench run exactly.
- dmesg has no warnings.
- The host `card1-HDMI-A-1` reads `connected`, with an EDID byte-identical to
  the fixture.

**Rollback:** copy the three files back from the `signal-owner.*` backup
directory, then cold boot.

**Not yet seen on hardware:** a stop of the new module from the *installed*
unit. The bench run covered the same wrapper and module through a drop-in.
That stop will happen at this board's next shutdown.
