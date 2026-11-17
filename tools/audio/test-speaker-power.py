#!/usr/bin/env python3
"""Run the real H713 speaker power helpers (kernel 0212) against stubs.

Usage: test-speaker-power.py <kernel-tree>/sound/soc/sunxi/sun4i-codec.c [--mutations]

The block between the "H713 speaker power: begin/end" markers is compiled on
the host with a virtual millisecond clock under ASan/UBSan. Every PA rise must
find the clock on, the whole path forced and >= 700 ms of settling; every clock
stop or rate change must find PA low for >= 100 ms (the measured silent
minimum; the driver holds 300). --mutations also builds broken variants and
requires each to fail. Ordering and state only: not hardware timing or sound.
"""
import pathlib
import subprocess
import sys
import tempfile

PREAMBLE = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define container_of(p, t, m) ((t *)((char *)(p) - offsetof(t, m)))
#define dev_err(d, ...) ((void)(d))
struct work_struct { int pending; };
struct mutex { int held; };
struct clk { unsigned long rate; int enable; int fail_enable, fail_rate; };
struct gpio_desc { int value; };
struct snd_soc_dapm_context { int locked; };
struct snd_soc_card { struct snd_soc_dapm_context dapm; void *drvdata; };
struct snd_kcontrol { struct snd_soc_card *card; };
struct snd_ctl_elem_value { union { struct { long value[2]; } integer; } value; };
struct device { int unused; };
struct sun4i_codec {
    struct device *dev;
    struct clk *clk_module;
    struct gpio_desc *gpio_pa;
    unsigned int mod_freq_mult;
    bool spk_power, spk_want, spk_blocked, spk_on;
    struct mutex spk_lock;
    struct work_struct spk_work;
    struct snd_soc_card *card;
};

static long now;                    /* virtual ms */
static long pa_low_since = -100000; /* PA low since boot */
static long forced_since = -1;
static int forced[6];
static int syncs;
static const char *names[6] = { "DAC Enable", "Left DAC", "Right DAC",
    "Line Out Source Playback Route", "HP Amp", "LINEOUT" };
static struct clk the_clk;
static struct gpio_desc the_pa;

static int idx(const char *w) {
    for (int i = 0; i < 6; i++) if (!strcmp(w, names[i])) return i;
    assert(!"unknown widget"); return -1;
}
static int all_forced(void) { for (int i = 0; i < 6; i++) if (!forced[i]) return 0; return 1; }
static int none_forced(void) { for (int i = 0; i < 6; i++) if (forced[i]) return 0; return 1; }

static void msleep(unsigned int ms) { now += ms; }
static void mutex_lock(struct mutex *m) { assert(!m->held); m->held = 1; }
static void mutex_unlock(struct mutex *m) { assert(m->held); m->held = 0; }
static void snd_soc_dapm_mutex_lock(struct snd_soc_dapm_context *d) { assert(!d->locked); d->locked = 1; }
static void snd_soc_dapm_mutex_unlock(struct snd_soc_dapm_context *d) { assert(d->locked); d->locked = 0; }
static int snd_soc_dapm_force_enable_pin_unlocked(struct snd_soc_dapm_context *d, const char *w) {
    assert(d->locked); forced[idx(w)] = 1; return 0; }
/* Real DAPM: disable clears force (and connected), enable restores connected only. */
static int snd_soc_dapm_disable_pin_unlocked(struct snd_soc_dapm_context *d, const char *w) {
    assert(d->locked); forced[idx(w)] = 0; return 0; }
static int snd_soc_dapm_enable_pin_unlocked(struct snd_soc_dapm_context *d, const char *w) {
    assert(d->locked); (void)w; return 0; }
static int snd_soc_dapm_sync_unlocked(struct snd_soc_dapm_context *d) {
    assert(d->locked); syncs++;
    if (all_forced() && forced_since < 0) forced_since = now;
    if (none_forced()) forced_since = -1;
    return 0; }
static bool __clk_is_enabled(struct clk *c) { return c->enable > 0; }
static int clk_set_rate(struct clk *c, unsigned long r) {
    if (c->fail_rate) return -22;
    /* A running clock may only change under a PA that has been low 100 ms. */
    if (c->enable) assert(!the_pa.value && now - pa_low_since >= 100);
    c->rate = r; return 0; }
static unsigned long clk_get_rate(struct clk *c) { return c->rate; }
static long clk_round_rate(struct clk *c, unsigned long r) { (void)c; return r; }
static int clk_prepare_enable(struct clk *c) { if (c->fail_enable) return -5; c->enable++; return 0; }
static void clk_disable_unprepare(struct clk *c) {
    assert(c->enable > 0);
    if (c->enable == 1) assert(!the_pa.value && now - pa_low_since >= 100);
    c->enable--; }
