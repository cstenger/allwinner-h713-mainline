// SPDX-License-Identifier: GPL-2.0-only
/* Diagnostic only: stock DSP1 word-read protocol, with bounded waits.
 * Requires live source 3, receiver holds, stock-order TVFE hold, and the
 * audio probe's init_audio_top + stock_audio_ihb clock setup beforehand.
 * Optional explicit parameters apply the fixed stock volatile patch and
 * saved/restored route settings. No stream, DMA or interrupt writes.
 */
#include <linux/delay.h>
#include <linux/io.h>
#include <linux/iopoll.h>
#include <linux/irqflags.h>
#include <linux/module.h>
#include <linux/mutex.h>

#include "h713-dsp-lock.h"

static void __iomem *port, *lock_window;
static struct h713_dsp_lock dsp_lock;
static DEFINE_MUTEX(command_lock);
static bool armed, live_source3, audio_ready, failed, lock_window_ready;
module_param(armed, bool, 0400);
module_param(live_source3, bool, 0400);
module_param(audio_ready, bool, 0400);
module_param(lock_window_ready, bool, 0400);
MODULE_PARM_DESC(lock_window_ready, "Explicit acknowledgement: stock lock window power/clocks checked and exclusive ARM DSP client");
static unsigned int dsp_word;
static int dsp_read(unsigned int device, u16 address, u32 *response)
{
	unsigned long flags;
	u32 status;
	u32 busy_mask = BIT(device ? 7 : 4);
	u32 done_mask = BIT(device ? 8 : 5);
	u32 command_offset = device ? 0x18 : 0x10;
	const char *phase = "busy";
	int ret;
	ret = readl_poll_timeout(port, status, !(status & busy_mask), 10, 10000);
	if (ret)
		goto done;
	/* Completion is sticky after response reads. A new command must clear
	 * it before a fresh completion can be accepted. Never clear it manually.
	 */
	pr_info("h713-hdmi-dsp-probe: requesting device=%u word=%04x status=%08x\n", device,
		address, status);
	/* Keep the command-to-first-status-read gap short and non-schedulable.
	 * IRQs are disabled only for the bounded 100-us clear observation;
	 * the longer completion wait remains sleepable. No status writes.
	 */
	phase = "completion-clear";
	local_irq_save(flags);
	writel(address << 16, port + command_offset);
	ret = readl_poll_timeout_atomic(port, status, !(status & done_mask), 1, 100);
	local_irq_restore(flags);
	if (ret)
		goto done;
	phase = "completion-set";
	ret = readl_poll_timeout(port, status, status & done_mask, 10, 10000);
	if (ret)
		goto done;
	*response = readl(port + command_offset);
done:
	if (ret) {
		failed = true;
		pr_warn("h713-hdmi-dsp-probe: device=%u word=%04x phase=%s timeout status=%08x; "
			"cold boot required\n",
			device, address, phase, status);
	}
	return ret;
}

static int read_word(const char *value, const struct kernel_param *kp)
{
	unsigned int address, device;
	u32 status, response;
	int ret = kstrtouint(value, 0, &address);
	bool claimed = false;
	if (ret)
		return ret;
	/* Restrict this first experiment to independently decoded selector words
	 * and the vendor patch-version register. No arbitrary address access.
	 */
	if (address != 0x77 && address != 0x130 && address != 0xfff7 && address != 0x80ff &&
	    address != 0x180ff)
		return -EINVAL;
	device = address >> 16;
	address &= 0xffff;
	mutex_lock(&command_lock);
	if (!port || failed) {
		ret = -EIO;
		goto out;
	}
	ret = h713_dsp_claim(&dsp_lock);
	if (ret)
		goto out;
	claimed = true;	ret = dsp_read(device, address, &response);
	if (ret)
		goto release;
	status = readl(port);
	dsp_word = (device << 16) | address;
	pr_info("h713-hdmi-dsp-probe: device=%u word=%04x value=%04x response=%08x status=%08x\n",
		device, address, response & 0xffff, response, status);
	goto release;
release:
	if (claimed) {
		int release_ret = h713_dsp_release(&dsp_lock);

		pr_info("h713-hdmi-dsp-probe: stock DSP lock released ret=%d\n", release_ret);
		if (release_ret) {
			failed = true;
			ret = release_ret;
		}
	}
out:
	mutex_unlock(&command_lock);
	return ret;
}
static const struct kernel_param_ops word_ops = {
    .set = read_word,
    .get = param_get_uint,
};
module_param_cb(dsp_word, &word_ops, &dsp_word, 0600);
MODULE_PARM_DESC(
    dsp_word,
    "Bounded word read: 0x77/0x130/0xfff7/0x80ff on device0; 0x180ff on device1; never at insmod");

