// SPDX-License-Identifier: GPL-2.0
/*
 * Host self-test of modules/hdmi-v4l2/h713-signal.h -- the exact header the
 * kernel bridge compiles (HDMI panel-source design 10.26).
 *
 *   test-signal-state             run the built-in scenarios; exit 0 if all pass
 *   test-signal-state --trace     read "dt_ms valid port_state w h moving" lines
 *                                 from stdin, print one line per transition
 *                                 ("t_ms state WxH events") for test-signal-traces.py
 *
 * Each scenario is a list of segments (how long, what the sampler sees, the
 * sample period). The checks name the transitions and when they may happen,
 * so a wrong threshold, a missing event or an extra event fails a named line.
 */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef uint16_t u16;
typedef uint32_t u32;
#include "../../modules/hdmi-v4l2/h713-signal.h"

struct seg {
	unsigned int ms;	/* segment length */
	struct h713_sig_sample s;
	unsigned int period;	/* sample period; 0 = 20 ms */
	unsigned int jitter;	/* add 0..jitter ms pseudo-randomly */
};

struct transition {
	unsigned int t;
	enum h713_sig_state state;
	u16 w, h;
	unsigned int ev;
};

#define MAXT 64
static struct transition tr[MAXT];
static unsigned int ntr;
static int fails;

#define LIVE720 { true, 5, 1280, 720, true }
#define LIVE480 { true, 5, 640, 480, true }
#define LIVE1080 { true, 5, 1920, 1080, true }
#define DEAD { true, 3, 0, 0, false }
#define STALL720 { true, 5, 1280, 720, false }
#define BADGUARD { false, 5, 1280, 720, true }
#define PORT3_STALE { true, 3, 1280, 720, true }

static const struct h713_sig_config cfg_default = { 200, 100, 1500, false };
static const struct h713_sig_config cfg_480 = { 200, 100, 1500, true };

static void run(const struct h713_sig_config *cfg, const struct seg *segs,
		unsigned int n)
{
	struct h713_sig sig;
	unsigned int t = 0, i, rng = 12345;

	h713_sig_init(&sig);
	ntr = 0;
	for (i = 0; i < n; i++) {
		unsigned int end = t + segs[i].ms;

		while (t < end) {
			unsigned int dt = segs[i].period ? segs[i].period : 20, ev;

			if (segs[i].jitter) {
				rng = rng * 1103515245u + 12345u;
				dt += (rng >> 16) % (segs[i].jitter + 1);
			}
			t += dt;
			ev = h713_sig_step(&sig, cfg, &segs[i].s, dt);
			if (ev && ntr < MAXT)
				tr[ntr++] = (struct transition){ t, sig.state, sig.width,
							       sig.height, ev };
		}
	}
}

static void check(int ok, const char *scenario, const char *what)
{
	if (!ok) {
		unsigned int i;

		printf("FAIL %s: %s\n", scenario, what);
		for (i = 0; i < ntr; i++)
			printf("    t=%u %s %ux%u ev=%u\n", tr[i].t, h713_sig_name(tr[i].state),
			       tr[i].w, tr[i].h, tr[i].ev);
		fails++;
	}
}

/* Transition k is `state` (and mode, when w) at a time in [lo, hi] with exactly `ev`. */
static int is(unsigned int k, enum h713_sig_state state, u16 w, u16 h,
	      unsigned int lo, unsigned int hi, unsigned int ev)
{
	return k < ntr && tr[k].state == state && (!w || (tr[k].w == w && tr[k].h == h)) &&
	       tr[k].t >= lo && tr[k].t <= hi && tr[k].ev == ev;
}

static int sources(void)
{
	unsigned int i, n = 0;

	for (i = 0; i < ntr; i++)
		n += !!(tr[i].ev & H713_SIG_EV_SOURCE);
	return n;
}

#define RUN(cfg, ...) do { \
	const struct seg s_[] = { __VA_ARGS__ }; \
	run(cfg, s_, sizeof(s_) / sizeof(s_[0])); \
} while (0)
#define ST H713_SIG_EV_STATE
#define SRC H713_SIG_EV_SOURCE

