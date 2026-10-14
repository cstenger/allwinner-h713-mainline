/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef H713_PCM_RING_H
#define H713_PCM_RING_H
#ifdef __KERNEL__
#include <linux/types.h>
#else
#include <stdint.h>
typedef uint32_t u32;
#endif

/* Stock audbrg_ostream_putdata2SW: address-high bits 7:4 supply PA31:28;
 * ostream +0x18 supplies PA27:4 in bits 23:0. No receiver MMIO involved.
 */
static inline u32 h713_pcm_address(u32 high, u32 pointer)
{
	return ((high & 0xf0) << 24) | ((pointer & 0xffffff) << 4);
}

static inline int h713_pcm_offset(u32 base, u32 size, u32 address, u32 *offset)
{
	u32 delta = address - base;

	if (!size || delta > size || (delta & 15))
		return -1;
	*offset = delta == size ? 0 : delta;
	return 0;
}

static inline u32 h713_pcm_advance(u32 old, u32 next, u32 size)
{
	return next >= old ? next - old : size - old + next;
}
#endif
