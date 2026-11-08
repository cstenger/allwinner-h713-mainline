#!/usr/bin/env python3
"""Re-advertise HDMI to a source that never started sending.

Some sources (an RTX 3090 on NVIDIA 615.78.08 after it boots) never read the EDID
on the first advert, while an HPD low pulse brings them up. With no TMDS at all
(signal "none") this asks the signal owner for one HPD cycle, on a growing
schedule, and starts the schedule again whenever a source goes away. Any other
signal state means a source is sending and is left alone.
"""
import errno
import fcntl
import json
import os
import select
import struct
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
# Set only in the separately packaged diagnostic generation, never by the
# installed production policy. Normal fallback remains byte-for-byte in run().
DIAGNOSTIC_DDC_ONLY = False
DIAGNOSTIC_HPD_ONLY = False
# Owners with hpd_pulse (hpd-pulse-v1) re-advertise with an HDMI-spec HPD low
# pulse of PULSE_MS, DDC left enabled, instead of the 2 s HPD+DDC hold. A
# fresh source (board start, or source power returning) gets a first step of
# PULSE_FIRST s: on 9 boots whose first advertisement worked, video started
# 1.31-1.37 s after the owner was ready. A source that was streaming and went
# away keeps the original 10 s first step, so a long source modeset is not
# pulsed. Polled every PULSE_POLL s while pulsing is available.
PULSE_MS = 150
PULSE_FIRST = 2
PULSE_POLL = 0.25
# Diagnostic only: with the ddc-activity owner (SCP watching the MIPS wrapper's
# DDC line byte 0x06840096 from owner ready), log its report at start, when a
# source appears and around each pulse, and re-arm it at each pulse so its
# activity timestamp measures the source's response. Other owners: no effect.
ACTIVITY_VERSIONS = ('ddc-activity-hpd-pulse-v1', 'ddc-activity-hpd-pulse-v2', 'hpd-event-v1')
# Event-driven pulse (hpd-event-v1 owners): the SCP watches the DDC lines from
# owner ready. A failed EDID read is a short burst of retries the slave never
# acknowledges (2026-11-07: 46 toggling passes over 7.5 ms, against 1148 over
# 108 ms for a real read), followed by silence and no TMDS. On that signature
# pulse at once instead of waiting PULSE_FIRST. At most EVENT_MAX event pulses
# per fresh period, EVENT_GAP s apart; the timed schedule stays as backstop.
EVENT_VERSIONS = ('hpd-event-v1',)
EVENT_POLL = 0.1
FAILED_READ_BUSY = 120      # toggling SCP passes (~57 us each); a 128-byte read at 100 kHz is ~200
FAILED_READ_QUIET = 0.1     # s without new DDC activity before a burst counts as over
EVENT_MAX = 2
EVENT_GAP = 1.0
ACTIVITY_WINDOW = '0x06840094 4'

# Native 64-bit Linux V4L2 ABI (the RC is arm64). No streaming/set-control ioctl.
POWER_ID = 0x00A00964
QUERYCTRL = 0xC0445624
G_CTRL = 0xC008561B
SUBSCRIBE_EVENT = 0x4020565A
DQEVENT = 0x80885659


