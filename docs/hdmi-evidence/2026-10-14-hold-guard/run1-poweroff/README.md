# H2 run 1: poweroff with retained holds, PASS

- **Injected boot:** `9ce0916d…`, at about 1385 s uptime. `run-hold-failure.sh
  inject poweroff` passed the production startup check, then started
  `h713-h2-busy-pcm` (an arecord ordered `Before=h713-hdmi-signal.service`).
  The PCM read `RUNNING`, and the poweroff was requested (`inject.log`).
- **Journal of the injected boot** (`injected-boot.extract`):
  - The signal `ExecStop` refused with "capture is open; signal retained",
    and the unit was marked failed.
  - The recorder was stopped afterwards.
  - The backend refused with "signal owner/helper must restore and stop
    before backend shutdown".
  - There was no restoration and no MIPS park.
  - `systemd-poweroff` finished and reached "Shutting down".

  The guard's own line went to kmsg and the console after journald stopped,
  so it is not in the journal.
- **Host:** the board was unreachable 3 s after the request and stayed down
  for more than 3.5 min, with no reboot and no watchdog reset.
- **Operator:** the lamp and fan went off, and the board stayed off.
- **Next cold boot** (`af897181…`, serial and USB unplugged, at least 1 min
  off): `run-hold-failure.sh verify` passed (`next-boot-check.log`).

This is the first unparked poweroff: MIPS was live, the receiver held, and
the SCP payload was still running. It is safe, and a cold cycle fully
recovers it.
