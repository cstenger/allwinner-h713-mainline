#!/usr/bin/env python3
"""Separate a PCM's STOP from its close, to time speaker pops against each.

RUNS ON THE BOARD (python3 + libasound via ctypes, no other packages).

    pcm-drop-close.py [DEVICE] [PLAY_S] [GAP_S] [RATE]

Opens DEVICE (default hw:Codec,0), plays PLAY_S seconds of digital silence,
calls snd_pcm_drop() (trigger STOP: the H713 driver drops the external amp,
but the codec module clock keeps running), waits GAP_S seconds, then
snd_pcm_close() (DAI shutdown: the module clock stops). Each phase is printed
with CLOCK_MONOTONIC so a microphone recording can be aligned to it. The
device must be free: stop whatever owns it (PipeWire's sink is released once
its last stream ends). RATE (default 48000) picks the hardware rate family:
44100 makes the H713 driver change its module clock (0212 takes PA down around it).
"""
import ctypes
import sys
import time

dev = (sys.argv[1] if len(sys.argv) > 1 else 'hw:Codec,0').encode()
play_s = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
gap_s = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0
RATE = int(sys.argv[4]) if len(sys.argv) > 4 else 48000

lib = ctypes.CDLL('libasound.so.2')
lib.snd_strerror.restype = ctypes.c_char_p
SND_PCM_STREAM_PLAYBACK = 0
SND_PCM_FORMAT_S32_LE = 10
SND_PCM_ACCESS_RW_INTERLEAVED = 3
CH = 2


def mark(what):
    print('mark %.6f %s' % (time.monotonic(), what), flush=True)


def check(rc, what):
    if rc < 0:
        raise SystemExit('%s: %s' % (what, lib.snd_strerror(rc).decode()))
    return rc


pcm = ctypes.c_void_p()
check(lib.snd_pcm_open(ctypes.byref(pcm), dev, SND_PCM_STREAM_PLAYBACK, 0), 'open')
mark('open')
# 100 ms latency, resampling off: the hardware runs at 48 kHz S32 like PipeWire.
check(lib.snd_pcm_set_params(pcm, SND_PCM_FORMAT_S32_LE,
                             SND_PCM_ACCESS_RW_INTERLEAVED, CH, RATE, 0,
                             100000), 'set_params')
chunk = RATE // 50
buf = ctypes.create_string_buffer(chunk * CH * 4)        # zeros
frames = 0
mark('play')
while frames < play_s * RATE:
    n = lib.snd_pcm_writei(pcm, buf, chunk)
    if n < 0:
        n = check(lib.snd_pcm_recover(pcm, n, 1), 'recover')
        continue
    frames += n
mark('drop')
check(lib.snd_pcm_drop(pcm), 'drop')
time.sleep(gap_s)
mark('close')
check(lib.snd_pcm_close(pcm), 'close')
mark('closed')
