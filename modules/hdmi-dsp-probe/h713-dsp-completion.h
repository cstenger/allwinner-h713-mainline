/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef H713_DSP_COMPLETION_H
#define H713_DSP_COMPLETION_H
/* Stock aud_dsp1_read_reg: after ownership and busy-clear, publish the
 * request, wait for done-set, consume the response. Completion can finish
 * before our first status read; no observable clear edge is required.
 * Caller retains the failure latch and must verify values for graph writes.
 */
static inline int h713_dsp_stock_response(void __iomem *status_port,
					 void __iomem *command_port, u16 address,
					 u32 done_mask, u32 *status, u32 *response)
{
	int ret;

	writel((u32)address << 16, command_port);
	ret = readl_poll_timeout(status_port, *status, (*status & done_mask),
				10, 50000);
	if (ret)
		return ret;
	*response = readl(command_port);
	return 0;
}

/* Continuous clear-edge observation with a real elapsed-time bound. Unlike
 * the atomic iopoll macro's iteration budget, this stays bounded when MMIO
 * reads are slow. Caller controls IRQ state; no sleep or register write here.
 */
static inline int h713_dsp_wait_clear_until(void __iomem *status_port, u32 *status,
					  u32 done_mask, u64 deadline)
{
	for (;;) {
		*status = readl(status_port);
		if (!(*status & done_mask))
			return 0;
		if (ktime_get_ns() >= deadline)
			return -ETIMEDOUT;
		cpu_relax();
	}
}
static inline int h713_dsp_wait_clear(void __iomem *status_port, u32 *status,
				    u32 done_mask, unsigned int timeout_us)
{
	return h713_dsp_wait_clear_until(status_port, status, done_mask,
			ktime_get_ns() + (u64)timeout_us * 1000);
}
#endif
