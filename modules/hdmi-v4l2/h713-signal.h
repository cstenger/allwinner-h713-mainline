/* SPDX-License-Identifier: GPL-2.0 */
/*
 * HDMI-in signal state machine for the H713 ring bridge (HDMI panel-source
 * design section 3, revised for route B in 10.26). Shared by the kernel
 * module and the host self-test (tools/hdmi/test-signal-state.c), so the
 * code that runs is the code tested.
 *
 * Input, every sample (about 20 ms apart): the firmware's HDMI port 1 state
 * and active size, whether the port-object guards passed, and whether the
 * capture ring advanced since the previous sample (AFBD +0x320 moved; the
 * production firmware has no VIncap hook, 10.25.5). The source is "live"
 * when all of: guards pass, port state 5, a non-zero size, the ring moving.
 *
 *   NO_SIGNAL    not live
 *   ACQUIRING    live, same size for less than lock_ms
 *   LOCKED(m)    live at m for lock_ms, and m supported
 *   HOLD(m)      was LOCKED(m); not live at m for hold_ms. The bridge hands
 *                out black frames. Back to LOCKED(m) silently, to LOCKED(m')
 *                with SOURCE_CHANGE, or to NO_SIGNAL after grace_ms
 *   UNSUPPORTED  live and stable at a size the panel route doesn't take
 *
 * The includer provides u16, u32 and bool.
 */
#ifndef H713_SIGNAL_H
#define H713_SIGNAL_H

enum h713_sig_state {
	H713_SIG_NONE,
	H713_SIG_ACQUIRING,
	H713_SIG_LOCKED,
	H713_SIG_HOLD,
	H713_SIG_UNSUPPORTED,
};

/* What a step changed. */
#define H713_SIG_EV_STATE	0x1	/* state or mode changed: attribute + uevent */
#define H713_SIG_EV_SOURCE	0x2	/* new locked resolution: V4L2 SOURCE_CHANGE */

struct h713_sig_sample {
	bool valid;		/* port-object guards passed */
	u32 port_state;		/* port +0xC0; 5 = live timing */
	u16 width;		/* port +0x4E */
	u16 height;		/* port +0x48 */
	bool moving;		/* ring pair advanced since the last sample */
};

struct h713_sig_config {
	unsigned int lock_ms;	/* live and unchanged this long to lock */
	unsigned int hold_ms;	/* LOCKED -> HOLD after this long not live at m */
	unsigned int grace_ms;	/* HOLD -> NO_SIGNAL after this long */
	bool allow_480p;	/* 640x480 counts as supported (Q9) */
};

struct h713_sig {
	enum h713_sig_state state;
	u16 width, height;		/* the mode of LOCKED/HOLD/UNSUPPORTED */
	u16 cand_width, cand_height;	/* candidate being timed */
	unsigned int stable_ms;		/* candidate live this long */
	unsigned int quiet_ms;		/* LOCKED/UNSUPPORTED: not live at m this long */
	unsigned int hold_elapsed_ms;	/* time spent in HOLD */
};

static inline bool h713_sig_supported(const struct h713_sig_config *cfg,
				      u16 w, u16 h)
{
	return (w == 1280 && h == 720) ||
	       (cfg->allow_480p && w == 640 && h == 480);
}

static inline bool h713_sig_live(const struct h713_sig_sample *s)
{
	return s->valid && s->port_state == 5 && s->width && s->height &&
	       s->moving;
}

static inline void h713_sig_init(struct h713_sig *sig)
{
	sig->state = H713_SIG_NONE;
	sig->width = sig->height = 0;
	sig->cand_width = sig->cand_height = 0;
	sig->stable_ms = sig->quiet_ms = sig->hold_elapsed_ms = 0;
}

/* Time the candidate mode; true once it has been live for lock_ms. */
static inline bool h713_sig_track(struct h713_sig *sig,
				  const struct h713_sig_config *cfg,
				  const struct h713_sig_sample *s,
				  unsigned int dt_ms)
{
	if (!h713_sig_live(s)) {
		sig->stable_ms = 0;
		sig->cand_width = sig->cand_height = 0;
		return false;
	}
	if (s->width != sig->cand_width || s->height != sig->cand_height) {
		sig->cand_width = s->width;
		sig->cand_height = s->height;
		sig->stable_ms = 0;
		return false;
	}
	sig->stable_ms += dt_ms;
	return sig->stable_ms >= cfg->lock_ms;
}

