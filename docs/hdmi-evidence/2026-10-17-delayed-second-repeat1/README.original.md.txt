# Independent delayed second-reboot repeat 1, 2026-10-17

Operator cold power-cycled board before capture started; logo/console visible. Initial SSH at uptime23.89s: boot7f07f5c3-129e-4014-b01b-7e21c94d0526, correct HDMI chosen handoff, GP6 48444d49, both capture/signal active. Cold serial startup was not captured, so verification relies on live Linux handoff/services.

Plan: first warm reboot, confirm black, second warm reboot at black-boot uptime238.07s without diagnostic TCON access or HDMI changes. Record actual first/cold session dwell and actual second reboot time. This is a fresh independent cold-trigger lineage; no intervening prompt second reboot in this arm. Keep HDMI attached at both ends throughout.

Capture raw UART and host timestamped data; target wall clock is wrong. No TCON reads/writes by diagnostics. Normal shutdown/boot display programming still occurs.

First reboot requested exactly at cold-boot uptime70.00s; serial confirms terminal MIPS park, ordered shutdown, restart, warm branch and logo commit, Linux serial login. Second-reboot timer pre-armed for uptime238.07s, gated on a boot-ID-specific operator black-confirmation file; no reboot if no confirmation by deadline or if window already missed. No diagnostic TCON access. Awaiting visual verdict and confirmation HDMI remains attached.

Operator confirmed black with HDMI still connected at both ends and authorized second warm reboot at238.07s. Boot-ID-gated confirmation sent at 2026-10-17T19:08:43.299392-07:00. No diagnostic TCON access or HDMI changes.

Second warm reboot requested at exactly uptime238.07s of confirmed black boot66ec1666-33d7-4cd7-8149-c1f9ab80792f. Operator confirmation flag sent at uptime66.56s, timer armed at26.05s. Serial confirms ordered panel shutdown, restart, warm branch, FIFO2 reset ->0, logo committed and Linux login. No diagnostic TCON access or HDMI disconnection. Awaiting operator visual result; serial capture remains active.

## Result: GOOD, independent delayed SECOND reboot at238.07s

Operator report received 2026-10-17T19:12:52.092721-07:00: logo and console returned; HDMI stayed connected at both ends.

This independently repeats recovery on the second warm reboot at black-boot uptime238.07s, without diagnostic TCON access or HDMI disconnection. First reboot requested at cold-boot uptime70.00s. Current observed independent delayed second-reboot controls at238.07s:2 good/2 trials. Prompt second reboot at54.58s:0 good/1 trial. Third-reboot recovery at695.23s is a different reset-count arm and must not be pooled as a second-reboot replicate. Small sample and potential hidden-state variation remain; no timing threshold or guaranteed workaround established. Next recommended trial: fresh cold lineage, first reboot at~70s with verified active services, then prompt second reboot near55s on operator-confirmed black. Pre-arm timing with confirmation gate where feasible and record actual age/missed windows. Serial recorder stopped after completed trial.
