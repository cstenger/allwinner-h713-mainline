# L3 cleanup deploy, 2026-10-15

This was deployed on boot `618c61bc…` (`update.log`). `update-signal-owner.sh`
installed:
- the wrapper, which writes `OWNED` before the first hold and handles a
  restored-but-unremoved owner;
- the module, which does read-modify-write of R_CPUCFG bit 0 and carries the
  delay-slot comment.

The installed tree verifies, and the running owner is untouched.

**Confirmed on hardware** (cold boot `5a00a2dc…`, untouched):
- **`check-startup.log`:** PASS. The installed signal module's hash
  (`0a6987ce…`) matches the new build, and `start` left both `attempted` and
  `owned`.
- **`stop.log`:** R_CPUCFG `0x07000400` read `0x00000001` while the SCP ran
  and `0x00000000` after `systemctl stop h713-hdmi-signal`. Only the run bit
  cleared, and there was no "other bits changed" warning.
- The stop itself was normal:
  - readback == originals, with SRAM, vectors and SCP restored and the
    client released;
  - DDC back to `io_disabled` (`0xFFFFFF3F`);
  - both modules unloaded, `clients=1`, and the unit `inactive success`.
