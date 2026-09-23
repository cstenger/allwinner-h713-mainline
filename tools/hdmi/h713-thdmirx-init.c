// SPDX-License-Identifier: GPL-2.0-only
/*
 * Opt-in H713 Synopsys HDMI-RX controller initializer.
 *
 * This reproduces the controller-side sequence from the independently
 * working sun50i-h713 HDMI-RX driver.  It deliberately touches only the
 * power/clock-gated THDMIRX window at 0x050c0000.  The H713 wrapper and
 * CPUS-domain HPD register remain owned by MIPS/SCP.
 */
#include <linux/bitfield.h>
#include <linux/delay.h>
#include <linux/io.h>
#include <linux/ioport.h>
#include <linux/module.h>

#define THDMIRX_BASE             0x050c0000
#define THDMIRX_SIZE             0x6000

#define GLOBAL_TIMER_REF_BASE    0x0028
#define CMU_CONFIG0              0x0060
#define PHY_CONFIG               0x00c0
#define DESCRAND_EN_CONTROL      0x0210
#define DEFRAMER_CONFIG0         0x0270
#define SCDC_CONFIG              0x0300
#define CED_CONFIG               0x0760
#define SCDC_REGBANK_STATUS1     0x0808
#define DMA_CONFIG11             0x4428
#define MAINUNIT_0_INT_MASK_N    0x5014
#define MAINUNIT_0_INT_CLEAR     0x5018
#define GLOBAL_SWENABLE          0x0024

#define CMU_TMDS_MARGIN          GENMASK(30, 16)
#define CMU_AUDIO_MARGIN         GENMASK(11, 9)
#define DESCRAND_SEL             GENMASK(1, 0)
#define DEFRAMER_VS_REMAP        BIT(8)
#define DEFRAMER_ORDER           GENMASK(1, 0)
#define CED_VIDEO_CHECK          BIT(27)
#define CED_GB_CHECK             BIT(25)
#define CED_CTRL_CHECK           BIT(24)
#define CED_LOCK_MAX             GENMASK(14, 0)
#define PHY_TMDS_CLOCK_RATIO     BIT(16)
#define PHY_RXDATA_WIDTH         BIT(15)
#define SCDC_TMDSBITCLKRATIO     BIT(1)
#define SCDC_HPDLOW              BIT(1)

#define SWENABLE_PHYCTRL         BIT(21)
#define SWENABLE_TMDS            BIT(13)
#define SWENABLE_DATAPATH        BIT(12)
#define SWENABLE_PKTFIFO         BIT(11)
#define SWENABLE_AVPUNIT         BIT(8)
#define SWENABLE_MAIN            BIT(0)
#define SWENABLE_FULL            (SWENABLE_PHYCTRL | SWENABLE_TMDS | \
                                  SWENABLE_DATAPATH | SWENABLE_PKTFIFO | \
                                  SWENABLE_AVPUNIT | SWENABLE_MAIN)

static bool apply;
module_param(apply, bool, 0400);
MODULE_PARM_DESC(apply, "Apply the known HDMI-RX controller enable sequence");

static void __iomem *base;
static bool region_owned;

struct saved_reg {
        u32 offset;
        u32 value;
};

static struct saved_reg saved[] = {
        { GLOBAL_TIMER_REF_BASE },
        { CMU_CONFIG0 },
        { PHY_CONFIG },
        { DESCRAND_EN_CONTROL },
        { DEFRAMER_CONFIG0 },
        { SCDC_CONFIG },
        { CED_CONFIG },
        { MAINUNIT_0_INT_MASK_N },
        { GLOBAL_SWENABLE },
};

static inline u32 rx_read(u32 offset)
{
        return readl(base + offset);
}

static inline void rx_write(u32 offset, u32 value)
{
        writel(value, base + offset);
        readl(base + offset);
}

static inline void rx_update(u32 offset, u32 mask, u32 value)
{
        rx_write(offset, (rx_read(offset) & ~mask) | (value & mask));
}

