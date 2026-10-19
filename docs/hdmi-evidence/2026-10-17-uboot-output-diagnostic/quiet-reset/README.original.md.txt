# Panel reset with LVDS output quiet, supply held on

Same U-Boot-only black state as prior isolated LVDS restart failure (lvds-only/attempt4). User authorizes no panel power cycle, HDMI attached, no Linux, timing snapshots before/after every step.

Plan: same four output-rest groups,20ms settle, PH16 assert, hold>=1s with snapshot, PH16 release,25ms settle, same four output restores. PF6 never written and must read high at every boundary. MIPS reset remains asserted. PH16 returns high before restoring outputs. No TCON timing/latch writes, PLL/clock changes, FIFO resets, firmware reload or SoC reset. Per-step timing/ownership/GPIO snapshots captured. Output values saved/validated before changes and restored on error; PH16 released on error.

Pending visual outcome; capture remains in parent serial logs.

Execution completed: ten staged operations with before/after snapshots each. No TCON timing/control readback changes at any step, all720p retained. PF6 high at every sampled boundary; PH16 low during assert/hold and high after release; MIPS reset/status0 throughout sampled boundaries. Saved output controls fully restored, final PH16 high. No supply write, reboot, Linux boot, clock or firmware change. Awaiting visual result.

## Result: BLACK

Operator report received 2026-10-17T23:13:13.389613-07:00: still lit but black; HDMI remains connected at both ends. Quiet-lane reset with supply ON did not recover. Output rest/restore alone previously failed on same black session. All timing readbacks720p throughout both tests. No subsequent writes; preserve black.

Next proposed test: repeat the same orderly output rest/reset hold, ADD a3s PF6 off/on interval, then release reset/restore outputs, capturing timing before/after every step including supply off and supply on. No preceding TCON/FIFO writes; capture actual first720p->1080p transition if any. Physical supply voltage is not measured; GPIO switching alone does not prove full discharge. This supply-cycle operation has not yet been executed on this black session and requires authorization distinct from the completed supply-on reset test.
