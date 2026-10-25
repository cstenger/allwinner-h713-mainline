// SPDX-License-Identifier: GPL-2.0
/*
 * Host self-test of modules/hdmi-v4l2/h713-nv12.h -- the exact header the
 * kernel bridge compiles (HDMI panel-source design 10.25, route B).
 *
 *   test-nv12-convert RING.nv16 FRAMES OUT.nv12
 *
 * 1. every (a, b) byte pair through the 8-byte path against (a+b+1)>>1;
 * 2. tail widths 1..40 against the same scalar rule;
 * 3. each 1280x720 frame of RING (Y plane then CbCr plane per frame) against
 *    an independent plain conversion, plus h713_nv12_matches accepting the
 *    result and refusing a one-bit corruption of luma and of chroma.
 * Writes the converted first frame to OUT for the end-to-end decode check.
 * Exit 0 only if everything matched.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef uint8_t u8;
typedef uint64_t u64;
#include "../../modules/hdmi-v4l2/h713-nv12.h"

#define W 1280u
#define H 720u

static int fails;

static void check(int ok, const char *what)
{
	if (!ok) {
		printf("FAIL: %s\n", what);
		fails++;
	}
}

int main(int argc, char **argv)
{
	static u8 a[65536 + 7], b[65536 + 7], d[65536 + 7];
	unsigned int i, n, f, frames;
	FILE *fp;
	u8 *ring, *out, *ref;
	size_t frame = (size_t)W * H * 2;

	if (argc != 4)
		return 2;
	frames = (unsigned int)atoi(argv[2]);
	/* 1. exhaustive byte pairs, laid out so most go through the 8-byte path */
	for (i = 0; i < 65536; i++) {
		a[i] = (u8)(i & 0xff);
		b[i] = (u8)(i >> 8);
	}
	h713_avg_rows(d, a, b, 65536);
	for (i = 0; i < 65536; i++)
		if (d[i] != (u8)((a[i] + b[i] + 1) >> 1))
			break;
	check(i == 65536, "byte-pair average (8-byte path)");
	/* 2. tails */
	for (n = 1; n <= 40; n++) {
		for (i = 0; i < n; i++) {
			a[i] = (u8)(i * 37 + n);
			b[i] = (u8)(255 - i * 11);
		}
		memset(d, 0xaa, sizeof(d));
		h713_avg_rows(d, a, b, n);
		for (i = 0; i < n; i++)
			if (d[i] != (u8)((a[i] + b[i] + 1) >> 1))
				break;
		check(i == n && d[n] == 0xaa, "tail width / no overrun");
	}
	/* 3. real ring frames */
	ring = malloc(frame * frames);
	out = malloc((size_t)W * H * 3 / 2);
	ref = malloc((size_t)W * H * 3 / 2);
	fp = fopen(argv[1], "rb");
	if (!fp || fread(ring, frame, frames, fp) != frames) {
		printf("FAIL: cannot read %u frames from %s\n", frames, argv[1]);
		return 1;
	}
	fclose(fp);
	for (f = 0; f < frames; f++) {
		const u8 *y = ring + f * frame, *c = y + (size_t)W * H;
		unsigned int r, x;

		h713_nv16_to_nv12(out, y, c, W, H);
		memcpy(ref, y, (size_t)W * H);
		for (r = 0; r < H / 2; r++)
			for (x = 0; x < W; x++)
				ref[(size_t)W * H + (size_t)r * W + x] =
					(u8)((c[(size_t)(2 * r) * W + x] +
					      c[(size_t)(2 * r + 1) * W + x] + 1) / 2);
		check(!memcmp(out, ref, (size_t)W * H * 3 / 2), "frame conversion vs plain reference");
		check(h713_nv12_matches(out, y, c, W, H) == 1, "verifier accepts a correct frame");
		out[12345] ^= 1;
		check(h713_nv12_matches(out, y, c, W, H) == 0, "verifier refuses corrupted luma");
		out[12345] ^= 1;
		out[(size_t)W * H + 54321] ^= 0x10;
		check(h713_nv12_matches(out, y, c, W, H) == 0, "verifier refuses corrupted chroma");
		out[(size_t)W * H + 54321] ^= 0x10;
		if (f == 0) {
			fp = fopen(argv[3], "wb");
			if (!fp || fwrite(out, (size_t)W * H * 3 / 2, 1, fp) != 1)
				check(0, "write OUT");
			if (fp)
				fclose(fp);
		}
	}
	printf("self-test %s (%u frames)\n", fails ? "FAILED" : "passed", frames);
	return fails ? 1 : 0;
}
