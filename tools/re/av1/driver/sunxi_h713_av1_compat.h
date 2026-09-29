/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Lets sunxi_h713_av1_gen.c build in the kernel and in the host test rig
 * (tools/re/av1/rig). Kernel: plain kernel headers. Host: the handful of
 * kernel helpers the generator uses.
 */
#ifndef SUNXI_H713_AV1_COMPAT_H_
#define SUNXI_H713_AV1_COMPAT_H_

#ifdef __KERNEL__
#include <linux/errno.h>
#include <linux/kernel.h>
#include <linux/minmax.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <linux/unaligned.h>
#include <linux/v4l2-controls.h>
#else
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <linux/v4l2-controls.h>

typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
typedef int8_t s8;
typedef int16_t s16;
typedef int32_t s32;
typedef int64_t s64;

#define S16_MIN		(-32768)
#define S16_MAX		32767
#define GFP_KERNEL	0
#define kzalloc(n, f)	calloc(1, (n))
#define kfree(p)	free(p)
#define lower_32_bits(x)	((u32)(x))
#define ALIGN(x, a)	(((x) + (a) - 1) & ~((__typeof__(x))(a) - 1))
#define DIV_ROUND_UP(n, d)	(((n) + (d) - 1) / (d))
#define min_t(t, a, b)	((t)(a) < (t)(b) ? (t)(a) : (t)(b))
#define max_t(t, a, b)	((t)(a) > (t)(b) ? (t)(a) : (t)(b))
#ifndef H713_NO_CLAMP	/* rockchip_av1_filmgrain.c has its own clamp() */
#define clamp(v, lo, hi)	((v) < (lo) ? (lo) : (v) > (hi) ? (hi) : (v))
#define clamp_val(v, lo, hi)	clamp((v), (lo), (hi))
#endif
#define BIT(n)		(1u << (n))

static inline void put_unaligned_le16(u16 v, void *p)
{
	u8 *b = p;
	b[0] = v; b[1] = v >> 8;
}

static inline void put_unaligned_le32(u32 v, void *p)
{
	u8 *b = p;
	b[0] = v; b[1] = v >> 8; b[2] = v >> 16; b[3] = v >> 24;
}
#endif

#endif
