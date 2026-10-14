// SPDX-License-Identifier: GPL-2.0-only
/* Driver-owned stock DSP initialization; receiver/source3 must be ready. */
#include <linux/delay.h>
#include <linux/firmware.h>
#include <linux/io.h>
#include <linux/ioport.h>
#include <linux/iopoll.h>
#include <linux/ktime.h>
#include <linux/module.h>
#include <linux/unaligned.h>
#include <crypto/sha2.h>
#include "h713-hdmi-dsp.h"
#include "../hdmi-dsp-probe/h713-dsp-lock.h"
#include "../hdmi-dsp-probe/h713-dsp-completion.h"

#define DSP_PORT 0x06144000
#define DSP_PORT_SIZE 0x1c
#define DSP_LOCK 0x05001530
#define DSP_LOCK_SIZE 8
#define DSP_FIRMWARE "h713/hdmi-audio-dsp.bin"
MODULE_FIRMWARE(DSP_FIRMWARE);
static const u8 patch_digest[SHA256_DIGEST_SIZE] = {
	0x8e, 0x31, 0xdb, 0x19, 0x9e, 0x00, 0x78, 0xd1, 0x42, 0xf6, 0x22,
	0x43, 0x6f, 0xf0, 0xb7, 0x24, 0x9b, 0x33, 0x3d, 0xbb, 0x6d, 0xf8,
	0xec, 0x3f, 0xba, 0xbc, 0x0d, 0x8f, 0xea, 0x6e, 0xa0, 0xc5,
};
struct graph_setting {
	u16 address, mask, value;
};
static const struct graph_setting graph_settings[] = {
	{ 0x0003, 0x0f00, 0x0300 },
	{ 0x800c, 0x00f8, 0x0080 },
	{ 0x800d, 0x00ff, 0x0000 },
	{ 0x00ac, 0xffff, 0x0000 },
	{ 0x0077, 0xffff, 0x1617 },
	{ 0x004d, 0xffff, 0x696a },
	{ 0x805a, 0x00ff, 0x007d },
	{ 0x8059, 0x00ff, 0x007c },
	{ 0x0130, 0xffff, 0x696a },
	{ 0x0012, 0xa3ff, 0x8180 },
	{ 0x0017, 0xff00, 0x2000 },
	{ 0x801a, 0x0002, 0x0000 },
	{ 0x8017, 0x0001, 0x0000 },
	/* graph_chain only, from tools/stock/decode-graph-edges.py and
  * decode-path-unmute.py: the route 8f data path is
  * 9600 -> 8400 -> 8500 -> 8f01 in2/3 -> 9009/900a -> DTVOUT1. The 13 words
  * above leave 8400 -> 8500 -> 8f01 unwired and its mixer gains unset.
  */
	{ 0x007c, 0xffff, 0x8081 }, /* 8500.0/1 <- 8400.0/1 */
	{ 0x007d, 0xffff, 0x8283 }, /* 8500.2/3 <- 8400.2/3 */
	{ 0x007e, 0xffff, 0x8485 }, /* 8500.4/5 <- 8400.4/5 */
	{ 0x8102, 0x00ff, 0x0086 }, /* 8f01.2 <- 8500.0 */
	{ 0x8103, 0x00ff, 0x0087 }, /* 8f01.3 <- 8500.1 */
	{ 0x0102, 0xff00, 0x2000 }, /* mixer 8f01 out0 <- in2 gain 0x20 */
	{ 0x0103, 0x00ff, 0x0020 }, /* mixer 8f01 out1 <- in3 gain 0x20 */
	/* HAL Check_Sound_Unmute(path 8f): clear user mute and 0 dB on 9009/900a. */
	{ 0x0059, 0xffc0, 0x0000 },
	{ 0x005a, 0xffc0, 0x0000 },
};

static void __iomem *port, *lock_window;
static struct h713_dsp_lock dsp_lock;
static bool port_claimed, lock_claimed, graph_active;
static unsigned int graph_written;
static u16 graph_saved[ARRAY_SIZE(graph_settings)];
bool h713_dsp_failed;