class PowerEvents:
    """Standard read-only power status and CTRL events on the capture node."""
    def __init__(self):
        self.fd = None

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def read(self):
        try:
            if self.fd is None:
                self.fd = os.open('/dev/h713-hdmi-in', os.O_RDONLY | os.O_NONBLOCK)
                fcntl.ioctl(self.fd, SUBSCRIBE_EVENT, struct.pack('=8I', 3, POWER_ID, 0, 0, 0, 0, 0, 0))
                fcntl.ioctl(self.fd, SUBSCRIBE_EVENT, struct.pack('=8I', 5, 0, 0, 0, 0, 0, 0, 0))
            # Drain notifications, then query current state; merged/lost events
            # must never leave a stale "absent" suppressing recovery forever.
            for _ in range(32):
                try:
                    fcntl.ioctl(self.fd, DQEVENT, bytearray(136), True)
                except OSError as error:
                    if error.errno in (errno.EAGAIN, errno.ENOENT):
                        break
                    raise
            query = bytearray(struct.pack('=II32siiiiIII', POWER_ID, 0, b'', 0, 0, 0, 0, 0, 0, 0))
            fcntl.ioctl(self.fd, QUERYCTRL, query, True)
            fields = struct.unpack('=II32siiiiIII', query)
            if fields[1] != 8 or fields[3:5] != (0, 1) or not fields[7] & 4:
                raise OSError('unexpected power control contract')
            if fields[7] & (1 | 16):  # DISABLED / INACTIVE: unknown, not absent
                return None
            value = bytearray(struct.pack('=Ii', POWER_ID, 0))
            fcntl.ioctl(self.fd, G_CTRL, value, True)
            present = struct.unpack('=Ii', value)[1]
            fcntl.ioctl(self.fd, QUERYCTRL, query, True)
            if struct.unpack('=II32siiiiIII', query)[7] & (1 | 16):
                return None
            return bool(present) if present in (0, 1) else None
        except OSError:
            self.close()
            return None

    def wait(self, seconds, sleep):
        if self.fd is None:
            sleep(seconds)
        else:
            try:
                select.select([], [], [self.fd], seconds)
            except OSError:
                self.close()


def read(path):
    try:
        return path.read_text().strip()
    except OSError:
        return ''


def owner_ready():
    return read(PARAMS / 'ready') == 'Y' and read(PARAMS / 'failed') == 'N'


def ddc_counters():
    """act/last/busy/seq from the owner's DDC watch header, or None."""
    try:
        head = (PARAMS / 'ddc_scan').read_text().split('\n', 1)[0].split()
        fields = dict(zip(head[::2], head[1::2]))
        return {k: int(fields[k]) for k in ('seq', 'act', 'last', 'busy')}
    except (OSError, KeyError, ValueError):
        return None


def ddc_activity(phase, clock, rearm=False):
    if read(PARAMS.parent / 'version') not in ACTIVITY_VERSIONS:
        return
    record = dict(kind='ddc_activity', phase=phase, monotonic=clock(),
                  signal=read(SIGNAL), scan=read(PARAMS / 'ddc_scan').splitlines())
    if rearm:
        try:
            (PARAMS / 'ddc_scan').write_text(ACTIVITY_WINDOW + '\n')
            record['rearmed'] = clock()
        except OSError as error:
            record['rearm_error'] = error.strerror
    print(json.dumps(record), flush=True)


def isolate_initial_ddc(power, clock, sleep):
    """Bench only: one DDC-only cycle if initial source state stays none.

    There is no HPD request here. If the stream starts during the grace
    interval, or power is known absent, leave it alone and use normal policy.
    The kernel checks SCP-copied HPD/DDC readbacks and keeps separate counts.
    """
    def emit(phase, **data):
        print(json.dumps(dict(kind='ddc_isolation', phase=phase,
                              monotonic=clock(), **data)), flush=True)

    if read(PARAMS.parent / 'version') != 'ddc-hpd-isolation-v1' or not (PARAMS / 'ddc_cycle').exists():
        raise RuntimeError('DDC diagnostic module/version missing')

    def quiet():
        return read(SIGNAL).split(' ')[0] == 'none' and power.read() is not False and owner_ready()

    deadline = clock() + 5
    while not read(SIGNAL) and clock() < deadline:
        sleep(.1)
    emit('initial', signal=read(SIGNAL), source_power=power.read())
    if not quiet():
        emit('skipped', reason='source active/acquiring, known absent, or owner unavailable')
        return
    deadline = clock() + 3
    while clock() < deadline:
        if not quiet():
            emit('skipped', reason='source or owner changed during grace')
            return
        sleep(.1)
    if not quiet() or read(PARAMS / 'readvertised') != '0' or read(PARAMS / 'ddc_cycles') != '0':
        emit('skipped', reason='initial state/count gate changed')
        return
    emit('request', hold_ms=2000, hpd_requests=0)
    (PARAMS / 'ddc_cycle').write_text('2000\n')
    if not owner_ready() or read(PARAMS / 'ddc_cycles') != '1' or read(PARAMS / 'readvertised') != '0':
        raise RuntimeError('DDC-only cycle failed state/count checks')
    emit('completed', ddc_cycles=1, hpd_retries=0)
    deadline = clock() + 5
    while clock() < deadline:
        state = read(SIGNAL).split(' ')[0]
        if state == 'locked':
            emit('locked_without_hpd_retry', signal=read(SIGNAL))
            return
        sleep(.1)
    emit('no_lock', signal=read(SIGNAL), next='original bounded HPD fallback')


