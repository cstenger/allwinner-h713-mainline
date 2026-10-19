#!/usr/bin/env python3
"""Exercise the actual H713 PA helper C code with a deterministic work queue.

Usage: test-speaker-pa.py <patched-kernel>/sound/soc/sunxi/sun4i-codec.c
This checks state/ordering and stale callbacks, not hardware timing or sound.
"""
import pathlib
import subprocess
import sys
import tempfile

source = pathlib.Path(sys.argv[1]).read_text()
helpers = source[source.index('static void sun50i_h713_codec_pa_work('):
                 source.index('static void sun4i_codec_start_playback(')]
preamble = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <limits.h>
struct work_struct { int unused; };
struct delayed_work { struct work_struct work; bool pending; unsigned long due; };
struct sun4i_codec {
    int *gpio_pa;
    bool pa_on_playback, pa_speaker_on, pa_playback_on;
    unsigned long pa_ready_at;
    int pa_lock;
    struct delayed_work pa_work;
};
static unsigned long jiffies;
static void *system_wq;
#define container_of(p,t,m) ((t *)((char *)(p) - offsetof(t,m)))
#define to_delayed_work(p) container_of(p,struct delayed_work,work)
#define spin_lock_irqsave(lock,flags) do { (void)(lock); (flags)=0; } while (0)
#define spin_unlock_irqrestore(lock,flags) do { (void)(lock); (void)(flags); } while (0)
#define msecs_to_jiffies(ms) (ms)
#define time_before(a,b) ((long)((a)-(b)) < 0)
static void gpiod_set_value(int *gpio, int value) { *gpio=value; }
static bool cancel_delayed_work(struct delayed_work *w) {
    bool previous=w->pending; w->pending=false; return previous;
}
static bool mod_delayed_work(void *queue, struct delayed_work *w, unsigned long delay) {
    (void)queue; bool previous=w->pending; w->pending=true; w->due=jiffies+delay; return previous;
}
static void cancel_delayed_work_sync(struct delayed_work *w) { w->pending=false; }
'''
tests = r'''
int main(void) {
    int gpio=0;
    struct sun4i_codec c={.gpio_pa=&gpio, .pa_on_playback=true};
    /* Running PCM alone cannot power a disabled Speaker widget. */
    sun50i_h713_codec_pa_playback(&c,true);
    assert(!gpio && !c.pa_work.pending);
    c.pa_speaker_on=true;
    sun50i_h713_codec_pa_update_locked(&c);
    assert(!gpio && c.pa_work.due==200);
    jiffies=199;
    sun50i_h713_codec_pa_work(&c.pa_work.work);
    assert(!gpio && c.pa_work.due==200);
    jiffies=200;
    sun50i_h713_codec_pa_work(&c.pa_work.work);
    assert(gpio);
    /* Stop immediately mutes, even if a callback was already dispatched. */
    sun50i_h713_codec_pa_playback(&c,false);
    assert(!gpio && !c.pa_work.pending);
    sun50i_h713_codec_pa_work(&c.pa_work.work);
    assert(!gpio);
    /* An old callback must honor the latest START's full settling time. */
    jiffies=300;
    sun50i_h713_codec_pa_playback(&c,true);
    jiffies=499;
    sun50i_h713_codec_pa_playback(&c,false);
    sun50i_h713_codec_pa_playback(&c,true);
    jiffies=500;
    sun50i_h713_codec_pa_work(&c.pa_work.work);
    assert(!gpio && c.pa_work.due==699);
    jiffies=699;
    sun50i_h713_codec_pa_work(&c.pa_work.work);
    assert(gpio);
    /* Speaker power-down overrides a still-running PCM. */
    c.pa_speaker_on=false;
    sun50i_h713_codec_pa_update_locked(&c);
    sun50i_h713_codec_pa_work(&c.pa_work.work);
    assert(!gpio && !c.pa_work.pending);
    /* Deadline arithmetic remains valid across jiffies wraparound. */
    c.pa_speaker_on=true;
    jiffies=ULONG_MAX-100;
    sun50i_h713_codec_pa_playback(&c,true);
    jiffies=ULONG_MAX-50;
    sun50i_h713_codec_pa_work(&c.pa_work.work);
    assert(!gpio && c.pa_work.due==99);
    jiffies=99;
    sun50i_h713_codec_pa_work(&c.pa_work.work);
    assert(gpio);
    sun50i_h713_codec_pa_cleanup(&c);
    assert(!gpio && !c.pa_work.pending);
    /* Other variants retain their existing GPIO behavior. */
    c.pa_on_playback=false; gpio=1;
    sun50i_h713_codec_pa_playback(&c,false);
    assert(gpio);
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='h713-pa-test-') as directory:
    path = pathlib.Path(directory)
    (path/'test.c').write_text(preamble+helpers+tests)
    subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                    str(path/'test.c'), '-o', str(path/'test')], check=True)
    subprocess.run([str(path/'test')], check=True)
print('PASS: PA gating, STOP, stale callbacks, rapid restart, widget power-down, wraparound, cleanup, variant isolation')