static inline unsigned int h713_sig_enter(struct h713_sig *sig,
					  enum h713_sig_state state,
					  u16 w, u16 h)
{
	sig->state = state;
	sig->width = w;
	sig->height = h;
	sig->quiet_ms = 0;
	sig->hold_elapsed_ms = 0;
	if (state == H713_SIG_NONE)
		sig->cand_width = sig->cand_height = sig->stable_ms = 0;
	return H713_SIG_EV_STATE;
}

/* Lock the timed candidate: LOCKED if supported, otherwise UNSUPPORTED. */
static inline unsigned int h713_sig_lock(struct h713_sig *sig,
					 const struct h713_sig_config *cfg)
{
	u16 w = sig->cand_width, h = sig->cand_height;

	if (!h713_sig_supported(cfg, w, h))
		return h713_sig_enter(sig, H713_SIG_UNSUPPORTED, w, h);
	return h713_sig_enter(sig, H713_SIG_LOCKED, w, h);
}

/* One sample, dt_ms after the previous one. Returns H713_SIG_EV_* bits. */
static inline unsigned int h713_sig_step(struct h713_sig *sig,
					 const struct h713_sig_config *cfg,
					 const struct h713_sig_sample *s,
					 unsigned int dt_ms)
{
	bool live = h713_sig_live(s);
	bool at_mode = live && s->width == sig->width &&
		       s->height == sig->height;
	u16 old_w = sig->width, old_h = sig->height;
	unsigned int ev;

	switch (sig->state) {
	case H713_SIG_NONE:
		if (!live)
			return 0;
		h713_sig_track(sig, cfg, s, 0);
		sig->state = H713_SIG_ACQUIRING;
		return H713_SIG_EV_STATE;
	case H713_SIG_ACQUIRING:
		if (!live)
			return h713_sig_enter(sig, H713_SIG_NONE, 0, 0);
		if (!h713_sig_track(sig, cfg, s, dt_ms))
			return 0;
		ev = h713_sig_lock(sig, cfg);
		return sig->state == H713_SIG_LOCKED ? ev | H713_SIG_EV_SOURCE : ev;
	case H713_SIG_LOCKED:
		if (at_mode) {
			sig->quiet_ms = 0;
			return 0;
		}
		sig->quiet_ms += dt_ms;
		if (sig->quiet_ms < cfg->hold_ms)
			return 0;
		ev = h713_sig_enter(sig, H713_SIG_HOLD, old_w, old_h);
		sig->cand_width = sig->cand_height = sig->stable_ms = 0;
		h713_sig_track(sig, cfg, s, 0);
		return ev;
	case H713_SIG_HOLD:
		sig->hold_elapsed_ms += dt_ms;
		if (h713_sig_track(sig, cfg, s, dt_ms)) {
			if (sig->cand_width == old_w && sig->cand_height == old_h) {
				/* The same mode is back: frames resume, no event. */
				sig->state = H713_SIG_LOCKED;
				sig->quiet_ms = sig->hold_elapsed_ms = 0;
				return H713_SIG_EV_STATE;
			}
			ev = h713_sig_lock(sig, cfg);
			return sig->state == H713_SIG_LOCKED ?
			       ev | H713_SIG_EV_SOURCE : ev;
		}
		if (sig->hold_elapsed_ms >= cfg->grace_ms)
			return h713_sig_enter(sig, H713_SIG_NONE, 0, 0);
		return 0;
	case H713_SIG_UNSUPPORTED:
		if (at_mode) {
			sig->quiet_ms = 0;
			return 0;
		}
		if (live) {
			/* A different size: time it from scratch. */
			sig->state = H713_SIG_ACQUIRING;
			sig->width = sig->height = 0;
			sig->quiet_ms = 0;
			h713_sig_track(sig, cfg, s, 0);
			return H713_SIG_EV_STATE;
		}
		sig->quiet_ms += dt_ms;
		if (sig->quiet_ms < cfg->hold_ms)
			return 0;
		return h713_sig_enter(sig, H713_SIG_NONE, 0, 0);
	}
	return 0;
}

static inline const char *h713_sig_name(enum h713_sig_state state)
{
	switch (state) {
	case H713_SIG_NONE:
		return "none";
	case H713_SIG_ACQUIRING:
		return "acquiring";
	case H713_SIG_LOCKED:
		return "locked";
	case H713_SIG_HOLD:
		return "holding";
	case H713_SIG_UNSUPPORTED:
		return "unsupported";
	}
	return "none";
}

#endif