static int dsp_read(unsigned int device, u16 address, u32 *response)
{
	u32 status;
	int ret;
	if (h713_dsp_failed)
		return -EIO;
	ret = readl_poll_timeout(port, status, !(status & BIT(device ? 7 : 4)),
				 10, 50000);
	if (!ret)
		ret = h713_dsp_stock_response(port,
					      port + (device ? 0x18 : 0x10),
					      address, BIT(device ? 8 : 5),
					      &status, response);
	if (ret) {
		h713_dsp_failed = true;
		pr_err("h713-hdmi-audio: DSP read %u:%04x failed %d status=%08x; cold boot required\n",
		       device, address, ret, status);
	}
	return ret;
}

static int dsp_write(u16 address, u16 value)
{
	u32 status;
	int ret;
	if (h713_dsp_failed)
		return -EIO;
	ret = readl_poll_timeout(port, status, !(status & BIT(4)), 10, 50000);
	if (!ret) {
		writel(((u32)address << 16) | value, port + 0xc);
		usleep_range(1000, 1100);
		ret = readl_poll_timeout(port, status, !(status & BIT(4)), 10,
					 50000);
	}
	if (ret) {
		h713_dsp_failed = true;
		pr_err("h713-hdmi-audio: DSP write %04x failed; cold boot required\n",
		       address);
	}
	return ret;
}

static int write_verified(u16 address, u16 value)
{
	u32 result;
	int ret = dsp_write(address, value);
	if (!ret)
		ret = dsp_read(0, address, &result);
	if (!ret && (result & 0xffff) != value)
		ret = -EIO;
	if (ret)
		h713_dsp_failed = true;
	return ret;
}

static int stock_mask(u16 address, u16 mask, u16 value)
{
	u32 before;
	int ret = dsp_read(0, address, &before);
	if (ret)
		return ret;
	return write_verified(address, (before & ~mask) | (value & mask));
}

static int initialize_patch(const struct firmware *firmware)
{
	u32 version0, version1;
	unsigned int i;
	int ret = dsp_read(0, 0x80ff, &version0);
	if (!ret)
		ret = dsp_read(1, 0x80ff, &version1);
	if (ret)
		return ret;
	pr_info("h713-hdmi-audio: DSP versions %04x/%04x\n", version0 & 0xffff,
		version1 & 0xffff);
	/* Do not adopt or overwrite externally initialized DSP state. */
	if ((version0 & 0xffff) || (version1 & 0xffff))
		return -EBUSY;
	ret = stock_mask(0x00ee, 0x7f80, 3 << 7);
	if (!ret)
		ret = stock_mask(0x8034, 0x90, 0x10);
	if (!ret)
		ret = stock_mask(0x8017, 1, 1);
	if (!ret)
		ret = dsp_write(0xfff7, 0);
	if (!ret)
		ret = dsp_write(0, 0);
	for (i = 0; !ret && i < firmware->size; i += 4)
		ret = dsp_write(get_unaligned_be16(firmware->data + i),
				get_unaligned_be16(firmware->data + i + 2));
	if (ret)
		return ret;
	usleep_range(100000, 101000);
	ret = dsp_read(0, 0xfff7, &version0);
	if (!ret)
		ret = dsp_read(0, 0x80ff, &version0);
	if (!ret)
		ret = dsp_read(1, 0x80ff, &version1);
	if (!ret && ((version0 & 0xffff) != 1 || (version1 & 0xffff) != 1))
		ret = -ENODEV;
	if (ret)
		h713_dsp_failed = true;
	else
		pr_info("h713-hdmi-audio: pinned 724-pair DSP patch verified versions 1/1\n");
	return ret;
}

