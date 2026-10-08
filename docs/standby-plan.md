# Standby: plan (2026-10-07)

> **Status 2026-10-07: Phases 1 (inputs) and 2 (software standby) DONE,
> verified on the bench board. Next: Phase 3 (s2idle).**
>
> Phase 1:
> Kernel 0169–0173 from a cold boot, no userspace setup: the case button
> sends `KEY_POWER` (3/3 presses), and every remote key arrives as its
> keymap code — POWER 116, UP 103, mirror 149, input 202, mouse 148,
> mute 113 — and the board stays up (logind ignores the key).

## Phase 1 findings (2026-10-07)

- **The remote is NEC, address 0x00**, and every code matches stock's
  `customer_ir_ff00.kl`. Nothing decoded before 0169: `sunxi-cir` stored the
  sample period as whole microseconds, and at our 24 MHz clock 2.667 us
  became 2, so every pulse arrived at 0.75x. The keymap is
  `rc-hy200-projector` (0172). Inherited 0021 then wrote a vendor
  CIR_CONFIG (`0x00200b2a`, a /256 sample clock) after the rc core had set
  /64, so with the keymap the remote was dead from boot and would have died
  after every resume; 0173 drops that write. A/B on the remote: `0x2d04`
  gives an 8943/4462 us leader and decodes, the vendor value gives exactly
  1/4 of that and nothing.
- **The case button pulls PL4 low**; the board pulls it up. Three presses
  gave clean 215-290 ms pulses, no bounce.
- **No GPIO interrupt on this SoC had ever fired.** Stock's pinctrl is
  `SUNXI_PCTL_HW_TYPE_1` (the layout our drivers already select) with the
  IRQ function at mux **0xE** on every pin; our tables said 0x6 and patch
  0004 skipped the mux switch. Measured: in gpio_in, 6 level changes and 0
  interrupts; at 0xE the first press delivered `KEY_POWER`. Fixed by 0171.
- **logind powers off on `KEY_POWER`** by default, which is how that first
  press shut the board down (journal: `Power key pressed short.` ->
  `Powering off...`). The rootfs now sets `HandlePowerKey=ignore`.
- **Linux power-off does not turn this board off.** After it, the power LED
  stays blue, the backlight stays on and the last frame stays on the panel:
  PSCI `SYSTEM_OFF` only parks the CPUs. A real "off" is part of this plan.

The goal is the stock behaviour: the power button on the case puts the
projector into standby and wakes it. On top of that, everything must also
work with nobody touching the device: from the CLI, over the network, on a
timer, and later from the HDMI source (CEC).

**Requirement (2026-10-07): the product must come back from standby with no
physical access.** The board is sealed inside the product, so the case button
is not reachable; a USB GPIO board on the USB port will drive standby and the
video player. Consequences:

- **Light standby (phase 2) is the product's standby.** The network and USB
  stay up, so a USB keypad, a GPIO-to-uinput bridge, ssh and timers can all
  wake it. `h713-keyd` takes `KEY_POWER` from any input device, including
  ones plugged in after it started (inotify on /dev/input), and
  `CONFIG_INPUT_UINPUT=m` (loaded at boot) lets a non-HID GPIO board inject
  keys. Verified with a hotplugged virtual USB keypad: press -> on,
  press -> off.
- **s2idle (phase 3) is not used by default.** It switches the hotspot off,
  so nothing on the network can wake it, and a USB device can only wake it
  through USB remote wakeup, which nothing here has been tested with. It
  becomes usable only once the actual USB GPIO board is shown to wake it.

## The three states