#ifdef H713_STOCK_DSP_PATCH
/* Generated only in an isolated diagnostic build from the SHA-256 pinned
 * stock binary; never compile an arbitrary patch provided by the target.
 */
struct dsp_pair {
	u16 address, value;
};
#include "stock-dsp-patch.h"
static bool stock_patch;
static bool patch_attempted;

static int dsp_write(u16 address, u16 value)
{
	u32 status;
	int ret = readl_poll_timeout(port, status, !(status & BIT(4)), 10, 10000);
	if (ret)
		return ret;
	writel(((u32)address << 16) | value, port + 0xc);
	/* Vendor patch loop sleeps one millisecond after every pair. */
	usleep_range(1000, 1100);
	return readl_poll_timeout(port, status, !(status & BIT(4)), 10, 10000);
}

static bool capture_route;
static bool dtvout_second;
static u16 dtvout_saved;
/* Direct preset route bd bypasses the processing graph selected by stock 8f.
 * Input format/prescale and DTV channel are recovered from stock initialization.
 * Every word is saved before applying the route and restored on explicit 0.
 */
static const u16 capture_words[] = { 0x130, 0x12, 0x17, 0x801a, 0x8017 };
static u16 capture_saved[ARRAY_SIZE(capture_words)];
static int set_capture_route(const char *value, const struct kernel_param *kp)
{
 bool next, claimed = false;
 u32 version0, version1, word;
 u16 target[ARRAY_SIZE(capture_words)];
 unsigned int i, index;
 int ret = kstrtobool(value, &next);
 if (ret)
  return ret;
 mutex_lock(&command_lock);
 if (!port || failed || next == capture_route || (!next && dtvout_second)) {
  ret = -EPERM;
  goto out;
 }
 ret = h713_dsp_claim(&dsp_lock);
 if (ret)
  goto out;
 claimed = true;
 if (next) {
  ret = dsp_read(0, 0x80ff, &version0);
  if (ret)
   goto release;
  ret = dsp_read(1, 0x80ff, &version1);
  if (ret)
   goto release;
  if ((version0 & 0xffff) != 1 || (version1 & 0xffff) != 1) {
   ret = -ENODEV;
   goto release;
  }
  for (i = 0; i < ARRAY_SIZE(capture_words); i++) {
   ret = dsp_read(0, capture_words[i], &word);
   if (ret)
    goto release;
   capture_saved[i] = word & 0xffff;
  }
 }
 target[0] = 0x1617;
 target[1] = (capture_saved[1] & ~0x23ff) | 0x8180;
 target[2] = (capture_saved[2] & ~0xff00) | 0x2000;
 target[3] = capture_saved[3] & ~2;
 target[4] = capture_saved[4] & ~1;
 for (i = 0; i < ARRAY_SIZE(capture_words); i++) {
  index = next ? i : ARRAY_SIZE(capture_words) - 1 - i;
  ret = dsp_write(capture_words[index], next ? target[index] : capture_saved[index]);
  if (ret)
   goto stop;
  ret = dsp_read(0, capture_words[index], &word);
  if (ret)
   goto stop;
  if ((word & 0xffff) != (next ? target[index] : capture_saved[index])) {
   ret = -EIO;
   goto stop;
  }
  pr_info("h713-hdmi-dsp-probe: capture word=%04x value=%04x saved=%04x restore=%u\n",
          capture_words[index], word & 0xffff, capture_saved[index], !next);
 }
 capture_route = next;
 pr_info("h713-hdmi-dsp-probe: direct capture route bd=%u verified\n", next);
 goto release;
stop:
 failed = true;
 pr_warn("h713-hdmi-dsp-probe: capture route stopped error=%d; cold boot required\n", ret);
release:
 if (claimed) {
  int release_ret = h713_dsp_release(&dsp_lock);
  pr_info("h713-hdmi-dsp-probe: stock DSP lock released ret=%d\n", release_ret);
  if (release_ret) {
   failed = true;
   ret = release_ret;
  }
 }
out:
 mutex_unlock(&command_lock);
 return ret;
}
static const struct kernel_param_ops capture_ops = {
    .set = set_capture_route,
    .get = param_get_bool,
};
module_param_cb(capture_route, &capture_ops, &capture_route, 0600);
MODULE_PARM_DESC(
    capture_route,
    "Direct route bd with stock I2SIN1 format/gain, DTV channel0 and unmute; explicit0 restores five words");

