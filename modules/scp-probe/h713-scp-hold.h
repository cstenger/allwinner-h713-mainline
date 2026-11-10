/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef H713_SCP_HOLD_H
#define H713_SCP_HOLD_H

static inline bool h713_scp_hold_valid(unsigned int milliseconds, bool long_hold)
{
	return milliseconds >= 1000 && milliseconds <= 3660000 &&
	       (milliseconds <= 150000 || long_hold);
}

#endif
