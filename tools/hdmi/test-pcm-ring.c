/* SPDX-License-Identifier: GPL-2.0-only */
/* Native tests of address reconstruction and wrap handling used by the IRQ. */
#include <assert.h>
#include <stdio.h>
#include "../../modules/hdmi-audio/h713-pcm-ring.h"

int main(void)
{
	u32 offset, base = 0x76c60000, size = 65536, last = 0, total = 0;
	unsigned int n;

	/* Real diagnostic DMA address, high register includes unrelated bits. */
	assert(h713_pcm_address(0xffff007f, 0xab6c6000) == base);
	assert(!h713_pcm_offset(base, size, base, &offset) && offset == 0);
	assert(!h713_pcm_offset(base, size, base + size, &offset) && offset == 0);
	assert(h713_pcm_offset(base, size, base - 16, &offset));
	assert(h713_pcm_offset(base, size, base + size + 16, &offset));
	assert(h713_pcm_offset(base, size, base + 1, &offset));
	/* Three wraps with delayed IRQs spanning three completed periods. */
	for (n = 1; n <= 64; n++) {
		u32 next = (n * 3072) % size;
		u32 address = h713_pcm_address(0x70, ((base + next) >> 4) & 0xffffff);

		assert(!h713_pcm_offset(base, size, address, &offset));
		total += h713_pcm_advance(last, offset, size);
		last = offset;
	}
	assert(total == 3 * size && last == 0);
	assert(h713_pcm_advance(64512, 2048, size) == 3072);
	assert(h713_pcm_advance(1024, 1024, size) == 0);
	puts("PCM pointer: address, range, alignment and multi-period wraps passed");
	return 0;
}
