#!/usr/bin/env python3
"""Re-advertise HDMI to a source that never started sending.

Some sources (an RTX 3090 on NVIDIA 615.78.08 after it boots) never read the EDID
on the first advert, while an HPD low pulse brings them up. With no TMDS at all
(signal "none") this asks the signal owner for one HPD cycle, on a growing
schedule, and starts the schedule again whenever a source goes away. Any other
signal state means a source is sending and is left alone.
"""
import sys
import time
from pathlib import Path

SIGNAL = Path('/sys/devices/platform/h713-hdmi-ring/signal')
PARAMS = Path('/sys/module/h713_hdmi_signal/parameters')
# Seconds without any source before each request, counted from the owner being
# ready, a source going away, or the previous request. ~5 min in all, enough to
# span a source PC's own reboot.
SCHEDULE = (10, 20, 40, 80, 160)
HOLD_MS = 2000


def read(path):
    try:
        return path.read_text().strip()
    except OSError:
        return ''


def owner_ready():
    return read(PARAMS / 'ready') == 'Y' and read(PARAMS / 'failed') == 'N'


def main(clock=time.monotonic, sleep=time.sleep, polls=None):
    if not (PARAMS / 'readvertise').exists():
        print('signal owner has no readvertise request; nothing to do', flush=True)
        return 0
    since, attempt, had_source = clock(), 0, False
    while polls is None or polls > 0:
        if polls is not None:
            polls -= 1
        state = read(SIGNAL).split(' ')[0]
        if state == '':
            pass  # unreadable: act on nothing
        elif state != 'none':
            attempt, had_source = 0, True
        else:
            if had_source:  # a source went away: a fresh schedule for its return
                since, had_source = clock(), False
            if attempt < len(SCHEDULE) and clock() - since >= SCHEDULE[attempt] and owner_ready():
                attempt += 1
                print(f'no source for {SCHEDULE[attempt - 1]} s: re-advertising ({attempt}/{len(SCHEDULE)})', flush=True)
                try:
                    (PARAMS / 'readvertise').write_text(f'{HOLD_MS}\n')
                except OSError as error:
                    print(f're-advertise refused ({error.strerror}); stopping', flush=True)
                    return 1
                since = clock()
        sleep(1)
    return 0


if __name__ == '__main__':
    sys.exit(main())
