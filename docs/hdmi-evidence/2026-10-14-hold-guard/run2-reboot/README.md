# H2 run 2: reboot with retained holds becomes poweroff, PASS

- **Injected boot:** `af897181…`, at about 633 s uptime. `run-hold-failure.sh
  inject reboot` passed the production startup check and started the busy
  recorder; the PCM read `RUNNING`. A **reboot** was requested
  (`inject.log`).
- **Journal of the injected boot** (`injected-boot.extract`):
  - logind logged "System is rebooting".
  - The signal `ExecStop` refused with "capture is open; signal retained".
  - The backend refused to park.
  - There was no restoration and no MIPS park.
  - `systemd-reboot.service` finished, `reboot.target` was reached, and the
    log ends at "Shutting down".

  So the shutdown went all the way through as a reboot. The guard runs after
  journald stops, so its own "reboot refused" line exists only on kmsg and the
  console.
- **Host:** the board was unreachable 1 s after the request. Its `spirits`
  access point was absent from a WiFi scan almost 5 min later. A reboot
  restores the access point in about 40 s, and the host autoconnects to it.
- **Operator:** the lamp and fan went off, the board stayed off, and there was
  no reboot. The guard turned the reboot into lamp-off plus poweroff.
- **Next cold boot** (`b048eab0…`, serial and USB unplugged, at least 1 min
  off): `run-hold-failure.sh verify` passed.