int h713_hdmi_dsp_reserve(void)
{
	if (!request_mem_region(DSP_PORT, DSP_PORT_SIZE, "h713-hdmi-audio-dsp"))
		return -EBUSY;
	port_claimed = true;
	if (!request_mem_region(DSP_LOCK, DSP_LOCK_SIZE, "h713-hdmi-audio-dsp-lock")) {
		release_mem_region(DSP_PORT, DSP_PORT_SIZE);
		port_claimed = false;
		return -EBUSY;
	}
	lock_claimed = true;
	return 0;
}

int h713_hdmi_dsp_prepare(struct device *device)
{
	const struct firmware *firmware;
	u8 digest[SHA256_DIGEST_SIZE];
	u32 word;
	unsigned int i;
	bool claimed = false;
	int ret;
	if (!port_claimed || !lock_claimed)
		return -EPERM;
	ret = request_firmware_direct(&firmware, DSP_FIRMWARE, device);
	if (ret)
		return ret;
	sha256(firmware->data, firmware->size, digest);
	if (firmware->size != 2896 ||
	    memcmp(digest, patch_digest, sizeof(digest))) {
		ret = -EINVAL;
		goto out_firmware;
	}
	port = ioremap(DSP_PORT, DSP_PORT_SIZE);
	lock_window = ioremap(DSP_LOCK, DSP_LOCK_SIZE);
	if (!port || !lock_window) {
		ret = -ENOMEM;
		goto out_firmware;
	}
	dsp_lock.peer = lock_window;
	dsp_lock.own = lock_window + 4;
	ret = h713_dsp_claim(&dsp_lock);
	if (ret)
		goto out_firmware;
	claimed = true;
	ret = initialize_patch(firmware);
	if (ret)
		goto out_firmware;
	for (i = 0; i < ARRAY_SIZE(graph_settings); i++) {
		ret = dsp_read(0, graph_settings[i].address, &word);
		if (ret)
			goto out_firmware;
		graph_saved[i] = word & 0xffff;
	}
	for (i = 0; i < ARRAY_SIZE(graph_settings); i++) {
		u16 expected = (graph_saved[i] & ~graph_settings[i].mask) |
			       graph_settings[i].value;
		graph_written = i + 1;
		ret = write_verified(graph_settings[i].address, expected);
		if (ret)
			goto out_firmware;
	}
	graph_active = true;
	pr_info("h713-hdmi-audio: managed DSP graph verified 22 words\n");
out_firmware:
	if (claimed) {
		int release_ret = h713_dsp_release(&dsp_lock);
		if (release_ret) {
			h713_dsp_failed = true;
			ret = release_ret;
		}
	}
	release_firmware(firmware);
	if (ret && h713_dsp_failed)
		pr_err("h713-hdmi-audio: DSP initialization failed; no more DSP commands; cold boot required\n");
	return ret;
}

void h713_hdmi_dsp_release(void)
{
	int ret = 0;
	if (graph_active && !h713_dsp_failed) {
		ret = h713_dsp_claim(&dsp_lock);
		if (!ret) {
			while (graph_written) {
				unsigned int index = graph_written - 1;
				ret = write_verified(
					graph_settings[index].address,
					graph_saved[index]);
				if (ret)
					break;
				pr_info("h713-hdmi-audio: DSP restore %04x=%04x verified\n",
					graph_settings[index].address,
					graph_saved[index]);
				graph_written--;
			}
			if (h713_dsp_release(&dsp_lock))
				ret = -EIO;
		}
		if (ret)
			h713_dsp_failed = true;
		else
			pr_info("h713-hdmi-audio: managed DSP graph restored 22 words\n");
	}
	if (h713_dsp_failed || (graph_active && graph_written))
		pr_err("h713-hdmi-audio: DSP state partial; physical cold boot required\n");
	graph_active = false;
	if (port)
		iounmap(port);
	if (lock_window)
		iounmap(lock_window);
	port = lock_window = NULL;
	if (lock_claimed)
		release_mem_region(DSP_LOCK, DSP_LOCK_SIZE);
	if (port_claimed)
		release_mem_region(DSP_PORT, DSP_PORT_SIZE);
	lock_claimed = port_claimed = false;
}
