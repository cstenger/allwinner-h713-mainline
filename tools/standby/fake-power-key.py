#!/usr/bin/env python3
"""Plug in a virtual keypad (uinput) and press its KEY_POWER, as a USB HID
keypad or a GPIO-to-uinput bridge would. RUNS ON THE TARGET, as root.

  fake-power-key.py [PRESSES] [GAP_S]     (default 2 presses, 3 s apart)

Checks that h713-keyd picks up a device that appears after it started
(inotify on /dev/input) and that its key toggles h713-standby. Prints the
standby state after each press. Needs CONFIG_INPUT_UINPUT (modprobe uinput).
"""
import fcntl, os, struct, subprocess, sys, time

PRESSES = int(sys.argv[1]) if len(sys.argv) > 1 else 2
GAP = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
EV_SYN, EV_KEY, KEY_POWER = 0, 1, 116
UI_SET_EVBIT, UI_SET_KEYBIT = 0x40045564, 0x40045565
UI_DEV_SETUP, UI_DEV_CREATE, UI_DEV_DESTROY = 0x405c5503, 0x5501, 0x5502

def emit(fd, typ, code, val):
    os.write(fd, struct.pack("llHHi", 0, 0, typ, code, val))

def state():
    return subprocess.run(["/usr/local/bin/h713-standby"], capture_output=True,
                          text=True).stdout.strip()

fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
fcntl.ioctl(fd, UI_SET_KEYBIT, KEY_POWER)
# struct uinput_setup: input_id (bustype=USB, vendor, product, version), name[80], ff_effects_max
fcntl.ioctl(fd, UI_DEV_SETUP, struct.pack("HHHH80sI", 0x03, 0x1209, 0x0001, 1,
                                          b"virtual-usb-keypad", 0))
fcntl.ioctl(fd, UI_DEV_CREATE)
print("plugged in virtual-usb-keypad; standby:", state(), flush=True)
time.sleep(1.5)                       # h713-keyd reopens on the inotify event
try:
    for i in range(PRESSES):
        emit(fd, EV_KEY, KEY_POWER, 1); emit(fd, EV_SYN, 0, 0)
        time.sleep(0.1)
        emit(fd, EV_KEY, KEY_POWER, 0); emit(fd, EV_SYN, 0, 0)
        time.sleep(GAP)
        print("press %d -> standby: %s" % (i + 1, state()), flush=True)
finally:
    fcntl.ioctl(fd, UI_DEV_DESTROY)
    os.close(fd)
