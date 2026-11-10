# M1 wrapper deploy, 2026-10-15

This was deployed on boot `b048eab0…`, the clean cold boot after H2 run 2,
with the new signal owner running. `update.log` records what happened:

- `update-signal-owner.sh` replaced the wrapper. The backup is
  `signal-owner.20260413T202144.12k4Et`.
- The installed tree verified, and the installed wrapper matches the bundle.
- The running owner was untouched: the unit is active, with build-id
  `166a2ca8…`.

This boot was started by the previous wrapper, so only `owned` exists, not
`attempted`. The new stop handles that, using `missing_ok`.

The normal start and stop path of the new wrapper runs at the next shutdown
and cold boot. The M1 refusal branch is host-verified only; see the review,
M1.
