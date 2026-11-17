# Speaker pop baseline — 2026-11-17

Phase 0 of [the speaker power plan](../../speaker-power-plan.md), on the
installed 0210 kernel (boot `a2cb8f4b-0f0a-4a92-9f20-7174dbaf7a1e`). No board
files were changed. Every test was ended with `h713-hdmi-speaker` active and
standby `off`.

## Rig

- **Recording:** a microphone on Scarlett 2i2 input 1, next to the
  projector's speaker. 48 kHz, gain fixed for every run.
- **Tool:** [`tools/audio/pop-capture.py`](../../../tools/audio/pop-capture.py).
  Every 2 ms, a board monitor logs the PA line (PL2), the DAPM `Speaker`
  widget and the codec PCM state on `CLOCK_MONOTONIC`. Clock offset comes
  from a minimum-RTT ping (1.6 ms RTT).
- **Score:** 1 ms RMS blocks above 6 kHz, divided by the larger of the
  medians over the preceding and following 150 ms. Flag at 3.5.
- **Timing:** arecord starts about 22 ms after its timestamp, so peaks appear
  22–25 ms early relative to board marks.
- **Recordings stay private.** Only their SHA-256 (`*/mic.wav.sha256`),
  scores and board logs are kept here.

## Controls (`run-ctrl2`, `run-ctrl3`)

| Signal through PipeWire | Scores | Flagged |
| --- | --- | --- |
| Quiet room, fan on | 1.9–2.6 | 0 |
| 0.5 FS single-sample impulse | 3.9, 4.6, 4.1 | 3/3 |
| −20 dBFS 1 kHz cosine onset, 0.1 FS DC step | ≤ 2.1 | 0/8 (below the fan) |
| −20 dBFS tone with 50 ms fades | ≤ 2.1 | 0/4 |

The fan sets the sensitivity limit: about a 0.5 FS impulse with the fan on.
With the fan off (standby), the same pops score 2–3× higher.

## Results

**1. Every HDMI speaker stop pops** (`run-base1`, `run-mute`): 3.4–10.1,
flagged 8 of 9. In standby with the fan off, the pop is +31–40 dB above the
room in the 0.4–6 kHz bands. Starting the speaker never pops (PA rises 700 +
200 ms after the analog power-up).

**2. It is not sample content.** The loopback carries digital zero (HDMI
silent). Setting `DAC Playback Volume` to 0 before the stop still pops
(9.2, 10.1).

**3. It is the module clock stopping while PA winds down** (`run-drop`,
`run-gap`, `run-gapsb`). `pcm-drop-close.py` separates trigger STOP (PA
low, clock running) from close (`sun4i_codec_shutdown()` disables
`clk_module`):

| STOP → close gap | Fan on | Fan off (standby) |
| --- | --- | --- |
| 0 ms (service stop is like this) | 3/3 (3.5–5.2) | 3/3 (8.9–10.9) |
| 10 ms | 2/3 | — |
| 30 ms | 0/3 | faint at close 3/3 (3.0, 3.0, 4.1) |
| 100 ms | 0/3 | 0/3 |
| 300 ms | 0/3 | 0/3 |
| 1–3 s | 0/4 (`run-drop`) | 0/3 |

Each peak lines up with the close mark (−22 to −25 ms, the arecord lag), not
the drop. STOP alone (PA falls, clock running) was silent in every trial,
including PipeWire's restart blips.

**4. No measurable idle hiss.** In standby with the fan off, the room reads
−42.3 dBFS with PA up and −41.7 dBFS with it down (`run-base1`). The 6 kHz+
band is −54.7 vs −54.8 dBFS.

## Consequences

- Any close of the codec PCM pops today. That happens whenever the HDMI
  speaker service stops: at power-off and reboot, and whenever its `BindsTo`
  HDMI services stop. It also happens when PipeWire releases the sink after
  its last stream, if nothing else holds it.
- The clock must stay running for at least 100 ms after PA falls. Use ≥ 300 ms
  as the margin.
- Side finding: every speaker start goes PREPARED → RUNNING → XRUN → RUNNING
  within about 50 ms. PA is still down then, so it's inaudible, but it is a
  startup underrun.

## Not covered

mpv, plane route and Kodi start/stop. While the loopback runs, those mix into
an already-running sink, so they have content edges only. Also not covered:
power-off, reboot and cold boot (need Chris present, or a warm reboot that
risks the display).

## After 0212 (same day)

Kernel 0212 (one speaker power state) and 0211 (NSI node disabled) were
installed with the guarded FIT installer. Before that, both ran in a
fake-root rehearsal: preview, apply, and a byte-exact rollback. The board was
then rebooted twice.

- **Build:** the baseline release build reproduced the installed FIT
  `845494c3…` byte for byte. The candidate FIT is `966eba3c…` (7,615,588
  bytes), with an unchanged config, `Module.symvers` and release. The only DT
  change is the NSI `status` ([bundle manifest](bundle-manifest.json)).