static int __init h713_thdmirx_init(void)
{
        u32 phy, scdc;
        unsigned int i;

        if (!apply)
                return -EINVAL;
        if (!request_mem_region(THDMIRX_BASE, THDMIRX_SIZE,
                                "h713-thdmirx-init"))
                return -EBUSY;
        region_owned = true;
        base = ioremap(THDMIRX_BASE, THDMIRX_SIZE);
        if (!base) {
                release_mem_region(THDMIRX_BASE, THDMIRX_SIZE);
                region_owned = false;
                return -ENOMEM;
        }

        for (i = 0; i < ARRAY_SIZE(saved); i++)
                saved[i].value = rx_read(saved[i].offset);

        pr_info("h713-thdmirx-init: before timer=%08x cmu=%08x phy=%08x descrand=%08x deframer=%08x scdc=%08x ced=%08x dma11=%08x mask=%08x enable=%08x\n",
                saved[0].value, saved[1].value, saved[2].value,
                saved[3].value, saved[4].value, saved[5].value,
                saved[6].value, rx_read(DMA_CONFIG11), saved[7].value,
                saved[8].value);

        rx_write(MAINUNIT_0_INT_MASK_N, 0xffffffff);
        writel(0xffffffff, base + MAINUNIT_0_INT_CLEAR);
        rx_write(GLOBAL_TIMER_REF_BASE, 428571429);
        udelay(10);

        rx_update(CMU_CONFIG0, CMU_TMDS_MARGIN | CMU_AUDIO_MARGIN,
                  FIELD_PREP(CMU_TMDS_MARGIN, 2) |
                  FIELD_PREP(CMU_AUDIO_MARGIN, 1));
        rx_update(DESCRAND_EN_CONTROL, DESCRAND_SEL,
                  FIELD_PREP(DESCRAND_SEL, 1));
        rx_update(CED_CONFIG,
                  CED_VIDEO_CHECK | CED_GB_CHECK | CED_CTRL_CHECK |
                  CED_LOCK_MAX,
                  CED_VIDEO_CHECK | CED_GB_CHECK | CED_CTRL_CHECK |
                  FIELD_PREP(CED_LOCK_MAX, 0x10));
        rx_update(DEFRAMER_CONFIG0,
                  DEFRAMER_VS_REMAP | DEFRAMER_ORDER,
                  DEFRAMER_VS_REMAP | FIELD_PREP(DEFRAMER_ORDER, 3));

        scdc = rx_read(SCDC_REGBANK_STATUS1);
        phy = PHY_RXDATA_WIDTH;
        if (scdc & SCDC_TMDSBITCLKRATIO)
                phy |= PHY_TMDS_CLOCK_RATIO;
        rx_write(PHY_CONFIG, phy);
        rx_write(GLOBAL_SWENABLE, SWENABLE_FULL);

        /* SCP owns the external HPD assertion.  Match the peer driver's
         * post-EDID steady state by releasing the internal HPD-low force. */
        rx_update(SCDC_CONFIG, SCDC_HPDLOW, 0);

        pr_info("h713-thdmirx-init: applied timer=%08x cmu=%08x phy=%08x descrand=%08x deframer=%08x scdc=%08x ced=%08x mask=%08x enable=%08x (scdc-status1=%08x)\n",
                rx_read(GLOBAL_TIMER_REF_BASE), rx_read(CMU_CONFIG0),
                rx_read(PHY_CONFIG), rx_read(DESCRAND_EN_CONTROL),
                rx_read(DEFRAMER_CONFIG0), rx_read(SCDC_CONFIG),
                rx_read(CED_CONFIG), rx_read(MAINUNIT_0_INT_MASK_N),
                rx_read(GLOBAL_SWENABLE), scdc);
        return 0;
}

static void __exit h713_thdmirx_exit(void)
{
        unsigned int i;

        if (base) {
                for (i = ARRAY_SIZE(saved); i-- > 0; )
                        rx_write(saved[i].offset, saved[i].value);
                iounmap(base);
                base = NULL;
        }
        if (region_owned) {
                release_mem_region(THDMIRX_BASE, THDMIRX_SIZE);
                region_owned = false;
        }
        pr_info("h713-thdmirx-init: restored controller registers\n");
}

module_init(h713_thdmirx_init);
module_exit(h713_thdmirx_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Opt-in H713 Synopsys HDMI-RX controller initializer");
