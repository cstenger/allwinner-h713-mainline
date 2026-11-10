# Approved checked poweroff before GP7 orderly trial, October 24

User explicitly authorized checked poweroff, then a disconnected cold cycle
and a later ready. Read-only precheck: current boot
4e82b014-0c3f-4645-be99-8ec69bed9ed4, uptime 772.90 s; fuser found no tty owner.
Sent exactly one systemctl poweroff --no-block using the detached serial
runner's poweroff action. UART recorded reboot: Power down at board uptime
782.729387 s; host receipt 2026-10-25 06:26:46.726 UTC (October 24 23:26:46 PDT).
Reader closed normally. See events.log and uart-poweroff.log.
No reboot, boot-stop request or GP7 trial was performed. Waiting for operator
to disconnect board power/serial/USB for at least one minute and say ready.