static int stock_mask(u16 address, u16 mask, u16 value)
{
	u32 before, after;
	u16 expected;
	int ret = dsp_read(0, address, &before);
	if (ret)
		return ret;
	expected = (before & ~mask) | (value & mask);
	ret = dsp_write(address, expected);
	if (ret)
		return ret;
	ret = dsp_read(0, address, &after);
	if (ret)
		return ret;
	pr_info("h713-hdmi-dsp-probe: stock-init word=%04x before=%04x after=%04x expected=%04x\n",
		address, before & 0xffff, after & 0xffff, expected);
	return ((after ^ expected) & mask) ? -EIO : 0;
}

/* Captured stock func_set_dtvout_channel: DSP0 word801a mask2, channel<<1.
 * Independent of route bd; keep every other bit and restore the saved word.
 */
static int set_dtvout_second(const char *value, const struct kernel_param *kp)
{
	bool next, claimed = false;
	u32 before, after;
	u16 expected;
	int ret = kstrtobool(value, &next);
	if (ret)
		return ret;
	mutex_lock(&command_lock);
	if (!port || failed || !capture_route || next == dtvout_second) {
		ret = -EPERM;
		goto out;
	}
	ret = h713_dsp_claim(&dsp_lock);
	if (ret)
		goto out;
	claimed = true;	ret = dsp_read(0, 0x801a, &before);
	if (ret)
		goto release;
	if (next)
		dtvout_saved = before & 0xffff;
	expected = next ? (dtvout_saved | 2) : dtvout_saved;
	ret = dsp_write(0x801a, expected);
	if (ret)
		goto release;
	ret = dsp_read(0, 0x801a, &after);
	if (ret)
		goto release;
	if ((after & 0xffff) != expected) {
		failed = true;
		ret = -EIO;
		goto release;
	}
	dtvout_second = next;
	pr_info("h713-hdmi-dsp-probe: dtvout_second=%u word801a=%04x saved=%04x\n",
		next, after & 0xffff, dtvout_saved);
release:
	if (claimed) {
		int release_ret = h713_dsp_release(&dsp_lock);

		pr_info("h713-hdmi-dsp-probe: stock DSP lock released ret=%d\n", release_ret);
		if (release_ret) {
			failed = true;
			ret = release_ret;
		}
	}
out:
	mutex_unlock(&command_lock);
	return ret;
}
static const struct kernel_param_ops dtvout_ops = {
	.set = set_dtvout_second,
	.get = param_get_bool,
};
module_param_cb(dtvout_second, &dtvout_ops, &dtvout_second, 0600);
MODULE_PARM_DESC(dtvout_second,
	"Stock DTV output channel1 selector; capture_route required; explicit0 restores saved word");