static void gpiod_set_value_cansleep(struct gpio_desc *g, int v) {
    if (v && !g->value) {
        assert(the_clk.enable > 0);
        assert(all_forced() && forced_since >= 0 && now - forced_since >= 700);
    }
    if (!v && g->value) pa_low_since = now;
    g->value = v; }
static bool cancel_work_sync(struct work_struct *w) { int p = w->pending; w->pending = 0; return p; }
static bool schedule_work(struct work_struct *w) { int p = w->pending; w->pending = 1; return !p; }
static void *snd_kcontrol_chip(struct snd_kcontrol *k) { return k->card; }
static void *snd_soc_card_get_drvdata(struct snd_soc_card *c) { return c->drvdata; }
#define SND_SOC_DAPM_PLACEHOLDER
'''

TESTS = r'''
static struct snd_soc_card card;
static struct device dev;
static struct sun4i_codec c;
static struct snd_kcontrol kc = { &card };

static void reset(void) {
    memset(&c, 0, sizeof c); memset(&the_clk, 0, sizeof the_clk); memset(&the_pa, 0, sizeof the_pa);
    memset(forced, 0, sizeof forced); now = 1000; pa_low_since = -100000; forced_since = -1;
    card.drvdata = &c; c.card = &card; c.dev = &dev; c.clk_module = &the_clk; c.gpio_pa = &the_pa;
    c.mod_freq_mult = 2; c.spk_power = true; c.spk_want = true; the_clk.rate = 43000000;
}
static void run_work(void) {
    if (c.spk_work.pending) { c.spk_work.pending = 0; sun50i_h713_spk_work(&c.spk_work); }
}
static int put(int v) {
    struct snd_ctl_elem_value u = {0}; u.value.integer.value[0] = v;
    return sun50i_h713_spk_power_put(&kc, &u);
}
static long get(void) {
    struct snd_ctl_elem_value u = {0}; sun50i_h713_spk_power_get(&kc, &u); return u.value.integer.value[0];
}
static void assert_up(void) {
    assert(c.spk_on && the_pa.value && the_clk.enable == 1 && all_forced());
}
static void assert_down(void) {
    assert(!c.spk_on && !the_pa.value && the_clk.enable == 0 && none_forced());
}