static void scenarios(void)
{
	const char *n;

	n = "no cable";
	RUN(&cfg_default, { 3000, DEAD });
	check(ntr == 0, n, "no transitions at all");

	n = "lock 720p";
	RUN(&cfg_default, { 200, DEAD }, { 2000, LIVE720 });
	check(ntr == 2, n, "two transitions");
	check(is(0, H713_SIG_ACQUIRING, 0, 0, 220, 220, ST), n, "ACQUIRING at the first live sample");
	check(is(1, H713_SIG_LOCKED, 1280, 720, 420, 440, ST | SRC), n,
	      "LOCKED 1280x720 with SOURCE_CHANGE after lock_ms");

	n = "login gap (same mode back within grace)";
	RUN(&cfg_default, { 1000, LIVE720 }, { 600, DEAD }, { 1000, LIVE720 });
	check(ntr == 4, n, "four transitions");
	check(is(2, H713_SIG_HOLD, 1280, 720, 1100, 1120, ST), n, "HOLD after hold_ms");
	check(is(3, H713_SIG_LOCKED, 1280, 720, 1800, 1840, ST), n,
	      "LOCKED again, no SOURCE_CHANGE");
	check(sources() == 1, n, "only the first lock raised SOURCE_CHANGE");

	n = "unplug";
	RUN(&cfg_default, { 1000, LIVE720 }, { 3000, DEAD });
	check(ntr == 4, n, "four transitions");
	check(is(2, H713_SIG_HOLD, 1280, 720, 1100, 1120, ST), n, "HOLD after hold_ms");
	check(is(3, H713_SIG_NONE, 0, 0, 2600, 2640, ST), n, "NO_SIGNAL after hold + grace");

	n = "gap exactly at grace";
	RUN(&cfg_default, { 1000, LIVE720 }, { 1700, DEAD }, { 1000, LIVE720 });
	check(is(3, H713_SIG_NONE, 0, 0, 2600, 2640, ST), n, "grace expires during the gap");
	check(is(4, H713_SIG_ACQUIRING, 0, 0, 2700, 2720, ST), n, "re-acquire afterwards");
	check(is(5, H713_SIG_LOCKED, 1280, 720, 2900, 2940, ST | SRC), n,
	      "fresh lock raises SOURCE_CHANGE");

	n = "720p -> 640x480, 480p not allowed";
	RUN(&cfg_default, { 1000, LIVE720 }, { 200, DEAD }, { 1500, LIVE480 }, { 300, DEAD },
	    { 1000, LIVE720 });
	check(is(2, H713_SIG_HOLD, 1280, 720, 1100, 1120, ST), n, "HOLD");
	check(is(3, H713_SIG_UNSUPPORTED, 640, 480, 1400, 1440, ST), n,
	      "UNSUPPORTED 640x480, no SOURCE_CHANGE");
	check(is(4, H713_SIG_NONE, 0, 0, 2800, 2820, ST), n, "NO_SIGNAL when 480p goes");
	check(is(6, H713_SIG_LOCKED, 1280, 720, 3220, 3260, ST | SRC), n, "720p locks again");

	n = "720p -> 640x480, 480p allowed";
	RUN(&cfg_480, { 1000, LIVE720 }, { 200, DEAD }, { 1000, LIVE480 });
	check(ntr == 4, n, "four transitions");
	check(is(3, H713_SIG_LOCKED, 640, 480, 1400, 1440, ST | SRC), n,
	      "LOCKED 640x480 straight from HOLD with SOURCE_CHANGE");

	n = "1080p source";
	RUN(&cfg_480, { 1000, LIVE1080 });
	check(is(1, H713_SIG_UNSUPPORTED, 1920, 1080, 220, 240, ST), n,
	      "an unoffered size is UNSUPPORTED even with 480p allowed");

	n = "mode switches with no gap";
	RUN(&cfg_480, { 1000, LIVE720 }, { 1000, LIVE480 });
	check(is(2, H713_SIG_HOLD, 1280, 720, 1100, 1120, ST), n, "HOLD after hold_ms");
	check(is(3, H713_SIG_LOCKED, 640, 480, 1300, 1340, ST | SRC), n, "new mode locks");

	n = "flapping while acquiring";
	{
		struct seg segs[40];
		unsigned int i;

		for (i = 0; i < 40; i++)
			segs[i] = (struct seg){ i % 2 ? 60 : 100,
						i % 2 ? (struct h713_sig_sample)DEAD :
							(struct h713_sig_sample)LIVE720 };
		run(&cfg_default, segs, 40);
		check(sources() == 0, n, "never locks on 100 ms bursts");
	}

	n = "ring stalls with port still at 5";
	RUN(&cfg_default, { 1000, LIVE720 }, { 3000, STALL720 });
	check(is(2, H713_SIG_HOLD, 1280, 720, 1100, 1120, ST), n, "HOLD");
	check(is(3, H713_SIG_NONE, 0, 0, 2600, 2640, ST), n, "NO_SIGNAL after grace");

	n = "port-object guard fails";
	RUN(&cfg_default, { 1000, LIVE720 }, { 3000, BADGUARD });
	check(is(3, H713_SIG_NONE, 0, 0, 2600, 2640, ST), n,
	      "an unreadable port object is never live");

	n = "port not at state 5";
	RUN(&cfg_default, { 3000, PORT3_STALE });
	check(ntr == 0, n, "a stale size with the ring moving is not a signal");

	n = "dropout during a HOLD relock";
	RUN(&cfg_default, { 1000, LIVE720 }, { 200, DEAD }, { 160, LIVE720 }, { 40, DEAD },
	    { 1000, LIVE720 });
	check(ntr == 4 && is(3, H713_SIG_LOCKED, 1280, 720, 1620, 1640, ST), n,
	      "the lock timer restarts after the dropout");

	n = "unsupported straight to 720p";
	RUN(&cfg_default, { 1000, LIVE1080 }, { 1000, LIVE720 });
	check(ntr == 4, n, "four transitions, no NO_SIGNAL in between");
	check(is(2, H713_SIG_ACQUIRING, 0, 0, 1020, 1020, ST), n,
	      "ACQUIRING at the first sample of the new size");
	check(is(3, H713_SIG_LOCKED, 1280, 720, 1220, 1240, ST | SRC), n, "720p locks");

	n = "single missed sample";
	RUN(&cfg_default, { 1000, LIVE720 }, { 20, DEAD }, { 1000, LIVE720 },
	    { 80, STALL720 }, { 1000, LIVE720 });
	check(ntr == 2, n, "dropouts shorter than hold_ms change nothing");

	n = "sampler jitter";
	{
		const struct seg segs[] = {
			{ 500, DEAD, 20, 25 }, { 3000, LIVE720, 20, 25 },
		};

		run(&cfg_default, segs, 2);
		check(ntr == 2 && tr[1].state == H713_SIG_LOCKED &&
		      tr[1].t - tr[0].t >= 200 && tr[1].t - tr[0].t <= 245, n,
		      "lock after lock_ms of live time, at most one late period");
	}

	n = "HOLD with an unstable candidate";
	{
		struct seg segs[40];
		unsigned int i;

		segs[0] = (struct seg){ 1000, LIVE720 };
		for (i = 1; i < 40; i++)
			segs[i] = (struct seg){ 60, i % 2 ? (struct h713_sig_sample)LIVE480 :
							(struct h713_sig_sample)LIVE1080 };
		run(&cfg_480, segs, 40);
		check(is(3, H713_SIG_NONE, 0, 0, 2600, 2640, ST) && sources() == 1, n,
		      "no lock on a size that keeps changing; NO_SIGNAL after grace");
	}
}

static int trace(void)
{
	static const struct h713_sig_config *cfg = &cfg_default;
	struct h713_sig sig;
	unsigned int t = 0, dt, valid, state, w, h, moving, ev;

	h713_sig_init(&sig);
	while (scanf("%u %u %u %u %u %u", &dt, &valid, &state, &w, &h, &moving) == 6) {
		struct h713_sig_sample s = { valid, state, (u16)w, (u16)h, moving };

		t += dt;
		ev = h713_sig_step(&sig, cfg, &s, dt);
		if (ev)
			printf("%u %s %ux%u %u\n", t, h713_sig_name(sig.state), sig.width,
			       sig.height, ev);
	}
	return 0;
}

int main(int argc, char **argv)
{
	if (argc > 1 && !strcmp(argv[1], "--trace"))
		return trace();
	scenarios();
	printf("signal self-test %s\n", fails ? "FAILED" : "passed");
	return fails ? 1 : 0;
}
