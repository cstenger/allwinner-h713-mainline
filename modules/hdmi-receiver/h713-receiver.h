/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef H713_RECEIVER_H
#define H713_RECEIVER_H
#include <linux/types.h>
int h713_receiver_acquire(void);
void h713_receiver_release(void);
int h713_receiver_edid_register(void);
void h713_receiver_edid_unregister(void);
extern bool h713_receiver_edid_ready;
#endif
