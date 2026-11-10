# T2: NRWinNode::WriteReg mask trace, live (10-23)

The trial proper `cb8e417a…` (installed reset-controls build + patch 0002)
was installed with `t2.sh install-dry` then `install`
([install.txt](../t2-preparation/install.txt)). Then: an orderly poweroff, an
operator cold boot (serial and USB unplugged, ≥ 1 min off, HDMI connected),
boot `7730adf2-2622-46c0-becf-9ac310ae6d04` with the handoff present.
Afterwards it was rolled back to `1b1f702f` and verified
([rollback.txt](rollback.txt)). Samples are in [samples.txt](samples.txt);
the trace after host output off and on is in `after-off.json` /
`after-on.json`.

## Every NRWinNode::WriteReg call in the boot

| # | When | Mask | `m_afbd_source_mode` | Log context |
| --- | --- | --- | --- | --- |
| 1 | firmware init, before `AppTopSetSource` | `0xffffffff` | 1 | `UpdateWce`, `refresh_node:2` |
| 2 | firmware init | `0xffffffff` | 2 | `UpdateWce`, `refresh_node:1` |
| 3 | HDMI lock (port 3 → 5, uptime 19–23 s; log tick 23211) | **`0x00000100`** | 1 | `CallbackOfSignalChange`, `UpdateWce`, `refresh_node:0` |
| 4 | re-lock after host output off/on | **`0x00000100`** | 1 | same |

* Signal loss caused no WriteReg.
* The frame programmer's last record stayed `6103`, mask `0xffffffff`,
  **mode 2**.

**Result (row 1 of §10.8):** an HDMI lock only does a partial window refresh
(`refresh_node:0`, mask `0x100`), so the AFBD source-0 programmer never runs
in capture mode. The last full refresh at init is the decoder one
(`refresh_node:1`, mode 2), so AFBD is left in decoder configuration.

**Stock comparison** (10-07 `final-elog`): the order is the same. The last
full refresh before HDMI was `refresh_node:1` with mode 2 (decoder signal,
187356), and the HDMI lock was `refresh_node:0` with mode 1 (290061). So
stock's lock didn't reprogram AFBD through this path either, yet stock
showed HDMI. Whatever made stock's picture visible is not the lock-time
`WriteReg`; that remains open.
