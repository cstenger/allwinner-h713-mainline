# Power-on before runner arm: preflight only, October 27

Operator said ready and reported already powering the board. The reviewed
trial requires the sole UART reader OPEN before power-on; it was not started.
No GP7 trial live-output directory was created, no GP7 arm/reset/launch sent.

Host Wi-Fi was disconnected and 192.168.4.1 incorrectly routed via Ethernet.
Two initial read-only SSH checks timed out. Restored the existing saved spirits
Wi-Fi profile on wlan0 (Ethernet retained). A passive eight-second serial
read (O_RDONLY, no terminal configuration or bytes sent) recorded zero bytes;
boot markers were already missed. No serial command was sent.

After Wi-Fi restore, read-only SSH found boot
be9e6729-f523-491d-b5d4-d19a643d451f, uptime 158.49 s, handoff present,
capture/signal/speaker/ring active and video inactive. This is only a state
snapshot, not verified cold-start evidence or a passing health result.
Board left powered/running. Need approval for checked poweroff, then a fully
disconnected cold cycle and OPEN before power-on. No boot-stop or SysRq test
has been attempted; no files staged or services changed on the board.