- **Install backup:** `/var/lib/h713-hdmi-startup/kernel-fit-274682e45daf4603a1f85d6ab959a221`
  ([summary](install-summary.txt)). The previous `h713-standby` is kept at
  `/var/lib/h713-standby-backup/h713-standby.pre-0212`.
- **Boots:** `67adc812` (first 0212 boot), then `3374b49b`. Startup PASS,
  health ack dry-run unwritten, zero failed units, ext4 errors 0, CPU_COMM
  IRQ-only, `Speaker Power` = 1, PA high.

### Matrix (`run-post1`, 50 steps)

| Event | Count | Flagged | Max score |
| --- | --- | --- | --- |
| Positive control: 0.5 FS impulse | 3 | **3** | 3.7–4.6 |
| HDMI speaker stop / start, fan on | 5 / 5 | 0 | 2.2 |
| Raw PCM close right after STOP (`gap0`), fan on | 3 | 0 (was 3/3) | 2.2 |
| 44.1 kHz stream (rate-change quiet window), fan on | 3 | 0 | 2.1 |
| `Speaker Power` 0 / 1, fan on | 3 / 3 | 0 | 2.3 |
| `Speaker Power` 1 / 0 in standby, fan off | 4 / 3 | 0 | 2.7 |
| HDMI speaker stop / start in standby, fan off | 3 / 3 | 0 (was 2/2) | 2.8 |
| `gap0` and 44.1 kHz in standby, fan off | 2 + 2 | 0 (was 3/3 at 8.9–10.9) | 2.4 |
| `h713-standby` on / off | 3 / 3 | 0 | 2.6 |

The fan-off quiet floor in the earlier runs was 2.5–2.7. On this run, the
PA line moved only at the intended points:
- `Speaker Power` 0: PA falls within 12 ms.
- `Speaker Power` 1: PA rises after 711–732 ms (700 ms settle).
- Standby enter: PA falls about 275 ms in, after the players stop.
- Standby leave: PA rises about 1.28 s in, after the lamp ramp.
- First 44.1 kHz stream, and the return to 48 kHz: one PA cycle each
  (low, clock change, high after about 1 s).

Stream starts, stops and closes never moved PA.

### Reboots (`run-reboot1`, `run-reboot2`)

- **0210 → 0212:** one pop (10.5) during the old kernel's way down. The
  `systemd-run --on-active=1` timer fires up to a minute late, so the exact
  stage isn't known. The new kernel's boot and speaker power-up are silent.
- **0212 → 0212**, with UART timestamps: shutdown (about 51–61 s), reset,
  U-Boot (61.6 s), kernel (69.4 s) and speaker power-up are all silent. The
  maximum over 115 s is 2.4.

### Still not covered

- Cold power-on and power-off from the mains (needs Chris at the board).
- A listening pass by ear.
- mpv, Kodi and plane-route content edges. Those are content, not power
  edges: samples that stop at a non-zero level still click.
- Suspend (s2idle) is opt-in and was not exercised.
- Rate changes cost about 1 s of silence at the start of the first stream
  in the other family. PipeWire runs at 48 kHz, so only raw-ALSA 44.1 kHz
  clients pay it.

### Mains power cycle (`run-cold1`)

Run on 0212: `systemctl poweroff` over ssh, then serial, USB and mains
unplugged, then power restored. Chris reports hearing nothing. The board
came back as boot `b6546bcc` (startup PASS, nothing failed, lamp on, PA
high).

The board's journal and uptime map onto the recording as follows. `board.log`
holds these as approximate phase markers; there was no UART.

| Phase | Recording time | Max score | Verdict |
| --- | --- | --- | --- |
| `poweroff`, 0212 shutdown (PA off, then clock), power cut | 10.6–18 s | 3.2 | clean |
| Board off, cables and mains handled | 18–41 s | 14.9 | handling: the board was unpowered |
| Power restored (SPL about 42.7 s) | 41.2 s | 20.4 | spectrum and length match the handling event, not a speaker pop |
| Kernel boot | 50.5 s | 2.9 | clean |
| Codec probe and PA up (about 55 s) | 54–58 s | 2.9 | clean |
| Speaker service and after | 58.8 s on | 9.3 | 76.7 s and 115.9 s are long low-mid bursts (speech or handling); 65.2 s is a 15 ms blip with energy only at 3–6 kHz |

Reference shapes:
- A known speaker pop (fan off) is 10 ms, +8 to +13 dB at 1.1–6 kHz, with
  nothing above 6 kHz.
- The power-on event is 170 ms long, +20 dB at 3–6 kHz and +13 dB above
  6 kHz, the same shape as the cable handling at 25.1 s.

Chris confirms that every flagged event in this run is his own typing or
handling of the microphone. None came from the speaker, and none was audible
from it.

**Result: the mains power cycle is pop-free on 0212**, through power-off,
the 0212 shutdown, power-on, boot and amp power-up. That matches the
microphone and the listening check. One limit: mains was off for only about
25–30 s, not a minute or more.
