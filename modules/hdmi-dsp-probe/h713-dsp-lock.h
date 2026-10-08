/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef H713_DSP_LOCK_H
#define H713_DSP_LOCK_H
/* Stock snd_alsa_trid WaitDSPFree/ReleaseDSP, with bounded waits.
 * ARM claims 05001534; MIPS peer is 05001530. Never write the peer word.
 * Caller must serialize ARM clients, hold the powered register window and
 * exclude every other diagnostic module accessing the same DSP port.
 */
struct h713_dsp_lock {
	void __iomem *peer;
	void __iomem *own;
};
static inline int h713_dsp_release(struct h713_dsp_lock *lock)
{
	writel(0xaa, lock->own);
	return readl(lock->own) == 0xaa ? 0 : -EIO;
}
static inline int h713_dsp_claim(struct h713_dsp_lock *lock)
{
	u32 peer;
	int ret;
	/* Do not steal a claim from another ARM client or clear a stale claim. */
	if (readl(lock->own) == 0x55)
		return -EBUSY;
	ret = readl_poll_timeout(lock->peer, peer, peer != 0x55, 10, 10000);
	if (ret)
		return ret;
	writel(0x55, lock->own);
	if (readl(lock->own) != 0x55) {
		h713_dsp_release(lock);
		return -EIO;
	}
	/* Stock rechecks the peer after publishing its own claim. */
	ret = readl_poll_timeout(lock->peer, peer, peer != 0x55, 10, 10000);
	if (ret && h713_dsp_release(lock))
		return -EIO;
	return ret;
}
#endif