def isolate_initial_hpd(power, clock, sleep):
    """Bench only: one HPD-only pulse (DDC left enabled) if initial state stays none.

    Mirror of isolate_initial_ddc: same grace, gates and 5 s lock window. The
    kernel forces HPD low 2000 ms and releases it without writing DDC, and
    checks SCP-copied HPD/DDC readbacks; it counts hpd_cycles, not readvertised.
    """
    def emit(phase, **data):
        # A sampler-equipped owner reports its read-only DDC/HPD register view
        # with every phase; without it the record is unchanged.
        if (PARAMS / 'ddc_sample').exists():
            data['ddc_sample'] = read(PARAMS / 'ddc_sample').splitlines()
        print(json.dumps(dict(kind='hpd_isolation', phase=phase,
                              monotonic=clock(), **data)), flush=True)

    if read(PARAMS.parent / 'version') not in ('hpd-only-isolation-v1', 'ddc-sampler-hpd-only-v1') \
            or not (PARAMS / 'hpd_cycle').exists():
        raise RuntimeError('HPD diagnostic module/version missing')

    def quiet():
        return read(SIGNAL).split(' ')[0] == 'none' and power.read() is not False and owner_ready()

    deadline = clock() + 5
    while not read(SIGNAL) and clock() < deadline:
        sleep(.1)
    emit('initial', signal=read(SIGNAL), source_power=power.read())
    if not quiet():
        emit('skipped', reason='source active/acquiring, known absent, or owner unavailable')
        return
    deadline = clock() + 3
    while clock() < deadline:
        if not quiet():
            emit('skipped', reason='source or owner changed during grace')
            return
        sleep(.1)
    if not quiet() or read(PARAMS / 'readvertised') != '0' or read(PARAMS / 'hpd_cycles') != '0':
        emit('skipped', reason='initial state/count gate changed')
        return
    emit('request', hold_ms=2000, ddc_requests=0)
    if (PARAMS / 'ddc_sample').exists():
        # Restart the toggle masks so the pulse's effects are attributable.
        (PARAMS / 'ddc_sample').write_text('1\n')
    (PARAMS / 'hpd_cycle').write_text('2000\n')
    if not owner_ready() or read(PARAMS / 'hpd_cycles') != '1' or read(PARAMS / 'readvertised') != '0':
        raise RuntimeError('HPD-only pulse failed state/count checks')
    emit('completed', hpd_cycles=1, readvertised=0)
    deadline = clock() + 5
    while clock() < deadline:
        state = read(SIGNAL).split(' ')[0]
        if state == 'locked':
            emit('locked_without_ddc_reset', signal=read(SIGNAL))
            return
        sleep(.1)
    emit('no_lock', signal=read(SIGNAL), next='original bounded HPD fallback')

def main(clock=time.monotonic, sleep=time.sleep, polls=None, power=None):
    if not (PARAMS / 'readvertise').exists():
        print('signal owner has no readvertise request; nothing to do', flush=True)
        return 0
    power = power if power is not None else PowerEvents()
    try:
        if DIAGNOSTIC_DDC_ONLY and DIAGNOSTIC_HPD_ONLY:
            raise RuntimeError('only one isolation diagnostic per generation')
        if DIAGNOSTIC_DDC_ONLY:
            isolate_initial_ddc(power, clock, sleep)
        if DIAGNOSTIC_HPD_ONLY:
            isolate_initial_hpd(power, clock, sleep)
        return run(power, clock, sleep, polls)
    finally:
        power.close()


