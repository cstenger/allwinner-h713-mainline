# Historical panel bench scripts

The five scripts here are byte-for-byte text snapshots of earlier October
16/17 experiments. [manifest.json](manifest.json) records the original paths,
lengths and SHA-256 values, verified against the prior untracked-file inventory.
They are non-executable evidence, not current experiment launchers.

| Snapshot | Review finding |
| --- | --- |
| `pl6-restart-trial.sh.txt` | Unbinds display, remounts read-only through SysRq and cuts PL6 core rails; waits for SSH indefinitely and masks the cut command's error |
| `warm-reboot-trial.sh.txt` | Reboots and reads registers using fixed hardware paths; appends into existing directories, lacks a serial-child cleanup trap and waits for recovery without a deadline |
| `source-away-trial.sh.txt` | Sends an interpolated source argument to the board, stops owners and invokes the old reboot wrapper; pipelines can mask SSH failures |
| `rdomain-snapshot.sh.txt` | Reads broad PPU/R_CCU/R_PIO ranges using devmem without a current per-register power/read-safety proof; not a reusable allowlist |
| `catch-uboot-warm-path.py.txt` | Writes RTC GP6 to force the warm path; has no exact U-Boot identity/readback authorization gate, unbounded initial waits, and descriptor leaks on reconnect/setup errors |

These findings are why the one-session wrappers were archived rather than
promoted unchanged. Historical results belong with the original trial records,
not a new pass claim. Local original copies are retained under
`build/panel-bench-review/originals/`.

Current reviewed bench modules and the receiver wrapper are described in
[panel-bench-tools.md](../panel-bench-tools.md). Normal build and recovery
instructions remain in the [panel runbook](../uboot-panel-initial-state.md).
No script here was executed during cleanup.
