/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef H713_HDMI_DSP_H
#define H713_HDMI_DSP_H
#include <linux/types.h>
struct device;
extern bool h713_dsp_failed;
int h713_hdmi_dsp_reserve(void);
int h713_hdmi_dsp_prepare(struct device *device);
void h713_hdmi_dsp_release(void);
#endif
