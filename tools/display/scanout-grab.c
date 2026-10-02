/*
 * Grab exactly what the display is scanning out, as a PPM. RUNS ON THE TARGET.
 *
 *   gcc -O2 -o scanout-grab scanout-grab.c $(pkg-config --cflags --libs libdrm)
 *   ./scanout-grab out.ppm [/dev/dri/card0]
 *
 * WHY. A photograph of the projection measures the camera, the throw and the
 * keystone as much as the pipeline, and the photo tool assumes the picture
 * fills the panel -- which a pillarboxed 4:3 or rotated clip does not. The
 * framebuffer on the plane is the pipeline's output, pixel for pixel, and needs
 * no operator. The panel's own path from that framebuffer on is unchanged by
 * the GPU work, so this is what WP2's geometry check actually needs.
 *
 * It takes the topmost plane with both a CRTC and a framebuffer whose format it
 * can read: XRGB/ARGB8888 (the GPU path's primary plane) or NV12 (the direct
 * path's video plane, converted with BT.601 limited range). GETFB2 returns
 * buffer handles only to a master or CAP_SYS_ADMIN, so run it as root. It also
 * prints the bounding box of non-black pixels: the picture's placement, which is
 * what aspect-fit, pillarboxing and rotation are judged by.
 */
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <linux/dma-buf.h>
#include <drm_fourcc.h>
#include <xf86drm.h>
#include <xf86drmMode.h>

static uint8_t clamp8(int v)
{
	return v < 0 ? 0 : v > 255 ? 255 : v;
}

int main(int argc, char **argv)
{
	const char *out = argc > 1 ? argv[1] : "scanout.ppm";
	const char *card = argc > 2 ? argv[2] : "/dev/dri/card0";
	drmModePlaneRes *res;
	drmModeFB2 *fb = NULL;
	unsigned int i;
	int fd;

	fd = open(card, O_RDWR | O_CLOEXEC);
	if (fd < 0) { perror(card); return 1; }
	drmSetClientCap(fd, DRM_CLIENT_CAP_UNIVERSAL_PLANES, 1);

	res = drmModeGetPlaneResources(fd);
	if (!res) { perror("GetPlaneResources"); return 1; }

	/* Last match wins: the plane list runs bottom (primary) to top. */
	for (i = 0; i < res->count_planes; i++) {
		drmModePlane *p = drmModeGetPlane(fd, res->planes[i]);
		drmModeFB2 *f;

		if (!p)
			continue;
		if (p->crtc_id && p->fb_id) {
			f = drmModeGetFB2(fd, p->fb_id);
			if (f && (f->pixel_format == DRM_FORMAT_XRGB8888 ||
				  f->pixel_format == DRM_FORMAT_ARGB8888 ||
				  f->pixel_format == DRM_FORMAT_NV12)) {
				if (fb)
					drmModeFreeFB2(fb);
				fb = f;
				fprintf(stderr, "plane %u fb %u %ux%u %.4s modifier 0x%llx pitch %u\n",
					p->plane_id, p->fb_id, f->width, f->height,
					(char *)&f->pixel_format,
					(unsigned long long)f->modifier, f->pitches[0]);
			} else if (f) {
				drmModeFreeFB2(f);
			}
		}
		drmModeFreePlane(p);
	}
	if (!fb || !fb->handles[0]) {
		fprintf(stderr, "no readable framebuffer on any active plane (root?)\n");
		return 1;
	}
	if (fb->modifier != DRM_FORMAT_MOD_LINEAR && fb->modifier != DRM_FORMAT_MOD_INVALID) {
		fprintf(stderr, "modifier 0x%llx is not linear; refusing to guess the layout\n",
			(unsigned long long)fb->modifier);
		return 1;
	}

	int dfd;
	if (drmPrimeHandleToFD(fd, fb->handles[0], DRM_CLOEXEC, &dfd)) {
		perror("PrimeHandleToFD");
		return 1;
	}
	size_t len = lseek(dfd, 0, SEEK_END);
	uint8_t *map = mmap(NULL, len, PROT_READ, MAP_SHARED, dfd, 0);
	if (map == MAP_FAILED) { perror("mmap dma-buf"); return 1; }
	struct dma_buf_sync sync = { DMA_BUF_SYNC_START | DMA_BUF_SYNC_READ };
	ioctl(dfd, DMA_BUF_IOCTL_SYNC, &sync);

	unsigned int w = fb->width, h = fb->height, x, y;
	unsigned int x0 = w, y0 = h, x1 = 0, y1 = 0;
	uint8_t *rgb = malloc((size_t)w * h * 3);

	for (y = 0; y < h; y++) {
		for (x = 0; x < w; x++) {
			uint8_t *d = rgb + ((size_t)y * w + x) * 3;

			if (fb->pixel_format == DRM_FORMAT_NV12) {
				int Y = map[fb->offsets[0] + y * fb->pitches[0] + x] - 16;
				const uint8_t *uv = map + fb->offsets[1] +
						    (y / 2) * fb->pitches[1] + (x & ~1U);
				int U = uv[0] - 128, V = uv[1] - 128;

				d[0] = clamp8((298 * Y + 409 * V + 128) >> 8);
				d[1] = clamp8((298 * Y - 100 * U - 208 * V + 128) >> 8);
				d[2] = clamp8((298 * Y + 516 * U + 128) >> 8);
			} else {
				const uint8_t *s = map + fb->offsets[0] +
						   y * fb->pitches[0] + x * 4;

				d[0] = s[2]; d[1] = s[1]; d[2] = s[0];
			}
			if (d[0] > 24 || d[1] > 24 || d[2] > 24) {
				if (x < x0) x0 = x;
				if (x > x1) x1 = x;
				if (y < y0) y0 = y;
				if (y > y1) y1 = y;
			}
		}
	}
	sync.flags = DMA_BUF_SYNC_END | DMA_BUF_SYNC_READ;
	ioctl(dfd, DMA_BUF_IOCTL_SYNC, &sync);

	FILE *f = fopen(out, "wb");
	if (!f) { perror(out); return 1; }
	fprintf(f, "P6\n%u %u\n255\n", w, h);
	fwrite(rgb, 3, (size_t)w * h, f);
	fclose(f);

	if (x1 >= x0)
		printf("GRAB %ux%u content x=%u..%u y=%u..%u (%ux%u) -> %s\n",
		       w, h, x0, x1, y0, y1, x1 - x0 + 1, y1 - y0 + 1, out);
	else
		printf("GRAB %ux%u content none (all black) -> %s\n", w, h, out);
	return 0;
}