int main(void) {
    /* Probe: the work brings it up at the 48 kHz family rate. */
    reset(); schedule_work(&c.spk_work); run_work();
    assert_up(); assert(the_clk.rate == 24576000UL * 2);
    assert(!c.spk_lock.held && !card.dapm.locked);

    /* Control: off, idempotent, on. */
    long t = now; assert(put(0) == 1); assert_down(); assert(now - t >= 300); assert(get() == 0);
    assert(put(0) == 0); assert_down();
    assert(put(1) == 1); assert_up(); assert(get() == 1);
    assert(put(1) == 0); assert_up();

    /* Same rate: nothing moves. */
    long pa_edges_before = pa_low_since; t = now;
    assert(sun50i_h713_spk_set_rate(&c, 24576000UL * 2) == 0);
    assert(now == t && pa_low_since == pa_edges_before); assert_up();

    /* Other rate family while up: PA down around the change, then up again. */
    assert(sun50i_h713_spk_set_rate(&c, 22579200UL * 2) == 0);
    assert_up(); assert(the_clk.rate == 22579200UL * 2);

    /* Rate change while down: no PA activity. */
    put(0); t = now;
    assert(sun50i_h713_spk_set_rate(&c, 24576000UL * 2) == 0);
    assert(now == t && !the_pa.value);

    /* A stream holding the clock: power-up keeps its rate. */
    reset(); the_clk.enable = 1; the_clk.rate = 22579200UL * 2;
    schedule_work(&c.spk_work); run_work();
    assert(c.spk_on && the_pa.value && the_clk.enable == 2 && the_clk.rate == 22579200UL * 2);
    /* Down releases only the state's reference; the stream keeps its own. */
    put(0); assert(!the_pa.value && the_clk.enable == 1 && none_forced());

    /* Suspend/shutdown: down and stays down; the control is remembered. */
    reset(); schedule_work(&c.spk_work); run_work(); assert_up();
    sun50i_h713_spk_block(&c); assert_down(); assert(c.spk_blocked);
    schedule_work(&c.spk_work); run_work(); assert_down();
    assert(put(1) == 0); assert_down();
    sun50i_h713_spk_unblock(&c); assert(c.spk_work.pending); run_work(); assert_up();
    /* Blocking with work pending cancels it. */
    put(0); sun50i_h713_spk_unblock(&c); c.spk_want = true;
    sun50i_h713_spk_block(&c); assert(!c.spk_work.pending); assert_down();

    /* The guard inside up_locked itself: never up against the control or a block. */
    reset(); c.spk_want = false; assert(sun50i_h713_spk_up_locked(&c) == 0); assert_down();
    reset(); c.spk_blocked = true; assert(sun50i_h713_spk_up_locked(&c) == 0); assert_down();

    /* Failures leave everything down. */
    reset(); the_clk.fail_enable = 1; schedule_work(&c.spk_work); run_work();
    assert(!c.spk_on && !the_pa.value && none_forced() && the_clk.enable == 0);
    reset(); the_clk.fail_rate = 1; assert(put(0) == 1); assert(put(1) < 0);
    assert(!c.spk_on && !the_pa.value && none_forced() && the_clk.enable == 0);

    assert(!c.spk_lock.held && !card.dapm.locked && syncs > 0);
    puts("speaker power: all checks passed");
    return 0;
}
'''

MUTATIONS = {
    'hold below the measured minimum':
        ('SUN50I_H713_SPK_PA_OFF_HOLD_MS\t300', 'SUN50I_H713_SPK_PA_OFF_HOLD_MS\t30'),
    'no settle before PA':
        ('SUN50I_H713_SPK_SETTLE_MS\t700', 'SUN50I_H713_SPK_SETTLE_MS\t200'),
    'PA before the path is forced':
        ('''	sun50i_h713_spk_force_path(scodec, true);
	msleep(SUN50I_H713_SPK_SETTLE_MS);
	gpiod_set_value_cansleep(scodec->gpio_pa, 1);''',
         '''	gpiod_set_value_cansleep(scodec->gpio_pa, 1);
	sun50i_h713_spk_force_path(scodec, true);
	msleep(SUN50I_H713_SPK_SETTLE_MS);'''),
    'clock off with PA still high':
        ('''	gpiod_set_value_cansleep(scodec->gpio_pa, 0);
	msleep(SUN50I_H713_SPK_PA_OFF_HOLD_MS);
	sun50i_h713_spk_force_path(scodec, false);
	clk_disable_unprepare(scodec->clk_module);''',
         '''	clk_disable_unprepare(scodec->clk_module);
	gpiod_set_value_cansleep(scodec->gpio_pa, 0);
	msleep(SUN50I_H713_SPK_PA_OFF_HOLD_MS);
	sun50i_h713_spk_force_path(scodec, false);'''),
    'unforce with enable_pin only':
        ('			snd_soc_dapm_disable_pin_unlocked(dapm, w);\n', ''),
    'rate change under a live PA':
        ('''	was_on = scodec->spk_on;''', '''	was_on = false;'''),
    'block does not block':
        ('''	scodec->spk_blocked = true;''', '''	scodec->spk_blocked = false;'''),
    'rate reset under a running stream':
        ('''	if (!__clk_is_enabled(scodec->clk_module)) {''', '''	if (1) {'''),
    'power-up ignores the control':
        ('''	if (scodec->spk_on || !scodec->spk_want || scodec->spk_blocked)''',
         '''	if (scodec->spk_on || scodec->spk_blocked)'''),
}


def extract(source):
    a = source.index('/* ── H713 speaker power: begin')
    b = source.index('/* ── H713 speaker power: end ── */')
    return source[a:b]


def build_and_run(block, workdir, name):
    src = pathlib.Path(workdir)/(name + '.c')
    exe = pathlib.Path(workdir)/name
    src.write_text(PREAMBLE + block + TESTS)
    cc = subprocess.run(['clang', '-std=gnu11', '-g', '-O1', '-Wall', '-Werror',
                         '-Wno-unused-function', '-fsanitize=address,undefined',
                         '-fno-sanitize-recover=all', '-o', str(exe), str(src)],
                        capture_output=True, text=True)
    if cc.returncode:
        return 'compile', cc.stderr
    run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
    return run.returncode, run.stdout + run.stderr


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    block = extract(pathlib.Path(sys.argv[1]).read_text())
    failed = False
    with tempfile.TemporaryDirectory(prefix='spk-power-') as d:
        rc, out = build_and_run(block, d, 'real')
        print('real helpers:', 'PASS' if rc == 0 else 'FAIL', out.strip()[-400:])
        failed |= rc != 0
        if '--mutations' in sys.argv:
            for i, (name, (old, new)) in enumerate(MUTATIONS.items()):
                if block.count(old) != 1:
                    print('mutation %-34s cannot apply (pattern drifted)' % name)
                    failed = True
                    continue
                rc, out = build_and_run(block.replace(old, new), d, 'm%d' % i)
                caught = rc not in (0, 'compile')
                print('mutation %-34s %s' % (name, 'caught' if caught else
                                             'NOT CAUGHT' if rc == 0 else 'did not compile'))
                failed |= not caught
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
