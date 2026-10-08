// SPDX-License-Identifier: GPL-2.0-only
/*
 * Diagnostic only: the audible HDMI split test.
 *
 * Stock Android plays HDMI audio as receiver -> MSP DSP I2SIN1 -> route 0x89
 * -> DSP I2S out -> codec internal I2S (0x02031000) -> codec DAC with
 * "DAC Src Select = I2S". This module reproduces the DSP and internal-I2S half
 * of that path so a listener can say whether HDMI audio reaches the DSP.
 *
 * insmod:  check both DSP versions are nonzero (stock patch already loaded),
 *          save and apply route 0x89 selectors, HDMI unmute and I2SIN1 enable,
 *          save and apply the stock internal-I2S init (vendor kernel
 *          0xc08320a0) plus the I2S half of the stock "DAC Src Select = I2S"
 *          put (0xc0831e2c).
 * dac_i2s: 1 sets DAC_DPC bits 30 and 29 (the DAC half of that put); 0 clears
 *          them. Toggle only while an ALSA playback stream keeps the DAC on.
 * rmmod:   restores every DSP word and codec register this module changed.
 *
 * The DSP command protocol is copied from h713-hdmi-dsp-probe, which was
 * validated on hardware. Its 0x02031078 "owner" handshake is NOT used: that
 * address is a register of the internal I2S block this module configures.
 */
#include <linux/delay.h>
#include <linux/io.h>
#include <linux/iopoll.h>
#include <linux/irqflags.h>
#include <linux/module.h>
#include <linux/mutex.h>

static void __iomem *port, *codec, *i2s;
static DEFINE_MUTEX(lock);
static bool armed, applied, dac_i2s, failed;
module_param(armed, bool, 0400);

static int dsp_read(u16 address, u32 *response)
{
	unsigned long flags;
	u32 status;
	int ret = readl_poll_timeout(port, status, !(status & BIT(4)), 10, 10000);

	if (ret)
		goto done;
	local_irq_save(flags);
	writel(address << 16, port + 0x10);
	ret = readl_poll_timeout_atomic(port, status, !(status & BIT(5)), 1, 100);
	local_irq_restore(flags);
	if (ret)
		goto done;
	ret = readl_poll_timeout(port, status, status & BIT(5), 10, 10000);
	if (ret)
		goto done;
	*response = readl(port + 0x10) & 0xffff;
done:
	if (ret) {
		failed = true;
		pr_warn("h713-speaker-split: read %04x timeout status=%08x\n", address, status);
	}
	return ret;
}

static int dsp_read1(u16 address, u32 *response)
{
	unsigned long flags;
	u32 status;
	int ret = readl_poll_timeout(port, status, !(status & BIT(7)), 10, 10000);

	if (ret)
		goto done;
	local_irq_save(flags);
	writel(address << 16, port + 0x18);
	ret = readl_poll_timeout_atomic(port, status, !(status & BIT(8)), 1, 100);
	local_irq_restore(flags);
	if (ret)
		goto done;
	ret = readl_poll_timeout(port, status, status & BIT(8), 10, 10000);
	if (ret)
		goto done;
	*response = readl(port + 0x18) & 0xffff;
done:
	if (ret) {
		failed = true;
		pr_warn("h713-speaker-split: dsp1 read %04x timeout status=%08x\n", address, status);
	}
	return ret;
}

static int dsp_write(u16 address, u16 value)
{
	u32 status;
	int ret = readl_poll_timeout(port, status, !(status & BIT(4)), 10, 10000);

	if (ret)
		return ret;
	writel(((u32)address << 16) | value, port + 0xc);
	usleep_range(1000, 1100);
	return readl_poll_timeout(port, status, !(status & BIT(4)), 10, 10000);
}