| state | how you enter | how it comes back |
| --- | --- | --- |
| **standby** (light; the product's) | power key, `h713-standby on` | key, network, timer, USB input |
| **suspend** (s2idle; opt-in) | `systemctl suspend` | case button, remote, RTC |
| **off** | `poweroff` / `shutdown -h` | power cycle only |

**Off (2026-10-07, verified):** PSCI `SYSTEM_OFF` on our BL31 only halts the
CPUs, leaving the lamp, fan and last frame up. A systemd-shutdown hook
(`/usr/lib/systemd/system-shutdown/h713-off`, rootfs) switches the lamp --
and so the fan -- off as the last step. Operator-observed: lamp off, nothing
came back; serial ends at `reboot: Power down` with no watchdog reset in
90 s. The power LED turned red, but it probably follows PB5 (the lamp/fan
enable) rather than the main rails, which stay up.

**What did not work:** dropping PL6, the core-rail enable stock names for
vdd-cpu/sys/pll/dram (kernel 0177, now out of series). The LED went red and
the rails dropped, but the SoC reset, PL6 returned to its default and the
board came straight back -- and that brownout restart then hung in U-Boot's
display bring-up (FIFO status 0x2, no logo, lamp on) until a power cycle.
Stock only holds PL6 low via ARISC firmware, which we do not load
([arisc-route-scope.md](arisc-route-scope.md)); a true rails-off "off" would
need that.

## Phase 0 — what is true today (measured on the bench board, 2026-10-07)

| fact | evidence |
| --- | --- |
| the kernel offers **s2idle only** | `/sys/power/state` = `freeze mem`, `/sys/power/mem_sleep` = `[s2idle]` |
| our BL31 has **no PSCI `SYSTEM_SUSPEND`** | `/sys/kernel/debug/psci` lists PSCIv1.1 with no SYSTEM_SUSPEND line |
| **no ARISC/SCP firmware is loaded** | [arisc-route-scope.md](arisc-route-scope.md) — so no DRAM self-refresh standby the way stock does it |
| the power button is **PL4**, a GPIO, `KEY_POWER` | stock DTB: `keyboard@2009800` `power-key = <0x74>`, `power-gpio = <&r_pio 0 4 0>`, `wakeup-source`; `standby_param` `power_key = "PL4"`, `key_debounce = 50` |
| our DT **leaves PL4 unclaimed** | `pinmux-pins`: `pin 356 (PL4): UNCLAIMED`; R_PIO CFG0 reads PL4 = `0xf` (I/O disabled), no pull |
| the IR receiver works, but **only raw** | `rc0` = `sunxi-ir` on PL9; `protocols` = `rc-5 nec rc-6 rc-5-sz [lirc]` — no decoder enabled, no keymap |
| stock's IR power codes | `cir_param`: 19 `(ir_addr_code, ir_power_key_code)` pairs, first is NEC addr `0xff00` key `0x14`; keymaps in `local/h713-lab/analysis/ir-keylayouts-stock/` |
| stock boots into standby on AC power | stock `env_a`: `BOOTMODE=standby`; also `CEC_ENABLE=1`, `CEC_WAKUP_ENABLE=1` |

## The tiers

Each tier works on its own and is a fallback for the one after it.

### Phase 1 — inputs

- `gpio-keys` node for PL4: `KEY_POWER`, `wakeup-source`, 50 ms debounce,
  polarity **measured, not copied** (stock's flag is 0 = active-high; read the
  pin idle and pressed before writing the node).
- IR: enable the NEC decoder and load a keymap built from the stock
  `.kl` files for the remote we actually have, with its power key mapped to
  `KEY_POWER`. Then both arrive as the same event.
- logind must not act on `KEY_POWER` by itself (`HandlePowerKey=ignore`);
  the standby daemon owns it.

### Phase 2 — software standby (`h713-standby`)

> **2026-10-07: DONE, verified on the bench board.** Kernel 0174 turns PB5
> from a gpio-hog into a gpio-backlight, `/sys/class/backlight/lamp`
> (`bl_power` 4 = lamp and fan off); no dark gap at boot (operator).
> `h713-standby on|off|toggle` stops the players, switches the lamp off and
> caps the CPU at 480 MHz; leaving turns the lamp (fan) on first, then
> lifts the cap. `h713-keyd` runs `toggle` on `KEY_POWER` from either
> source. Operator test with a video playing: case button -> on (mpv quit
> cleanly), remote -> off, remote -> on, case button -> off, each within
> ~1 s. With nobody touching it: `h713-standby on` over ssh went dark
> (operator saw it; PB5 read 1 -> 0 -> 1 across the cycle), and a
> `systemd-run` timer ran `off` per the journal -- that run was not
> watched (14 s for a 10 s timer: use `--timer-property=AccuracySec=1s`). Fan-off thermal: 15 min with PB5 low
> at 480 MHz, 54 C -> 59.1 C peak -> 57-58 C, against a 75 C passive trip,
> so no thermal guard is needed while idle and capped. Playback is stopped
> rather than paused: no player has a control channel.

The SoC stays up. Everything the user sees or hears turns off:
stop playback, mute (DAC volume 0 — **never** `Speaker Switch` 0, see
[audio.md](audio.md)), blank the plane/CRTC, backlight off, CPU to
the lowest OPP. Waking reverses it. WiFi stays up, so ssh and the network
keep working.

- One entry point: `h713-standby on|off|toggle|status`, driven by the power
  key, the IR power key, ssh, a network trigger, and timers.
- **PB5 is the backlight *and* fan enable.** Lamp off with the fan off is
  only acceptable if the SoC stays below its trips at idle. Measure the
  temperature over an hour of standby before shipping it that way.

### Phase 3 — s2idle (`systemctl suspend`)

> **2026-10-07: in progress.** `tools/standby/suspend-ladder.sh` runs
> `pm_test` stages (CONFIG_PM_DEBUG) then a real s2idle, with a health check
> after each (vblank, a VE decode, WiFi, new kernel errors). Results:
> `freezer` pass; `devices` pass -- every driver suspends and resumes, the
> display and the VE work after -- once the WiFi AP is restarted (cfg80211
> stops it on suspend; a systemd-sleep hook now restarts h713-hotspot and
> clients re-associate); a real `rtcwake -m freeze` suspended and was woken
> by the RTC (pm_wakeup_irq = the RTC's), all healthy after. 0175 keeps the
> IR receiver running as a wakeup source.
>
> **The RTC ran at 0.717x real time**, so every alarm was ~40% late (20 s
> woke after 28 s). No 32k crystal is fitted; it counted on the internal RC
> (+/-30%), and the H616 calibration register is not implemented on H713.
> Stock instead feeds the RTC from the 24 MHz crystal (/750, gate at
> LOSC_OUT_GATING bit 16, mux at LOSC_CTRL bit 1 -- selecting it with the
> gate closed STOPS the RTC). Measured live: 1.00008x. Kernel 0176.
>
> With 0176 from a cold boot: RTC 0.99998x, and a real 20 s rtcwake slept
> 20 s. Woken from real s2idle (`tools/standby/wake-sources.sh`, 60 s RTC
> safety net): the case button after 7.2 s (pm_wakeup_irq = Power, PL4) and
> the remote's POWER after 7.4 s (sunxi-ir). All three wake sources work.

CPUs idle in WFI, devices suspend, and any wake-capable interrupt resumes.
Wake sources: PL4, IR (`s_cir` is in the R domain), RTC alarm (`rtcwake`),
and WiFi if the aic8800 supports WoWLAN on this firmware.
The risk is every driver's suspend/resume path, which nothing has
exercised: afbd/KMS with the display MIPS running, cedrus, panfrost,
mmc + aic8800 (remember: unbind/reload oopses the mmc core), audio, IOMMU.
Gate: 100 suspend/resume cycles with playback working after each.

### Phase 4 — deep standby (deferred)

DRAM self-refresh with rails off, like stock: PSCI `SYSTEM_SUSPEND` in our
TF-A plus SCP/ARISC firmware to watch PL4/IR/CEC while the ARM cores are
off. This is the large reverse-engineering job in arisc-route-scope.md and
is only worth starting if Phases 2–3 do not save enough power.

## Measurements still needed

- standby power at each tier — needs a wall or USB power meter;
- SoC temperature in Phase 2 standby with PB5 low;
- PL4 polarity, idle and pressed (operator).
