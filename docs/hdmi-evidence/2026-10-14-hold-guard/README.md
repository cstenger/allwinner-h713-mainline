# H2 shutdown hold guard: deploy and live dry run, 2026-10-14

The guard was deployed on boot `9ce0916d…`, the post-deploy cold boot, while
the new signal owner was running. The bundle was
`build/hdmi-startup-signal-owner` after the H2 changes.

- **`update.log`:** `update-signal-owner.sh` installed:
  - `h713-hdmi-hold-guard`, into both the bundle and
    `/usr/lib/systemd/system-shutdown/`;
  - the updated `install-startup.sh` and the updater itself.

  The backup is in `signal-owner.20260413T195541.f4nLWy`. The installed tree
  verified, the hook copy matches the bundle, and a second run reported
  "already current". The running owner was untouched (build-id `166a2ca8…`).
- **`live-dry-run.log`:** the real installed guard ran against the real
  `/sys/module`, with lamp-off and poweroff replaced by `echo`.
  - It named the four loaded holds: `h713_hdmi_signal h713_ddc_pins
    h713_hdmi_audio h713_hdmi_receiver`.
  - On `poweroff` it logged only.
  - On `reboot` it logged "reboot refused … powering off", then called
    lamp-off `poweroff` and the poweroff command.

Not yet exercised: the guard inside a real systemd-shutdown. Bench runs 1 and
2 in [the review](../../hdmi-signal-review.md) (H2) cover that.