/* Write a whole word and read it back. */
static int dsp_set(u16 address, u16 value)
{
	u32 after = 0;
	int ret = dsp_write(address, value);

	if (!ret)
		ret = dsp_read(address, &after);
	if (!ret && after != value)
		ret = -EIO;
	pr_info("h713-speaker-split: dsp %04x <- %04x readback=%04x ret=%d\n", address, value,
		after, ret);
	if (ret)
		failed = true;
	return ret;
}

/* Route 0x89 (HDMI2PCM_MIXED_TO_S), decoded from the stock preset and executed
 * offline against the stock library; plus HDMI unmute and I2SIN1 enable.
 */
static const u16 dsp_words[] = { 0x0077, 0x0118, 0x0020, 0x8017, 0x0012 };
static u32 dsp_saved[ARRAY_SIZE(dsp_words)];

static u16 dsp_target(unsigned int i)
{
	switch (dsp_words[i]) {
	case 0x0077: return 0x1617;
	case 0x0118: return 0x7c7d;
	case 0x0020: return 0x2e2f;
	case 0x8017: return dsp_saved[i] & ~1;
	default:     return dsp_saved[i] | 0x8000;
	}
}

/* Internal I2S registers the stock init and put touch. */
static const u16 i2s_regs[] = { 0x00, 0x04, 0x08, 0x24, 0x30, 0x34, 0x48, 0x64, 0x74 };
static u32 i2s_saved[ARRAY_SIZE(i2s_regs)];
static u32 dpc_saved;

static void i2s_rmw(u16 reg, u32 mask, u32 value)
{
	writel((readl(i2s + reg) & ~mask) | (value & mask), i2s + reg);
}

static void apply_i2s(void)
{
	/* Vendor kernel 0xc08320a0, in its order. */
	i2s_rmw(0x00, 0x1, 0x1);
	i2s_rmw(0x04, 0x40000000, 0);
	i2s_rmw(0x04, 0x0003ff00, 0x1f00);
	i2s_rmw(0x04, 0x7, 0x5);
	i2s_rmw(0x24, 0xf, 0x4);
	i2s_rmw(0x24, 0x100, 0x100);
	i2s_rmw(0x00, 0x30, 0x10);
	i2s_rmw(0x04, 0x80000, 0x80000);
	i2s_rmw(0x04, 0x80, 0);
	i2s_rmw(0x24, 0xf0, 0x80);
	i2s_rmw(0x08, 0x40, 0);
	i2s_rmw(0x08, 0x80, 0);
	i2s_rmw(0x08, 0x30, 0x30);
	i2s_rmw(0x04, 0x70, 0x50);
	writel(0x100, i2s + 0x74);
	i2s_rmw(0x64, 0xf0000, 0x10000);
	i2s_rmw(0x30, 0xf0, 0x10);
	writel(0x3210, i2s + 0x48);
	i2s_rmw(0x34, 0xf0000, 0x10000);
	i2s_rmw(0x30, 0xf, 0x1);
	i2s_rmw(0x34, 0xffff, 0x3);
	/* I2S half of the stock DAC-source put (0xc0831e2c), value I2S. */
	i2s_rmw(0x00, 0x20000, 0);
	i2s_rmw(0x00, 0x40000, 0);
	i2s_rmw(0x00, 0x2, 0x2);
}

static void dump_i2s(const char *when)
{
	unsigned int i;

	for (i = 0; i < ARRAY_SIZE(i2s_regs); i++)
		pr_info("h713-speaker-split: %s i2s+%02x=%08x\n", when, i2s_regs[i],
			readl(i2s + i2s_regs[i]));
	pr_info("h713-speaker-split: %s ista=%08x fsta=%08x dac_dpc=%08x\n", when,
		readl(i2s + 0x0c), readl(i2s + 0x18), readl(codec));
}

