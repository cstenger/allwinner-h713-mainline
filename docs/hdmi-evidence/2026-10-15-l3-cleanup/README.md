# L3 cleanup deploy, 2026-10-15

This was deployed on boot `618c61bc…` (`update.log`). `update-signal-owner.sh`
installed:
- the wrapper, which writes `OWNED` before the first hold and handles a
  restored-but-unremoved owner;
- the module, which does read-modify-write of R_CPUCFG bit 0 and carries the
  delay-slot comment.

The installed tree verifies, and the running owner is untouched.

The new module first runs at the next boot, and its R_CPUCFG path at the
stop after that. Confirm both by checking that the stop restores normally
and that there is no "R_CPUCFG other bits changed" warning.