def run(power, clock, sleep, polls):
    pulse = (PARAMS / 'hpd_pulse').exists()
    fresh = ((PULSE_FIRST,) + SCHEDULE) if pulse else SCHEDULE
    step = PULSE_POLL if pulse else 1
    schedule = fresh
    event = pulse and read(PARAMS.parent / 'version') in EVENT_VERSIONS and (PARAMS / 'ddc_scan').exists()
    step = EVENT_POLL if event else step
    events, watch = 0, None
    since, attempt, had_source = clock(), 0, False
    previous_power = object()
    ddc_activity('start', clock)
    seen = False
    while polls is None or polls > 0:
        if polls is not None:
            polls -= 1
        state = read(SIGNAL).split(' ')[0]
        present = power.read()
        if present != previous_power:
            print('source power: ' + {None: 'unknown; timeout fallback', False: 'absent', True: 'present'}[present], flush=True)
            if present is True and previous_power is False:
                since, attempt, schedule = clock(), 0, fresh
                events, watch = 0, None
                if event:  # the returning source's first read must be judged on its own
                    ddc_activity('source_power_returned', clock, rearm=True)
            previous_power = present
        if present is False:
            # Never request HPD for a known disconnected/unpowered source.
            since, attempt = clock(), 0
        if state == '':
            pass  # unreadable: act on nothing
        elif state != 'none':
            attempt, had_source, watch = 0, True, None
            if not seen:
                seen = True
                ddc_activity('source_seen', clock)
        else:
            seen = False
            if had_source:  # a source went away: a fresh schedule for its return
                since, had_source, schedule = clock(), False, SCHEDULE
                events, watch = 0, None
                if event:  # forget the old good read so a failed return read is seen
                    ddc_activity('source_lost', clock, rearm=True)
            if event and present is not False and events < EVENT_MAX and owner_ready() and \
                    (clock() - since >= EVENT_GAP or (attempt == 0 and events == 0)):
                c = ddc_counters()
                if c and c['act'] and c['busy'] < FAILED_READ_BUSY:
                    if watch is None or watch[0] != c['last']:
                        watch = (c['last'], clock())
                    elif clock() - watch[1] >= FAILED_READ_QUIET:
                        if read(SIGNAL).split(' ')[0] != 'none' or power.read() is False or not owner_ready():
                            power.wait(EVENT_POLL, sleep)
                            continue
                        events, attempt, watch = events + 1, max(attempt, 1), None
                        print(f'failed EDID read (busy {c["busy"]} passes): HPD pulse {PULSE_MS} ms '
                              f'(event {events}/{EVENT_MAX})', flush=True)
                        ddc_activity('failed_read', clock, rearm=True)
                        try:
                            (PARAMS / 'hpd_pulse').write_text(f'{PULSE_MS}\n')
                        except OSError as error:
                            print(f're-advertise refused ({error.strerror}); stopping', flush=True)
                            return 1
                        since = clock()
                        power.wait(EVENT_POLL, sleep)
                        continue
                else:
                    watch = None
            if present is not False and attempt < len(schedule) and clock() - since >= schedule[attempt] and owner_ready():
                # Close the sample-to-request window as far as possible;
                # preserve the owner gate and refuse to pulse any active state.
                if read(SIGNAL).split(' ')[0] != 'none' or power.read() is False or not owner_ready():
                    power.wait(step, sleep)
                    continue
                attempt += 1
                if pulse:
                    print(f'no source for {schedule[attempt - 1]} s: HPD pulse {PULSE_MS} ms ({attempt}/{len(schedule)})', flush=True)
                    request, value = 'hpd_pulse', PULSE_MS
                    ddc_activity('before_pulse', clock, rearm=True)
                else:
                    print(f'no source for {schedule[attempt - 1]} s: re-advertising ({attempt}/{len(schedule)})', flush=True)
                    request, value = 'readvertise', HOLD_MS
                try:
                    (PARAMS / request).write_text(f'{value}\n')
                except OSError as error:
                    print(f're-advertise refused ({error.strerror}); stopping', flush=True)
                    return 1
                since = clock()
        power.wait(step, sleep)
    return 0


if __name__ == '__main__':
    sys.exit(main())