static int set_dac(const char *value, const struct kernel_param *kp)
{
	bool next;
	int ret = kstrtobool(value, &next);

	if (ret)
		return ret;
	mutex_lock(&lock);
	if (!applied) {
		ret = -EPERM;
		goto out;
	}
	if (next)
		writel(readl(codec) | BIT(30) | BIT(29), codec);
	else
		writel(readl(codec) & ~(BIT(30) | BIT(29)), codec);
	dac_i2s = next;
	dump_i2s(next ? "dac-i2s" : "dac-apb");
out:
	mutex_unlock(&lock);
	return ret;
}
static const struct kernel_param_ops dac_ops = { .set = set_dac, .get = param_get_bool };
module_param_cb(dac_i2s, &dac_ops, &dac_i2s, 0600);

/* Read-only: live internal-I2S status on demand. */
static int show_status(char *buffer, const struct kernel_param *kp)
{
	return sysfs_emit(buffer, "ctl=%08x ista=%08x fsta=%08x rxcnt=%08x dac_dpc=%08x\n",
			  readl(i2s), readl(i2s + 0x0c), readl(i2s + 0x18),
			  readl(i2s + 0x2c), readl(codec));
}
static const struct kernel_param_ops status_ops = { .get = show_status };
module_param_cb(status, &status_ops, NULL, 0400);

static void restore_all(void)
{
	unsigned int i;

	writel((readl(codec) & ~(BIT(30) | BIT(29))) | (dpc_saved & (BIT(30) | BIT(29))), codec);
	for (i = ARRAY_SIZE(i2s_regs); i-- > 0;)
		writel(i2s_saved[i], i2s + i2s_regs[i]);
	if (failed) {
		pr_warn("h713-speaker-split: DSP failed earlier; DSP words left as they are\n");
		return;
	}
	for (i = 0; i < ARRAY_SIZE(dsp_words); i++)
		dsp_set(dsp_words[i], dsp_saved[i]);
	dump_i2s("restored");
}

static int __init split_init(void)
{
	u32 version0, version1;
	unsigned int i;
	int ret;

	if (!armed)
		return -EPERM;
	port = ioremap(0x06144000, 0x1c);
	codec = ioremap(0x02030000, 4);
	i2s = ioremap(0x02031000, 0x7c);
	if (!port || !codec || !i2s) {
		ret = -ENOMEM;
		goto unmap;
	}
	ret = dsp_read(0x80ff, &version0);
	if (!ret)
		ret = dsp_read1(0x80ff, &version1);
	if (ret)
		goto unmap;
	pr_info("h713-speaker-split: dsp versions %04x %04x\n", version0, version1);
	if (!version0 || !version1) {
		ret = -ENODEV;
		goto unmap;
	}
	for (i = 0; i < ARRAY_SIZE(dsp_words); i++) {
		ret = dsp_read(dsp_words[i], &dsp_saved[i]);
		if (ret)
			goto unmap;
		pr_info("h713-speaker-split: saved dsp %04x=%04x\n", dsp_words[i], dsp_saved[i]);
	}
	for (i = 0; i < ARRAY_SIZE(i2s_regs); i++)
		i2s_saved[i] = readl(i2s + i2s_regs[i]);
	dpc_saved = readl(codec);
	dump_i2s("before");

	for (i = 0; i < ARRAY_SIZE(dsp_words); i++) {
		ret = dsp_set(dsp_words[i], dsp_target(i));
		if (ret)
			break;
	}
	apply_i2s();
	applied = true;
	dump_i2s("applied");
	if (ret) {
		restore_all();
		goto unmap;
	}
	return 0;
unmap:
	if (port)
		iounmap(port);
	if (codec)
		iounmap(codec);
	if (i2s)
		iounmap(i2s);
	return ret;
}

static void __exit split_exit(void)
{
	mutex_lock(&lock);
	restore_all();
	mutex_unlock(&lock);
	iounmap(port);
	iounmap(codec);
	iounmap(i2s);
}
module_init(split_init);
module_exit(split_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("H713 audible HDMI split test: DSP route 0x89 into the codec DAC over I2S");
