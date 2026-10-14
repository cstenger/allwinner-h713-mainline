/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef H713_RECEIVER_POLICY_H
#define H713_RECEIVER_POLICY_H
/* Unknown/nonzero status fails closed; only proven parked status permits off. */
static inline bool h713_receiver_release_allowed(unsigned int mips_status,
						 unsigned int clients)
{
	return mips_status == 0 && clients == 0;
}
static inline bool h713_receiver_park_allowed(unsigned int mips_status,
                                             unsigned int clients,
                                             bool ready, bool accepting,
                                             int init_error)
{
 return mips_status == 1 && clients == 0 && ready && accepting && !init_error;
}
static inline bool h713_receiver_clock_step_allowed(unsigned int enabled,
						   unsigned int next)
{
	return enabled <= 4 && next <= 4 &&
	       (next == enabled || next == enabled + 1);
}
#endif
