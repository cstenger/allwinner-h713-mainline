/* SPDX-License-Identifier: GPL-2.0 */
/*
 * NV16 -> NV12 for the H713 HDMI ring bridge (HDMI panel-source design 10.25,
 * route B). Shared by the kernel module and the host self-test
 * (tools/hdmi/test-nv12-convert.c), so the code that runs is the code tested.
 *
 * Luma is copied. Each NV12 chroma row r is the rounded average of NV16
 * chroma rows 2r and 2r+1 (vertically interstitial siting, the MPEG-2 /
 * H.264 default that the KMS NV12 plane assumes). CbCr are interleaved, so a
 * byte-wise average averages Cb with Cb and Cr with Cr. The average is done
 * eight bytes at a time with the carry-free identity
 *     ceil((a + b) / 2) = (a | b) - (((a ^ b) & 0xfe..fe) >> 1)
 * which is exact for every byte pair; a tail loop handles widths that are not
 * a multiple of 8.
 *
 * The includer provides u8 and u64 (kernel types, or the self-test's typedefs)
 * and memcpy.
 */
#ifndef H713_NV12_H
#define H713_NV12_H

#define H713_NV12_LOW7 0xfefefefefefefefeULL

static inline void h713_avg_rows(u8 *dst, const u8 *a, const u8 *b,
				 unsigned int n)
{
	unsigned int i = 0;

	for (; i + 8 <= n; i += 8) {
		u64 x, y;

		memcpy(&x, a + i, 8);
		memcpy(&y, b + i, 8);
		x = (x | y) - (((x ^ y) & H713_NV12_LOW7) >> 1);
		memcpy(dst + i, &x, 8);
	}
	for (; i < n; i++)
		dst[i] = (u8)((a[i] + b[i] + 1) >> 1);
}

/*
 * src_y / src_c: NV16 planes, each `width` bytes per line, `height` lines.
 * dst: NV12 frame, Y (width x height) then CbCr (width x height / 2).
 */
static inline void h713_nv16_to_nv12(u8 *dst, const u8 *src_y,
				     const u8 *src_c, unsigned int width,
				     unsigned int height)
{
	u8 *dst_c = dst + (unsigned long)width * height;
	unsigned int r;

	memcpy(dst, src_y, (unsigned long)width * height);
	for (r = 0; r < height / 2; r++)
		h713_avg_rows(dst_c + (unsigned long)r * width,
			      src_c + (unsigned long)(2 * r) * width,
			      src_c + (unsigned long)(2 * r + 1) * width,
			      width);
}

/* Full verification of a converted frame against the (re-read) source. */
static inline int h713_nv12_matches(const u8 *dst, const u8 *src_y,
				    const u8 *src_c, unsigned int width,
				    unsigned int height)
{
	const u8 *dst_c = dst + (unsigned long)width * height;
	unsigned int r, i;

	if (memcmp(dst, src_y, (unsigned long)width * height))
		return 0;
	for (r = 0; r < height / 2; r++) {
		const u8 *a = src_c + (unsigned long)(2 * r) * width;
		const u8 *b = a + width;
		const u8 *d = dst_c + (unsigned long)r * width;

		for (i = 0; i < width; i++)
			if (d[i] != (u8)((a[i] + b[i] + 1) >> 1))
				return 0;
	}
	return 1;
}

#endif