static int set_stock_patch(const char *value, const struct kernel_param *kp)
{
	bool next, claimed = false;
	u32 version0, version1;
	unsigned int i = 0;
	const char *phase = "readiness";
	int ret = kstrtobool(value, &next);
	if (ret)
		return ret;
	if (!next)
		return -EINVAL;
	mutex_lock(&command_lock);
	if (!port || failed || patch_attempted) {
		ret = -EPERM;
		goto out;
	}
	ret = h713_dsp_claim(&dsp_lock);
	if (ret)
		goto out;
	claimed = true;	ret = dsp_read(0, 0x80ff, &version0);
	if (ret)
		goto release;
	ret = dsp_read(1, 0x80ff, &version1);
	if (ret)
		goto release;
	/* Do not overwrite a DSP that already reports stock's ready versions. */
	if ((version0 & 0xffff) || (version1 & 0xffff)) {
		ret = -EBUSY;
		goto release;
	}
	patch_attempted = true;
	pr_info("h713-hdmi-dsp-probe: beginning fixed stock init/724-pair volatile patch; physical "
		"cold boot required for teardown\n");
	phase = "clock-init";
	ret = stock_mask(0x00ee, 0x7f80, 3 << 7);
	if (ret)
		goto stop;
	phase = "HDMI-input-init";
	ret = stock_mask(0x8034, 0x90, 0x10);
	if (ret)
		goto stop;
	phase = "I2S-mute-init";
	ret = stock_mask(0x8017, 1, 1);
	if (ret)
		goto stop;
	phase = "patch-prefix";
	ret = dsp_write(0xfff7, 0);
	if (ret)
		goto stop;
	ret = dsp_write(0, 0);
	if (ret)
		goto stop;
	phase = "patch-pairs";
	for (i = 0; i < ARRAY_SIZE(stock_dsp_patch); i++) {
		ret = dsp_write(stock_dsp_patch[i].address, stock_dsp_patch[i].value);
		if (ret)
			goto stop;
	}
	usleep_range(100000, 101000);
	phase = "patch-version";
	ret = dsp_read(0, 0xfff7, &version0);
	if (ret)
		goto stop;
	pr_info("h713-hdmi-dsp-probe: patch-word fff7=%04x\n", version0 & 0xffff);
	ret = dsp_read(0, 0x80ff, &version0);
	if (ret)
		goto stop;
	ret = dsp_read(1, 0x80ff, &version1);
	if (ret)
		goto stop;
	pr_info("h713-hdmi-dsp-probe: stock-patch pairs=%u version0=%04x version1=%04x\n", i,
		version0 & 0xffff, version1 & 0xffff);
	if (!(version0 & 0xffff) || !(version1 & 0xffff)) {
		ret = -ENODEV;
		goto stop;
	}
	stock_patch = true;
	goto release;
stop:
	failed = true;
	pr_warn("h713-hdmi-dsp-probe: stock-patch stopped phase=%s pair=%u error=%d; cold boot "
		"required\n",
		phase, i, ret);
release:
	if (claimed) {
		int release_ret = h713_dsp_release(&dsp_lock);

		pr_info("h713-hdmi-dsp-probe: stock DSP lock released ret=%d\n", release_ret);
		if (release_ret) {
			failed = true;
			ret = release_ret;
		}
	}
out:
	mutex_unlock(&command_lock);
	return ret;
}
static const struct kernel_param_ops patch_ops = {
    .set = set_stock_patch,
    .get = param_get_bool,
};
module_param_cb(stock_patch, &patch_ops, &stock_patch, 0600);
MODULE_PARM_DESC(
    stock_patch,
    "One-shot fixed stock volatile DSP patch; requires cold boot afterward; never at insmod");
#endif

static int __init probe_init(void)
{
	if (!armed || !live_source3 || !audio_ready || !lock_window_ready)
		return -EPERM;
	port = ioremap(0x06144000, 0x1c);
	lock_window = ioremap(0x05001530, 8);
	if (!port || !lock_window) {
		if (port)
			iounmap(port);
		if (lock_window)
			iounmap(lock_window);
		port = NULL;
		return -ENOMEM;
	}
	dsp_lock.peer = lock_window;
	dsp_lock.own = lock_window + 4;
	pr_info("h713-hdmi-dsp-probe: status=%08x; stock lock mapped; no command issued\n",
		readl(port));
	return 0;
}
static void __exit probe_exit(void)
{
	iounmap(port);
	iounmap(lock_window);
}
module_init(probe_init);
module_exit(probe_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Bounded H713 stock DSP access with stock cross-processor lock");
